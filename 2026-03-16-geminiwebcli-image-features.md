# geminiwebcli — Bildgenerierungs-Features
Datum: 2026-03-16
Dauer: ~30 Turns

## Zusammenfassung
Umfangreiche Weiterentwicklung der Bildgenerierungs-Features in geminiwebcli. Batch-Modus für sequentielle Bildgenerierung aus Markdown-Prompt-Dateien (Kinderbuch-Illustrationen "Agent Tatze").

## Implementierte Features
1. `/image <prompt>` — Einzelbild generieren + speichern
2. `/batch <file.md>` — Batch-Bildgenerierung mit:
   - Intro-Context (Charaktere, Stil) in jeder Message (2-Step war fehlerhaft, jetzt single-message)
   - No-Text-Instruction (Gemini fügte sonst Namen unter Charaktere)
   - Progress-Tracking + Resume
   - Retry bei Fehlern
   - Ctrl+C graceful pause
   - Model-Switch pro Batch
   - Ref-Images pro Prompt
   - Bilder in Sub-Directories
3. `/ref <image>` — Referenzbild hochladen
4. `/gallery` — Bilder-Übersicht mit Größen
5. `/save-images` — Alle Bilder aus Chat-History extrahieren
6. `image_dir` in config.toml konfigurierbar
7. Locale-Fix Download-Button (DE + EN)
8. Refactoring: Image-Extraktion als wiederverwendbare Methoden

## Erkenntnisse
- Gemini ignoriert Chat-History-Context bei Bildgenerierung → alles in eine Message
- "No text" Instruction muss explizit und stark formuliert sein (CRITICAL: NO text...)
- Charakter-Namen in Markdown-Bold (`**Tobi**`) werden von Gemini als Labels ins Bild geschrieben

## Commits
- f9fe234: Initial commit
- 6e02ff2: Image extraction + Chromium discovery
- 48b918b: Project docs
- 972bb85: Batch + /image + upload
- a7916ad: Intro context per chat
- 6a90173: Sub-directory per batch
- a9994e2: Single-message statt 2-step
- 34faf52: No-text instruction
- e722074: /ref command
- 06a67a5: /save-images + history extraction
- e4ec088: Progress tracking + retry
- 30bbeb1: Gallery, Ctrl+C, --model, ref-images, image_dir config
