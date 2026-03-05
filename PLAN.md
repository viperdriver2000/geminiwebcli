# geminiwebcli - Implementation Plan

## Overview
A CLI tool that communicates with the Gemini website (gemini.google.com) via browser
automation, giving a claude-CLI-like user experience.

## Architecture

```
prompt_toolkit CLI
    ↓ (slash commands / text)
Command Parser
    ↓ (assembled prompt text)
Playwright → gemini.google.com
    ↓ (scrape response)
rich Renderer → Terminal
```

## Tech Stack
- **prompt_toolkit** - CLI with history, tab-completion, multiline input, keybindings
- **playwright** (async) - browser automation for Gemini web interface
- **rich** - pretty terminal output (markdown rendering, syntax highlighting)

## Setup Flow
1. First run: browser opens visibly → user logs in manually with Google account
2. Browser profile saved to `~/.geminiwebcli/profile/`
3. Subsequent runs: headless mode, reuses saved profile

## Config File
`~/.geminiwebcli/config.toml`:
```toml
profile_dir = "~/.geminiwebcli/profile"
headless = true
model = "gemini-2.0-flash"   # or gemini-2.5-pro etc.
```

## Slash Commands (MVP)
| Command | Description |
|---|---|
| `/upload <file\|dir> [glob]` | Concatenate files and append to next message |
| `/context <dir> [glob]` | Load project context (stays for whole session) |
| `/clear` | Reset conversation (new Gemini chat) |
| `/history` | Show currently loaded context summary |
| `/model [name]` | Show or switch Gemini model |
| `/paste` | Enter multiline paste mode (end with Ctrl+D) |
| `/help` | List all commands |
| `/exit` | Quit |

## File Upload Format
Files are concatenated with separators:
```
=== path/to/file.py ===
<file content>

=== path/to/other.py ===
<file content>
```

## CLI Features
- Arrow key history (up/down)
- Tab completion for slash commands and file paths
- `Alt+Enter` for newline in input
- Multiline responses rendered as Markdown via `rich`
- Streaming output (character by character as Gemini types)

## Project Structure
```
geminiwebcli/
├── geminiwebcli/
│   ├── __init__.py
│   ├── cli.py          # prompt_toolkit setup, main loop
│   ├── browser.py      # Playwright / Gemini interaction
│   ├── commands.py     # Slash command parser and handlers
│   ├── context.py      # File loading and concatenation
│   └── config.py       # Config file handling
├── tests/
├── pyproject.toml
└── README.md
```

## Installation (target)
```bash
pip install geminiwebcli
playwright install chromium
geminiwebcli          # first run opens browser for login
```

## Open Questions / Future
- Headless mode might need extra workarounds (Google bot detection)
- Streaming: Gemini types character by character - needs polling or DOM-watching
- Model switching: depends on UI availability per account (free vs. Advanced)
