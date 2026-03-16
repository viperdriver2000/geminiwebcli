# geminiwebcli

Playwright-basierte CLI für Google Gemini (Browser-Automation). Ursprünglich von einem Kollegen, weiterentwickelt mit Fokus auf Bildgenerierung.

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

## Architektur (7 Module)
- `browser.py` — Playwright-Automation, DOM-Extraktion, Streaming, Bild-Upload/-Download
- `cli.py` — REPL, Context-Priming, Edit/Plan-Modus, Batch-Runner
- `commands.py` — Slash-Commands, SessionState
- `batch.py` — Markdown-Prompt-Datei-Parser (Intro, Style, Prompts, Ref-Images)
- `patch.py` — Diff-Extraktion, Normalisierung, `patch -p1`
- `context.py` — Git-File-Context-Builder
- `config.py` — TOML-Config inkl. `image_dir`

## Features

### Chat & Code
- Interaktive REPL mit Prompt-History und Tab-Completion
- Automatischer Git-Context (alle tracked Files)
- Edit-Mode mit Diff-Erkennung und Patch-Anwendung (`/edit`, `/apply`)
- Modell-Wechsel (`/model`)
- Telegram Bot-Modus (`--bot`)

### Bildgenerierung
- `/image <prompt>` — Einzelbild generieren + speichern
- `/batch <file.md>` — Sequentielle Bildgenerierung aus Markdown-Prompt-Datei
  - Intro-Context (Charaktere, Stil, Regeln) in jeder Message
  - No-Text-Instruction automatisch eingebaut
  - `--dry-run` — nur Prompt-Liste anzeigen (mit DONE/FAILED Status)
  - `--start-at <name>` — ab bestimmtem Prompt starten
  - `--resume` — erledigte überspringen, fehlgeschlagene retries
  - `--retries N` — Anzahl Versuche pro Bild (default 1)
  - `--model <name>` — Modell nur für Batch wechseln
  - Ref-Images pro Prompt: `### file.png [ref: path/to/ref.png]`
  - Progress-Tracking via `.batch-progress.json`
  - Ctrl+C = sauber pausieren, Progress speichern
  - Bilder in Unterverzeichnis pro Batch-Datei
- `/ref <image>` — Referenzbild für nächste Nachricht hochladen
- `/gallery` — Alle gespeicherten Bilder auflisten (Größen, Gruppen)
- `/save-images` — Alle Bilder aus Chat-History nachträglich speichern
- `image_dir` in config.toml konfigurierbar (default: `gemini-images`)

### Sonstiges
- `/upload <file>` — Dateien an nächste Nachricht anhängen
- `/git <args>` — Git-Befehle mit auto Context-Reload
- `/run <alias>` — Vorkonfigurierte Shell-Commands
- Chromium-Discovery (snap, which-Fallback, Playwright-bundled)
- Locale-unabhängiger Download-Button (DE + EN)

## Anwendungsfall: Kinderbuch-Illustrationen
- Prompt-Dateien im Markdown-Format (`bild-prompts-v2.md`)
- Stil-Prefix + Charakter-Referenzen als Intro
- Goldene Regeln für konsistente Bild-KI-Ergebnisse
- Projekt "Agent Tatze" — Bände mit je ~18-20 Illustrationen
