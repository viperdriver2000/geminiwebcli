# geminiwebcli — Git-Repo & lokales Setup
Datum: 2026-03-06
Dauer: ~12 Turns

## Zusammenfassung
Projekt von einem Kollegen (Gemini Web CLI — Playwright-basierte Browser-Automation für Google Gemini) als eigenes GitHub-Repo aufgesetzt und lokal lauffähig gemacht.

## Schritte
1. Alte Git-History entfernt (war vom Kollegen, Remote auf dessen Home-Server)
2. Frisches Git-Repo initialisiert, Initial Commit
3. GitHub-Repo `viperdriver2000/geminiwebcli` erstellt (public) und gepusht
4. Aktualisierte Version vom User eingepflegt (Image-Extraktion, Chromium-Discovery)
5. Windows Zone.Identifier-Dateien bereinigt, `.gitignore` ergänzt
6. pyenv installiert (war nicht vorhanden), Python 3.12.13 gebaut
   - Build-Dependencies mussten erst via apt nachinstalliert werden (libffi, libssl, etc.)
   - Debian Bullseye Repos veraltet → `apt-get update` nötig
7. venv erstellt, `pip install -e ".[bot]"`, Playwright Chromium installiert
8. `geminiwebcli --help` funktioniert

## Entscheidungen / Erkenntnisse
- pyenv statt System-Python, da WSL nur Python 3.9 hat, Projekt braucht >=3.11
- Classic PAT nötig für GitHub push (Fine-grained PAT kann nicht pushen)
- tkinter-Warning beim pyenv-Build ist egal (nicht benötigt)

## Relevante Dateien
- Projekt: `/home/viperdriver2000/tmp/geminiwebcli/`
- venv: `/home/viperdriver2000/tmp/geminiwebcli/.venv/`
- pyenv: `~/.pyenv/` mit Python 3.12.13
- GitHub: `https://github.com/viperdriver2000/geminiwebcli`
