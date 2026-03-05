"""Telegram bot I/O interface for geminiwebcli."""
import asyncio
import logging
import subprocess
from pathlib import Path

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from geminiwebcli import config as cfg
from geminiwebcli.browser import GeminiBrowser
from geminiwebcli.commands import SessionState, handle, BLOCKED_BRANCHES
from geminiwebcli.context import load_git_context
from geminiwebcli.patch import extract_diffs, normalize_diff, apply_diff
from geminiwebcli.cli import EDIT_INSTRUCTION, PLAN_INSTRUCTION, PRIME_INSTRUCTION

log = logging.getLogger(__name__)
_MAX_MSG = 4096


async def _send_long(reply_fn, text: str, **kwargs):
    """Send text split into Telegram-safe chunks."""
    for i in range(0, max(len(text), 1), _MAX_MSG):
        await reply_fn(text[i:i + _MAX_MSG], **kwargs)


async def run_bot():
    conf = cfg.load()
    if not conf.telegram_token:
        print("Error: telegram_token not set in ~/.geminiwebcli/config.toml")
        return

    cwd = Path.cwd()
    if not (cwd / ".git").exists():
        print(f"Error: Not a git repository: {cwd}")
        return
    r = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=cwd, capture_output=True, text=True,
    )
    if r.returncode != 0:
        print("Error: Empty git repository — please make an initial commit first.")
        return
    branch = r.stdout.strip()
    context = load_git_context(cwd)
    print(f"Branch: {branch} — {len(context)} chars from {context.count('=== ')} files")

    state = SessionState(
        model=conf.model, session_context=context,
        cwd=cwd, system_prompt=conf.system_prompt,
        run_commands=conf.run_commands,
    )

    print("Starting browser...")
    browser = GeminiBrowser(conf.profile_path, conf.headless)
    try:
        await browser.start()
    except Exception as e:
        print(f"Error: Failed to start browser: {e}")
        return
    print(f"Ready. Starting Telegram bot. chat_id={conf.telegram_chat_id or 'any'}")

    message_lock = asyncio.Lock()
    confirm_queue: asyncio.Queue[str] = asyncio.Queue()
    state_box = {"awaiting": False}

    async def handle_message(update: Update, context_tg: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        if conf.telegram_chat_id and str(update.message.chat_id) != str(conf.telegram_chat_id):
            log.warning("Ignored message from chat_id=%s", update.message.chat_id)
            return

        text = update.message.text.strip()
        reply = update.message.reply_text

        # Route to confirmation queue if we're waiting for y/n
        if state_box["awaiting"]:
            print(f"← {text}  [confirmation]")
            await confirm_queue.put(text)
            return

        async with message_lock:
            print(f"← {text}")
            await _process(text, reply, state, browser, confirm_queue, state_box, conf)

    app = Application.builder().token(conf.telegram_token).concurrent_updates(True).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.COMMAND, handle_message))

    try:
        async with app:
            await app.start()
            await app.updater.start_polling(
                allowed_updates=["message"],
                drop_pending_updates=True,
            )
            if conf.telegram_chat_id:
                await app.bot.send_message(
                    chat_id=conf.telegram_chat_id,
                    text=f"Hello from {cwd.name} ({branch})",
                )
            await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        print("\nShutting down...")
        await browser.stop()


async def _confirm_via_telegram(question: str, reply_fn, confirm_queue, state_box,
                                 timeout: int = 120) -> str:
    state_box["awaiting"] = True   # set before await so incoming reply is routed to queue
    await reply_fn(question)
    try:
        return await asyncio.wait_for(confirm_queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        await reply_fn("Timeout — skipped.")
        return "n"
    finally:
        state_box["awaiting"] = False


async def _process(text: str, reply_fn, state: SessionState, browser: GeminiBrowser,
                   confirm_queue, state_box, conf):
    # ── Slash command ──────────────────────────────────────────────────────────
    if text.startswith("/") and not text == "/start":
        # Handle /edit separately: branch protection via Telegram
        if text.strip().lstrip("/").split()[0] == "edit":
            r = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=state.cwd, capture_output=True, text=True,
            )
            branch = r.stdout.strip()
            if branch in BLOCKED_BRANCHES:
                answer = await _confirm_via_telegram(
                    f"⚠ Protected branch: *{branch}*\nType YES to confirm edit mode.",
                    reply_fn, confirm_queue, state_box,
                )
                if answer.strip() != "YES":
                    await reply_fn("Cancelled.")
                    return
            state.edit_mode = True
            print("[bot] EDIT mode on")
            await reply_fn("Edit mode enabled.")
            return

        result = await handle(text, state, browser)

        if result == "__exit__":
            await reply_fn("Goodbye.")
            print("→ exit")
            return
        elif result == "__apply__":
            print("[bot] /apply → injecting 'write me a patch!'")
            text = "write me a patch!"
            # fall through to message sending
        elif result == "__paste_mode__":
            await reply_fn("Paste mode is not available in bot mode. Send text directly.")
            return
        elif result:
            print(f"→ {result[:80]}")
            await _send_long(reply_fn, result)
            return
        else:
            return

    # ── Context priming ────────────────────────────────────────────────────────
    if state.session_context and not state.context_sent:
        prime_parts = []
        if state.system_prompt:
            prime_parts.append(state.system_prompt)
        prime_parts.append(state.session_context)
        prime_parts.append(PRIME_INSTRUCTION)
        print("[context] Sending context...")
        try:
            await browser.send_message("\n\n".join(prime_parts))
            async for _ in browser.stream_response():
                pass
            state.context_sent = True
            print("[context] OK")
        except Exception as e:
            await reply_fn(f"Browser error during context priming: {e}")
            return

    # ── Assemble message ───────────────────────────────────────────────────────
    parts = []
    if state.edit_mode:
        parts.append(EDIT_INSTRUCTION)
    if state.pending_plan_reset:
        parts.append(PLAN_INSTRUCTION)
        state.pending_plan_reset = False
    if state.pending_upload:
        parts.append(state.pending_upload)
        state.pending_upload = ""
    parts.append(text)
    message = "\n\n".join(parts)

    # ── Send to Gemini, collect full response ──────────────────────────────────
    try:
        await browser.send_message(message)
        state.context_sent = True
    except Exception as e:
        await reply_fn(f"Browser error: {e}")
        return

    print("[gemini] Waiting for response...")
    response_text = ""
    async for chunk in browser.stream_response():
        response_text = chunk

    print(f"[gemini] {len(response_text)} chars → sending")
    if response_text:
        await _send_long(reply_fn, response_text)

    # ── Edit mode: detect and apply diffs ─────────────────────────────────────
    if state.edit_mode and response_text:
        diffs = [normalize_diff(d, state.cwd) for d in extract_diffs(response_text)]
        total = len(diffs)
        for n, diff in enumerate(diffs, 1):
            fname = next((l[6:] for l in diff.splitlines() if l.startswith("+++ b/")), "?")
            preview = diff[:800] + ("…" if len(diff) > 800 else "")
            question = f"Patch {n}/{total}: {fname}\n```\n{preview}\n```\nApply? (y/N)"
            if state.auto_apply_patch:
                answer = "y"
                print("[patch] Auto-applying...")
            else:
                print("[patch] Asking to apply...")
                answer = await _confirm_via_telegram(question, reply_fn, confirm_queue, state_box)
            print(f"[patch] Answer: {answer!r}")
            if answer.strip().lower() == "y":
                ok, out = apply_diff(diff, state.cwd)
                if ok:
                    state.session_context = load_git_context(state.cwd)
                    state.context_sent = False
                    await reply_fn(f"Applied. {out}")
                    print("[patch] Applied")
                else:
                    await reply_fn(f"Failed: {out}")
                    print(f"[patch] Failed: {out}")

    # ── /apply: return to PLAN mode ────────────────────────────────────────────
    if state.post_apply_plan_reset:
        state.edit_mode = False
        state.pending_plan_reset = True
        state.post_apply_plan_reset = False
        state.auto_apply_patch = False
        await reply_fn("Returned to PLAN mode.")
        print("→ Returned to PLAN mode.")
