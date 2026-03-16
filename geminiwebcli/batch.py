"""Batch prompt file parser for sequential image generation."""
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BatchPrompt:
    filename: str
    prompt: str
    note: str = ""


def parse_prompt_file(path: Path) -> tuple[str, list[BatchPrompt]]:
    """Parse a markdown prompt file.

    Expected format:
    - First code block = style prefix (prepended to every prompt)
    - ### filename.png headers followed by code blocks = individual prompts
    - Optional blockquote lines before a code block = notes

    Returns (style_prefix, list of BatchPrompt).
    """
    text = path.read_text()
    lines = text.split("\n")

    style_prefix = ""
    prompts: list[BatchPrompt] = []

    # Extract first code block as style prefix
    first_block = re.search(r"^```\w*\n(.*?)^```", text, re.MULTILINE | re.DOTALL)
    if first_block:
        style_prefix = first_block.group(1).strip()

    # Find all ### headers with filenames, then their code blocks
    current_filename = ""
    current_note = ""
    in_header_section = False

    i = 0
    while i < len(lines):
        line = lines[i]

        # Match ### headers with image filenames
        header_match = re.match(r"^###\s+(\S+\.(?:png|jpg|jpeg|webp))", line, re.IGNORECASE)
        if header_match:
            current_filename = header_match.group(1)
            current_note = ""
            in_header_section = True
            i += 1
            continue

        # Collect blockquote notes after header
        if in_header_section and line.startswith(">"):
            current_note = line.lstrip("> ").strip()
            i += 1
            continue

        # Match code block after a header
        if in_header_section and line.startswith("```"):
            # Read until closing ```
            block_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block_lines.append(lines[i])
                i += 1
            prompt_text = "\n".join(block_lines).strip()

            # Skip if this is the style prefix block (first one, no filename)
            if current_filename and prompt_text != style_prefix:
                prompts.append(BatchPrompt(
                    filename=current_filename,
                    prompt=prompt_text,
                    note=current_note,
                ))
            current_filename = ""
            current_note = ""
            in_header_section = False
            i += 1
            continue

        # Non-header ## lines reset state
        if line.startswith("## ") and not line.startswith("### "):
            in_header_section = False

        i += 1

    return style_prefix, prompts
