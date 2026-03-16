"""Slash command parser and handlers."""
import asyncio
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from rich.console import Console
from rich.panel import Panel
from geminiwebcli import context as ctx
from geminiwebcli.batch import parse_prompt_file

BLOCKED_BRANCHES = {"master", "main", "qa", "devel"}
_console = Console()


@dataclass
class SessionState:
    session_context: str = ""       # git ls-files context, stays for whole session
    pending_upload: str = ""        # /upload: appended to next message
    model: str = "gemini-2.0-flash"
    edit_mode: bool = False         # /edit: apply diffs from responses
    cwd: Path = field(default_factory=Path.cwd)
    system_prompt: str = ""         # prepended to every message
    context_sent: bool = False      # True after context was sent once
    pending_plan_reset: bool = False  # send PLAN_INSTRUCTION on next message
    post_apply_plan_reset: bool = False  # /apply: return to PLAN after patching
    auto_apply_patch: bool = False       # /apply -y: skip confirmation
    run_commands: dict = field(default_factory=dict)  # allowed /run aliases


COMMANDS = {}


def command(name: str):
    def decorator(fn: Callable):
        COMMANDS[name] = fn
        return fn
    return decorator


async def handle(line: str, state: SessionState, browser) -> str | None:
    """Parse and dispatch a slash command. Returns text to print or None."""
    parts = line.strip().split()
    cmd = parts[0].lstrip("/")
    args = parts[1:]

    handler = COMMANDS.get(cmd)
    if handler is None:
        return f"Unknown command: /{cmd}. Type /help for a list."
    return await handler(args, state, browser)


@command("upload")
async def cmd_upload(args, state: SessionState, browser) -> str:
    if not args:
        return "Usage: /upload <file|dir> [glob]"
    path, glob = args[0], args[1] if len(args) > 1 else "*"
    try:
        state.pending_upload = ctx.load_files(path, glob)
        return f"Loaded upload: {path} ({len(state.pending_upload)} chars)"
    except FileNotFoundError as e:
        return str(e)


@command("edit")
async def cmd_edit(args, state: SessionState, browser) -> str:
    r = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=state.cwd, capture_output=True, text=True
    )
    branch = r.stdout.strip()
    if branch in BLOCKED_BRANCHES:
        _console.print(Panel(
            f"[bold]You are on a protected branch: [red]{branch}[/red][/bold]\n"
            "Edit mode may cause direct changes to the main codebase!",
            title="[bold red]⚠  WARNING[/bold red]",
            border_style="bold red",
        ))
        answer = await asyncio.get_event_loop().run_in_executor(
            None, lambda: input('Type "YES" to confirm: ')
        )
        if answer.strip() != "YES":
            return "Cancelled."
    state.edit_mode = True
    return "Edit mode enabled."


@command("plan")
async def cmd_plan(args, state: SessionState, browser) -> str:
    if state.edit_mode:
        state.pending_plan_reset = True
    state.edit_mode = False
    return "Edit mode disabled. Context unchanged."


@command("git")
async def cmd_git(args, state: SessionState, browser) -> str:
    if not args:
        return "Usage: /git <git-args>"
    r = subprocess.run(["git"] + args, cwd=state.cwd, capture_output=True, text=True)
    state.session_context = ctx.load_git_context(state.cwd)
    output = (r.stdout + r.stderr).strip()
    suffix = f"\nContext reloaded: {len(state.session_context)} chars"
    return (output + suffix) if output else suffix.strip()


@command("run")
async def cmd_run(args, state: SessionState, browser) -> str:
    cmds = state.run_commands
    if not cmds:
        return (
            "No /run commands configured.\n\n"
            "Add a [run] section to ~/.geminiwebcli/config.toml to define allowed commands:\n\n"
            "  \\[run]\n"
            '  test   = "pytest -v"\n'
            '  lint   = "ruff check ."\n'
            '  build  = "make build"\n'
            '  deploy = "ansible-playbook site.yml"\n\n'
            "Usage after configuration:\n"
            "  /run          — list all configured commands\n"
            "  /run test     — execute the command mapped to 'test'"
        )
    if not args:
        lines = [f"  {k:<20} {v}" for k, v in cmds.items()]
        return "Configured run commands:\n" + "\n".join(lines)
    key = args[0]
    if key not in cmds:
        return f"Unknown key: '{key}'. Available: {', '.join(cmds)}"
    r = subprocess.run(cmds[key], cwd=state.cwd, capture_output=True, text=True, shell=True)
    return (r.stdout + r.stderr).strip() or "(no output)"


@command("clear")
async def cmd_clear(args, state: SessionState, browser) -> str:
    state.pending_upload = ""
    state.edit_mode = False
    await browser.new_chat()
    state.session_context = ctx.load_git_context(state.cwd)
    state.context_sent = False
    return "Conversation cleared. Context reloaded."


@command("history")
async def cmd_history(args, state: SessionState, browser) -> str:
    if not state.session_context:
        return "No context loaded."
    lines = state.session_context.count("\n")
    return f"Session context: {len(state.session_context)} chars, {lines} lines"


@command("model")
async def cmd_model(args, state: SessionState, browser) -> str:
    if not args:
        try:
            models = await browser.get_models()
            lines = [f"Current: {state.model}", "Available:"]
            lines += [f"  {k:<24} {v['name']:<20} {v['desc']}" for k, v in models.items()]
            return "\n".join(lines)
        except Exception as e:
            return f"Current model: {state.model} (could not fetch list: {e})"
    try:
        display = await browser.select_model(args[0])
        state.model = args[0]
        return f"Model set to: {display}"
    except Exception as e:
        return f"Failed to switch model: {e}"


@command("apply")
async def cmd_apply(args, state: SessionState, browser) -> str:
    auto_yes = "-y" in args or "--yes" in args
    result = await cmd_edit([], state, browser)
    if result == "Cancelled.":
        return result
    state.post_apply_plan_reset = True
    state.auto_apply_patch = auto_yes
    return "__apply__"


@command("paste")
async def cmd_paste(args, state: SessionState, browser) -> str:
    return "__paste_mode__"  # handled by cli.py


@command("help")
async def cmd_help(args, state: SessionState, browser) -> str:
    cmds = {
        "/upload <file|dir> [glob]": "Append files to next message",
        "/edit":                     "Enable edit mode (apply diffs from responses)",
        "/plan":                     "Disable edit mode (keep context)",
        "/apply [-y]":               "EDIT → 'write me a patch!' → apply → PLAN (-y: auto-yes)",
        "/ref <image-path>":         "Upload reference image for next message",
        "/image <prompt>":           "Send prompt and save generated images",
        "/save-images":              "Save all images from current chat history",
        "/batch <file> [opts]":      "Batch image gen (--dry-run, --start-at, --resume, --retries N)",
        "/git <args>":               "Run git command + reload context",
        "/run [key]":                "Run allowed command by key (no key = list all)",
        "/clear":                    "New conversation + reload context",
        "/history":                  "Show context summary",
        "/model [name]":             "Show or set model",
        "/paste":                    "Enter multiline paste mode",
        "/help":                     "Show this help",
        "/exit":                     "Quit",
    }
    return "\n".join(f"  {k:<30} {v}" for k, v in cmds.items())


@command("image")
async def cmd_image(args, state: SessionState, browser) -> str:
    """Send a prompt and extract generated images."""
    if not args:
        return "Usage: /image <prompt text>\n  Sends the prompt and saves any generated images."
    return "__image__:" + " ".join(args)


@command("ref")
async def cmd_ref(args, state: SessionState, browser) -> str:
    """Upload a reference image to include with the next message."""
    if not args:
        return "Usage: /ref <image-path>\n  Uploads an image as reference for the next message."
    image_path = Path(" ".join(args)).expanduser()
    if not image_path.exists():
        return f"File not found: {image_path}"
    if not image_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        return f"Not an image file: {image_path}"
    try:
        await browser.upload_image(image_path)
        return f"Reference image uploaded: {image_path.name}\nType your message — it will be sent together with the image."
    except Exception as e:
        return f"Upload failed: {e}"


@command("save-images")
async def cmd_save_images(args, state: SessionState, browser) -> str:
    """Extract and save all images from the current chat history."""
    return "__save_images__"


@command("batch")
async def cmd_batch(args, state: SessionState, browser) -> str:
    """Parse a prompt file and run batch image generation."""
    if not args:
        return "Usage: /batch <file.md> [--dry-run] [--start-at <name>] [--resume] [--retries N]"
    filepath = args[0]
    dry_run = "--dry-run" in args
    start_at = None
    if "--start-at" in args:
        idx = args.index("--start-at")
        if idx + 1 < len(args):
            start_at = args[idx + 1]

    p = Path(filepath).expanduser()
    if not p.exists():
        return f"File not found: {filepath}"
    try:
        batch = parse_prompt_file(p)
    except Exception as e:
        return f"Parse error: {e}"

    prompts = batch.prompts
    if not prompts:
        return "No prompts found in file."

    if start_at:
        found = False
        for i, pr in enumerate(prompts):
            if start_at in pr.filename:
                prompts = prompts[i:]
                found = True
                break
        if not found:
            return f"Start-at '{start_at}' not found. Available: {', '.join(p.filename for p in prompts)}"

    if dry_run:
        # Check progress file
        import json
        subdir = Path(filepath).stem
        progress_file = state.cwd / "gemini-images" / subdir / ".batch-progress.json"
        done = []
        if progress_file.exists():
            prog = json.loads(progress_file.read_text())
            done = prog.get("done", [])
            failed = prog.get("failed", [])

        lines = [f"Intro: {len(batch.intro)} chars", f"Style prefix: {len(batch.style_prefix)} chars", f"Prompts: {len(prompts)}", ""]
        for i, pr in enumerate(prompts, 1):
            note = f" ({pr.note})" if pr.note else ""
            status = ""
            if pr.filename in done:
                status = " [green]DONE[/green]"
            elif failed and pr.filename in failed:
                status = " [red]FAILED[/red]"
            lines.append(f"  {i:>2}. {pr.filename}{note}{status}")
        if done:
            lines.append(f"\n  {len(done)}/{len(prompts)} completed. Use --resume to skip done.")
        return "\n".join(lines)

    # Return batch data for cli.py to process
    return f"__batch__:{filepath}"


@command("exit")
async def cmd_exit(args, state: SessionState, browser) -> str:
    return "__exit__"  # handled by cli.py
