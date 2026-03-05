# geminiwebcli – Project Notes

## Architecture

- **browser.py** – Playwright/Chromium automation; DOM text extraction, message send/stream
- **cli.py** – prompt_toolkit REPL; context priming, edit/plan mode, diff application
- **commands.py** – slash command handlers, `SessionState`
- **patch.py** – unified diff extraction, normalization, hunk count fix, `patch -p1` application
- **context.py** – git-tracked file context builder
- **config.py** – TOML config, profile path, system prompt default

## Key Design Decisions

### Context Priming
Context + system prompt sent as a **separate first message** (ACK discarded) before the user's
actual question. Prevents Gemini from being overwhelmed by large first messages.
Triggered when `state.context_sent == False` (after start, `/git`, `/clear`, patch apply).

### Edit / Plan Mode
- **EDIT mode**: `EDIT_INSTRUCTION` prepended to each message; Gemini must respond with
  `\`\`\`diff` fenced unified diffs only.
- **PLAN mode**: default; `PLAN_INSTRUCTION` sent once (via `pending_plan_reset` flag) to
  tell Gemini to stop producing diffs.
- Prompt shows `EDIT` (red) or `PLAN` (green).

### DOM Text Extraction (`_get_response_text`)
`innerText` alone loses code block structure. Custom JS `toMarkdown()` traverses the DOM:
- `<pre>` → reconstruct ` ```lang\n...\n``` `
- `<code>` → `` `...` ``
- `<br>` → `\n`
- block elements → append `\n`
- Language label (outside `<pre>`) → folded into fence via regex post-processing:
  `\nBash\n\n\`\`\`\n` → ` \`\`\`bash\n`

### Patch Robustness
- `_fix_hunk_counts()`: recalculates `@@ -start,count +new_start,count @@` headers from
  actual diff lines before calling `patch`. Fixes Gemini sometimes claiming wrong counts.
- `--reject-file=/dev/null`: suppresses `.rej` file creation on patch failure.
- `--no-backup-if-mismatch`: no `.orig` backup files.

## Known Issues / Gotchas

- **Syntax highlighting intermittent**: Language label regex range `{2,6}` covers most cases
  but DOM nesting can vary. Widening the range further risks false positives.
- **Gemini send button label**: hardcoded German `"Nachricht senden"` — breaks if UI locale
  changes. Falls back to `Enter` key.
- **`SYSTEM_CHROMIUM`**: hardcoded `/snap/bin/chromium` — adjust for non-snap installs.

## Workflow

```
geminiwebcli          # start in a git repo
/edit                 # switch to edit mode (Gemini produces diffs)
/plan                 # back to plan mode
/git status           # run git command + reload context
/clear                # new chat + reload context
/upload <file>        # attach file content to next message
/paste                # multiline input until Ctrl+D
```
