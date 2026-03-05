"""Main CLI loop using prompt_toolkit."""
import asyncio
import subprocess
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from pathlib import Path

from geminiwebcli import config as cfg
from geminiwebcli.browser import GeminiBrowser
from geminiwebcli.commands import SessionState, handle, BLOCKED_BRANCHES
from geminiwebcli.context import load_git_context
from geminiwebcli.patch import extract_diffs, normalize_diff, apply_diff

HISTORY_FILE = Path.home() / ".geminiwebcli" / "history"
SLASH_COMMANDS = [
    "/upload", "/edit", "/plan", "/apply", "/git", "/run", "/clear",
    "/history", "/model", "/paste", "/help", "/exit",
]

EDIT_INSTRUCTION = (
    "IMPORTANT: You are in edit mode. You MUST respond with unified diffs ONLY. "
    "Wrap each diff in a fenced code block: ```diff ... ```. "
    "No explanations, no prose — only fenced unified diffs.\n"
    "Always use a/ and b/ prefixes, even for new or deleted files:\n"
    "```diff\n--- a/path/to/file\n+++ b/path/to/file\n@@ -L,N +L,N @@\n"
    " context\n-removed\n+added\n```\n"
    "For new files use @@ -0,0 +1,N @@ and only + lines.\n"
    "For deleted files use @@ -1,N +0,0 @@ and only - lines.\n"
)

PLAN_INSTRUCTION = (
    "IMPORTANT: Edit mode is now disabled. "
    "Stop responding with unified diffs. "
    "Return to normal responses: explanations, analysis, discussion. "
    "Do NOT output any diffs or patches."
)

PRIME_INSTRUCTION = "Study this project context carefully. When done, reply with just 'OK'."

console = Console()


def _build_session() -> PromptSession:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    completer = WordCompleter(SLASH_COMMANDS, sentence=True)
    kb = KeyBindings()

    @kb.add("escape", "enter")
    def _newline(event):
        event.current_buffer.insert_text("\n")

    return PromptSession(
        history=FileHistory(str(HISTORY_FILE)),
        completer=completer,
        key_bindings=kb,
        multiline=False,
    )


async def _paste_mode() -> str:
    """Read multiline input until Ctrl+D."""
    console.print("[dim]Paste mode: enter text, finish with Ctrl+D[/dim]")
    lines = []
    try:
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, input)
            lines.append(line)
    except EOFError:
        pass
    return "\n".join(lines)


async def run():
    conf = cfg.load()
    cwd = Path.cwd()

    if not (cwd / ".git").exists():
        console.print(f"[bold red]Error:[/bold red] Not a git repository: {cwd}")
        return
    r = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=cwd, capture_output=True, text=True
    )
    if r.returncode != 0:
        console.print("[bold red]Error:[/bold red] Empty git repository — please make an initial commit first.")
        return
    branch = r.stdout.strip()
    console.print(f"[dim]Branch: {branch} — loading context...[/dim]")
    context = load_git_context(cwd)
    file_count = context.count("=== ")
    console.print(f"[dim]{len(context)} chars from {file_count} files[/dim]")

    state = SessionState(model=conf.model, session_context=context, cwd=cwd, system_prompt=conf.system_prompt, run_commands=conf.run_commands)
    browser = GeminiBrowser(conf.profile_path, conf.headless)
    session = _build_session()

    console.print("[bold green]geminiwebcli[/bold green] - type [bold]/help[/bold] for commands")
    console.print("Starting browser...")
    try:
        await browser.start()
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] Failed to start browser: {e}")
        return
    if conf.model not in ("gemini-2.0-flash", "fast"):
        try:
            await browser.select_model(conf.model)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not set model {conf.model!r}: {e}[/yellow]")
    console.print("Ready.\n")

    try:
        while True:
            try:
                rel = state.cwd.relative_to(Path.home())
                mode = " <ansired>EDIT</ansired>" if state.edit_mode else " <ansigreen>PLAN</ansigreen>"
                prompt = HTML(f"<ansigreen>{rel}{mode} ></ansigreen> ")
                user_input = await session.prompt_async(prompt)
            except (EOFError, KeyboardInterrupt):
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            # Slash command
            if user_input.startswith("/"):
                result = await handle(user_input, state, browser)
                if result == "__exit__":
                    break
                elif result == "__paste_mode__":
                    user_input = await _paste_mode()
                    if not user_input.strip():
                        continue
                elif result == "__apply__":
                    user_input = "write me a patch!"
                    # fall through to message sending
                else:
                    if result:
                        console.print(result)
                    continue

            # Context priming: send context as separate message first
            if state.session_context and not state.context_sent:
                prime_parts = []
                if state.system_prompt:
                    prime_parts.append(state.system_prompt)
                prime_parts.append(state.session_context)
                prime_parts.append(PRIME_INSTRUCTION)
                console.print("[dim]Sending context...[/dim]")
                try:
                    await browser.send_message("\n\n".join(prime_parts))
                    async for _ in browser.stream_response():
                        pass  # discard ack
                    state.context_sent = True
                except Exception:
                    console.print("[bold red]Browser closed.[/bold red]")
                    break

            # Assemble message: pending upload + user text
            parts = []
            if state.session_context and not state.context_sent:
                parts.append(state.session_context)
            if state.edit_mode:
                parts.append(EDIT_INSTRUCTION)
            if state.pending_plan_reset:
                parts.append(PLAN_INSTRUCTION)
                state.pending_plan_reset = False
            if state.pending_upload:
                parts.append(state.pending_upload)
                state.pending_upload = ""
            parts.append(user_input)
            message = "\n\n".join(parts)

            # Send and stream response
            try:
                await browser.send_message(message)
                state.context_sent = True
            except Exception:
                console.print("[bold red]Browser closed.[/bold red]")
                break
            response_text = ""
            with Live(console=console, refresh_per_second=8, transient=True) as live:
                async for text in browser.stream_response():
                    response_text = text
                    live.update(Markdown(text))
            if response_text:
                console.print(Markdown(response_text))

            # Check for generated images (wait a bit for images to render)
            await asyncio.sleep(2)
            images = await browser.extract_images()
            if images:
                img_dir = state.cwd / "gemini-images"
                img_dir.mkdir(exist_ok=True)
                from time import strftime
                ts = strftime("%Y%m%d-%H%M%S")
                for i, img_data in enumerate(images, 1):
                    suffix = ".png" if img_data[:4] == b'\x89PNG' else ".jpg"
                    fname = img_dir / f"{ts}-{i}{suffix}"
                    fname.write_bytes(img_data)
                    console.print(f"[bold cyan]Image saved:[/bold cyan] {fname}")

            # In edit mode: detect and apply diffs
            if state.edit_mode and response_text:
                diffs = [normalize_diff(d, state.cwd) for d in extract_diffs(response_text)]
                total = len(diffs)
                any_skipped = False
                for n, diff in enumerate(diffs, 1):
                    fname = next((l[6:] for l in diff.splitlines() if l.startswith("+++ b/")), "?")
                    console.print(f"\n[bold yellow]Patch {n}/{total}:[/bold yellow] {fname}")
                    console.print(diff, markup=False)
                    if state.auto_apply_patch:
                        console.print("[dim]Auto-applying patch...[/dim]")
                        answer = "y"
                    else:
                        answer = await asyncio.get_event_loop().run_in_executor(
                            None, lambda: input("Apply this patch? [y/N] ")
                        )
                    if answer.strip().lower() == "y":
                        ok, out = apply_diff(diff, state.cwd)
                        if ok:
                            console.print(f"[green]Applied.[/green] {out}")
                            state.session_context = load_git_context(state.cwd)
                            state.context_sent = False
                        else:
                            console.print(f"[red]Failed:[/red] {out}")
                    else:
                        any_skipped = True
                if any_skipped:
                    await browser.new_chat()
                    state.session_context = load_git_context(state.cwd)
                    state.context_sent = False
                    console.print("[dim]Patches skipped → cleared chat, context reloaded.[/dim]")

            if state.post_apply_plan_reset:
                state.edit_mode = False
                state.pending_plan_reset = True
                state.post_apply_plan_reset = False
                state.auto_apply_patch = False
                console.print("[dim]Returned to PLAN mode.[/dim]")

    finally:
        await browser.stop()


def main():
    import argparse
    p = argparse.ArgumentParser(prog="geminiwebcli")
    p.add_argument("--bot", action="store_true", help="Telegram bot mode")
    args = p.parse_args()
    if args.bot:
        from geminiwebcli.bot import run_bot
        asyncio.run(run_bot())
    else:
        asyncio.run(run())


if __name__ == "__main__":
    main()
