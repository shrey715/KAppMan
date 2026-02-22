"""
kappman.config
==============
Persistent user configuration stored at ~/.config/kappman/config.ini.

Stores:
  - watch_dir  : directory to monitor for new AppImages (default: ~/AppImages)
  - theme      : name of the active .qss theme file without extension
                 (default: catppuccin_mocha)
  - themes_dir : directory scanned for .qss theme files
                 (default: the built-in kappman/themes/ package directory)
"""

from __future__ import annotations

import configparser
from pathlib import Path

_CONFIG_DIR = Path.home() / ".config" / "kappman"
_CONFIG_FILE = _CONFIG_DIR / "config.ini"

# Built-in themes bundled with the package
_BUILTIN_THEMES_DIR = Path(__file__).parent / "themes"

_SECTION = "kappman"
_DEFAULTS: dict[str, str] = {
    "watch_dir": str(Path.home() / "AppImages"),
    "theme": "catppuccin_mocha",
    "themes_dir": str(_BUILTIN_THEMES_DIR),
}


def _load() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg[_SECTION] = _DEFAULTS.copy()
    if _CONFIG_FILE.exists():
        cfg.read(_CONFIG_FILE, encoding="utf-8")
    return cfg


def _save(cfg: configparser.ConfigParser) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_FILE, "w", encoding="utf-8") as fh:
        cfg.write(fh)


# ── Watch directory ────────────────────────────────────────────────────────

def get_watch_dir() -> Path:
    return Path(_load()[_SECTION]["watch_dir"]).expanduser()


def set_watch_dir(directory: str | Path) -> None:
    cfg = _load()
    cfg[_SECTION]["watch_dir"] = str(Path(directory).expanduser().resolve())
    _save(cfg)


# ── Themes directory ───────────────────────────────────────────────────────

def get_themes_dir() -> Path:
    return Path(_load()[_SECTION]["themes_dir"]).expanduser()


def set_themes_dir(directory: str | Path) -> None:
    cfg = _load()
    cfg[_SECTION]["themes_dir"] = str(Path(directory).expanduser().resolve())
    _save(cfg)


def list_themes(themes_dir: Path | None = None) -> list[str]:
    """
    Return a sorted list of theme names (filename stems) found in *themes_dir*.
    Falls back to the built-in themes directory if none given.
    """
    d = themes_dir or get_themes_dir()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.qss"))


def load_theme_stylesheet(theme_name: str, themes_dir: Path | None = None) -> str:
    """
    Read and return the QSS content for *theme_name*.
    Looks in *themes_dir* first, then in the built-in themes directory.
    Returns an empty string if the file is not found.
    """
    dirs = []
    if themes_dir:
        dirs.append(Path(themes_dir))
    dirs.append(get_themes_dir())
    dirs.append(_BUILTIN_THEMES_DIR)

    for d in dirs:
        qss_file = d / f"{theme_name}.qss"
        if qss_file.exists():
            return qss_file.read_text(encoding="utf-8")
    return ""


# ── Active theme ───────────────────────────────────────────────────────────

def get_theme() -> str:
    return _load()[_SECTION]["theme"]


def set_theme(theme_name: str) -> None:
    cfg = _load()
    cfg[_SECTION]["theme"] = theme_name
    _save(cfg)
