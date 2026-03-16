"""Config file handling for geminiwebcli."""
import tomllib
from pathlib import Path
from dataclasses import dataclass, field, asdict

CONFIG_DIR = Path.home() / ".geminiwebcli"
CONFIG_FILE = CONFIG_DIR / "config.toml"
PROFILE_DIR = Path.home() / "snap" / "chromium" / "common" / "geminiwebcli"

DEFAULTS = {
    "profile_dir": str(PROFILE_DIR),
    "headless": False,
    "model": "gemini-2.0-flash",
    "image_dir": "gemini-images",
    "system_prompt": "IMPORTANT: Write all code, variable names, and comments in English. Write all explanations and prose in German. Be concise: do not add unsolicited commentary, explanations, or prose. Only do what is explicitly requested.",
    "telegram_token": "",
    "telegram_chat_id": "",
}


@dataclass
class Config:
    profile_dir: str = str(PROFILE_DIR)
    headless: bool = True
    model: str = "gemini-2.0-flash"
    image_dir: str = "gemini-images"
    system_prompt: str = DEFAULTS["system_prompt"]
    telegram_token: str = ""
    telegram_chat_id: str = ""
    run_commands: dict = field(default_factory=dict)

    @property
    def profile_path(self) -> Path:
        return Path(self.profile_dir).expanduser()

    @property
    def image_path(self) -> Path:
        p = Path(self.image_dir).expanduser()
        return p if p.is_absolute() else Path.cwd() / p


def load() -> Config:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        _write_defaults()
    with open(CONFIG_FILE, "rb") as f:
        data = tomllib.load(f)
    cfg = Config(**{k: data.get(k, v) for k, v in DEFAULTS.items()})
    cfg.run_commands = data.get("run", {})
    return cfg


def _write_defaults():
    lines = [
        f'profile_dir = "{DEFAULTS["profile_dir"]}"',
        f'headless = {str(DEFAULTS["headless"]).lower()}',
        f'model = "{DEFAULTS["model"]}"',
        f'image_dir = "{DEFAULTS["image_dir"]}"',
        f'system_prompt = "{DEFAULTS["system_prompt"]}"',
        f'# telegram_token = "1234:AAxx..."',
        f'# telegram_chat_id = "155463840"',
        f'',
        f'# Allowed commands for /run (key = alias, value = shell command):',
        f'# [run]',
        f'# test = "pytest"',
        f'# lint = "ruff check ."',
        f'# build = "make build"',
    ]
    CONFIG_FILE.write_text("\n".join(lines) + "\n")
