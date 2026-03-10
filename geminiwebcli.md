# geminiwebcli

Playwright-basierte CLI für Google Gemini (Browser-Automation). Ursprünglich von einem Kollegen.

## Repo
- GitHub: `https://github.com/viperdriver2000/geminiwebcli` (public)
- Lokal: `/home/viperdriver2000/tmp/geminiwebcli/`
- Branch: `master`

## Tech Stack
- Python >=3.11 (lokal 3.12.13 via pyenv)
- Playwright + Chromium
- prompt_toolkit, rich
- Optional: python-telegram-bot (Bot-Modus)

## Setup
- venv: `.venv/` im Projektverzeichnis
- `pip install -e ".[bot]"` für editable install mit Telegram-Support
- `playwright install chromium` für den Browser
- Starten: `source .venv/bin/activate && geminiwebcli`

## Features
- Interaktive CLI mit Gemini via Browser
- Image-Extraktion aus Gemini-Responses (speichert nach `gemini-images/`)
- Chromium-Discovery (snap, which-Fallback, Playwright-bundled)
- Telegram Bot-Modus (`--bot`)
- Edit-Mode mit Diff-Erkennung und Patch-Anwendung
