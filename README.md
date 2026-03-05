# geminiwebcli

CLI tool for interacting with [Gemini](https://gemini.google.com) via browser automation (Playwright + Chromium). No API key required — uses your existing Google account.

## Requirements

- Python 3.11+
- Chromium (snap): `/snap/bin/chromium`
- `patch` command (for edit mode)
- Must be run from a **git repository** on a **feature branch**

## Installation

```bash
pip install -e .
playwright install chromium
```

## First Run (Login)

On first start, a browser window opens for Google login:

```bash
geminiwebcli
```

1. Log in with your Google account in the browser window
2. Press **Enter** in the terminal when done
3. The browser profile is saved to `~/snap/chromium/common/geminiwebcli/`

Subsequent starts use the saved profile and run headless by default.

## Git Workflow

geminiwebcli only works inside a git repository. On startup it:

1. Checks for a `.git` directory in the current working directory
2. Rejects protected branches (`master`, `main`, `qa`, `devel`) — only feature branches are allowed
3. Loads all git-tracked files (`git ls-files`) as context automatically

```bash
cd ~/myproject          # must have .git here
git checkout -b my-feature
geminiwebcli
```

## Configuration

Config file is created automatically at `~/.geminiwebcli/config.toml`:

```toml
profile_dir = "/home/user/snap/chromium/common/geminiwebcli"
headless = false
model = "gemini-2.0-flash"
system_prompt = "..."

# telegram_token = "1234:AAxx..."
# telegram_chat_id = "155463840"

# Allowed commands for /run (key = alias, value = shell command):
# [run]
# test = "pytest"
# lint = "ruff check ."
# build = "make build"
```

| Option | Default | Description |
|---|---|---|
| `profile_dir` | `~/snap/chromium/common/geminiwebcli` | Browser profile directory |
| `headless` | `false` | Run browser without GUI |
| `model` | `gemini-2.0-flash` | Gemini model (display only) |
| `system_prompt` | (built-in) | System prompt prepended to every message |
| `telegram_token` | — | Telegram bot token (required for `--bot` mode) |
| `telegram_chat_id` | — | Restrict bot to this Telegram chat ID |
| `[run]` | — | Allowed commands for `/run` (see below) |

## Usage

Type your message and press **Enter** to send. Use **Escape+Enter** for a newline within a message.

## Commands

| Command | Description |
|---|---|
| `/edit` | Enable edit mode — Gemini returns diffs that can be applied interactively |
| `/plan` | Disable edit mode, keep context |
| `/apply [-y]` | Switch to edit mode, send "write me a patch!", apply diffs, return to plan mode (`-y`: skip confirmation) |
| `/git <args>` | Run a git command and reload context |
| `/run [key]` | Run a configured command by key (no key = list all) |
| `/upload <file\|dir> [glob]` | Append files to next message only |
| `/clear` | Start a new conversation and reload context |
| `/history` | Show context summary |
| `/model [name]` | Show or change the model name |
| `/paste` | Enter multiline paste mode (finish with Ctrl+D) |
| `/help` | Show command list |
| `/exit` | Quit |

## Keybindings

| Key | Action |
|---|---|
| `Enter` | Send message |
| `Escape+Enter` | Insert newline |
| `Up` / `Down` | Browse input history |
| `Tab` | Autocomplete slash commands |
| `Ctrl+D` | Quit (or end paste mode) |

## Prompt

The prompt shows the current working directory relative to `$HOME`, and the current mode:

```
gitlab/myproject PLAN >
gitlab/myproject EDIT >
```

`PLAN` (green) is the default mode. `EDIT` (red) is active when edit mode is enabled.

## Edit Mode

`/edit` instructs Gemini to return code changes as unified diffs. After each response, detected diffs are shown and applied interactively.

- New files are automatically staged with `git add`
- Deleted files are removed with `git rm`
- File paths outside the repository are rejected
- Diff headers are normalized automatically (absolute paths, `/dev/null` variants)

```
gitlab/myproject PLAN > /edit
Edit mode enabled.

gitlab/myproject EDIT > Create a bash script that lists all files

Patch 1/1: list_files.sh
--- a/list_files.sh
+++ b/list_files.sh
@@ -0,0 +1,3 @@
+#!/bin/bash
+
+ls -1

Apply this patch? [y/N] y
Applied.
```

Use `/plan` to return to plan mode without clearing the conversation.

## /git and /run

`/git` runs any git command and reloads the context afterwards:

```
gitlab/myproject PLAN > /git status
gitlab/myproject PLAN > /git add newfile.py
gitlab/myproject PLAN > /git diff HEAD
```

`/run` executes commands defined in the `[run]` section of `~/.geminiwebcli/config.toml`:

```toml
[run]
test   = "pytest -v"
lint   = "ruff check ."
build  = "make build"
```

```
gitlab/myproject PLAN > /run
Configured run commands:
  test                 pytest -v
  lint                 ruff check .
  build                make build

gitlab/myproject PLAN > /run test
```

## Telegram Bot Mode

geminiwebcli can run as a Telegram bot, forwarding messages to Gemini and returning responses:

```bash
geminiwebcli --bot
```

Configure `telegram_token` and optionally `telegram_chat_id` in `~/.geminiwebcli/config.toml`. All slash commands are available via Telegram, including `/edit`, `/apply`, and `/run`.
