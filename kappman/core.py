"""
kappman.core
============
Core logic for AppImage integration and removal.

Responsibilities
----------------
- Make an AppImage executable (``chmod +x``).
- Write an XDG-compliant ``.desktop`` entry to
  ``~/.local/share/applications/`` so the application appears in the KDE
  (and any other XDG-conformant) application menu.
- Optionally extract an icon from the AppImage via ``unsquashfs``.
- Remove a previously created ``.desktop`` entry.
- List all AppImages currently managed by KAppMan (identified by the
  ``X-KAppMan-Source`` key injected into every entry we create).

All public functions raise :class:`FileNotFoundError` when given a path that
does not exist and return plain dicts or booleans so that callers (GUI,
watcher, CLI) can present output in whatever way is appropriate for their
context.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

APPLICATIONS_DIR = Path.home() / ".local" / "share" / "applications"
ICONS_DIR = Path.home() / ".local" / "share" / "icons" / "kappman"


def _ensure_dirs() -> None:
    APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
    ICONS_DIR.mkdir(parents=True, exist_ok=True)


def _desktop_path(app_name: str) -> Path:
    return APPLICATIONS_DIR / f"{app_name}.desktop"


def _sanitize_name(file_path: Path) -> str:
    """Return a display name by stripping the ``.AppImage`` / ``.appimage`` suffix."""
    name = file_path.name
    for suffix in (".AppImage", ".appimage"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _extract_icon(appimage_path: Path, app_name: str) -> Path | None:
    """Attempt to extract an icon from *appimage_path* using ``unsquashfs``.

    The extraction is best-effort.  If ``unsquashfs`` is not installed, or if
    the AppImage does not contain a recognisable icon, ``None`` is returned and
    the caller falls back to a generic system icon.

    Parameters
    ----------
    appimage_path:
        Absolute path to the AppImage file.
    app_name:
        Sanitised application name used to name the extracted icon file.

    Returns
    -------
    Path | None
        Absolute path to the extracted icon, or ``None`` on failure.
    """
    if not shutil.which("unsquashfs"):
        logger.debug("unsquashfs not found — skipping icon extraction")
        return None

    try:
        with tempfile.TemporaryDirectory(prefix="kappman_") as tmpdir:
            subprocess.run(
                [
                    "unsquashfs", "-n", "-i",
                    "-d", f"{tmpdir}/squash",
                    str(appimage_path),
                    "*.png", "*.svg", "*.DirIcon",
                ],
                capture_output=True,
                timeout=15,
            )
            squash_root = Path(tmpdir) / "squash"
            for pattern in ("*.png", "*.svg", ".DirIcon"):
                candidates = sorted(squash_root.rglob(pattern))
                if candidates:
                    src = candidates[0]
                    dest = ICONS_DIR / f"{app_name}{src.suffix}"
                    shutil.copy2(src, dest)
                    logger.info("Extracted icon: %s", dest)
                    return dest
    except Exception:
        logger.debug("Icon extraction failed for %s", appimage_path, exc_info=True)

    return None


def integrate_appimage(file_path: str | Path) -> dict:
    """Make *file_path* executable and register it in the application menu.

    Steps performed:

    1. Resolve the absolute path and verify the file exists.
    2. Set the executable bit (equivalent to ``chmod +x``).
    3. Attempt icon extraction via :func:`_extract_icon`.
    4. Write a ``.desktop`` entry to :data:`APPLICATIONS_DIR`.

    Parameters
    ----------
    file_path:
        Path to the AppImage, accepts ``~`` expansion.

    Returns
    -------
    dict
        A dict with keys ``app_name``, ``exec_path``, ``desktop_path``, and
        ``icon_path`` (``None`` if no icon could be extracted).

    Raises
    ------
    FileNotFoundError
        If *file_path* does not exist.
    """
    _ensure_dirs()

    path = Path(os.path.abspath(os.path.expanduser(file_path)))
    if not path.exists():
        raise FileNotFoundError(f"AppImage not found: {path}")

    current_mode = path.stat().st_mode
    path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    logger.info("Made executable: %s", path)

    app_name = _sanitize_name(path)
    icon_path = _extract_icon(path, app_name)
    icon_value = str(icon_path) if icon_path else "application-x-executable"

    desktop_content = (
        "[Desktop Entry]\n"
        f"Name={app_name}\n"
        f"Exec={path}\n"
        f"Icon={icon_value}\n"
        "Type=Application\n"
        "Categories=Utility;\n"
        "Terminal=false\n"
        "StartupNotify=true\n"
        f"Comment=AppImage managed by KAppMan\n"
        f"X-KAppMan-Source={path}\n"
    )

    dp = _desktop_path(app_name)
    dp.write_text(desktop_content, encoding="utf-8")
    logger.info("Desktop entry written: %s", dp)

    return {
        "app_name": app_name,
        "exec_path": str(path),
        "desktop_path": str(dp),
        "icon_path": str(icon_path) if icon_path else None,
    }


def remove_appimage(file_path: str | Path) -> bool:
    """Remove the ``.desktop`` entry associated with *file_path*.

    The AppImage file itself is **not** deleted.

    Parameters
    ----------
    file_path:
        Path to the AppImage whose desktop entry should be removed.

    Returns
    -------
    bool
        ``True`` if a desktop entry was found and deleted; ``False`` if no
        matching entry existed.
    """
    path = Path(os.path.abspath(os.path.expanduser(file_path)))
    app_name = _sanitize_name(path)
    dp = _desktop_path(app_name)

    if not dp.exists():
        logger.warning("Desktop entry not found for %s", app_name)
        return False

    dp.unlink()
    logger.info("Removed desktop entry: %s", dp)

    for suffix in (".png", ".svg", ""):
        icon = ICONS_DIR / f"{app_name}{suffix}"
        if icon.exists():
            icon.unlink()
            logger.info("Removed icon: %s", icon)
            break

    return True


def list_integrated() -> list[dict]:
    """Return a list of all AppImages currently managed by KAppMan.

    Only ``.desktop`` files that contain the ``X-KAppMan-Source`` marker key
    are included.  This prevents KAppMan from claiming ownership of desktop
    entries created by other tools.

    Returns
    -------
    list[dict]
        Each item has keys ``app_name``, ``exec_path``, and ``desktop_path``.
    """
    if not APPLICATIONS_DIR.exists():
        return []

    results = []
    for desktop_file in sorted(APPLICATIONS_DIR.glob("*.desktop")):
        content = desktop_file.read_text(encoding="utf-8", errors="ignore")
        if "X-KAppMan-Source=" not in content:
            continue
        exec_path = ""
        for line in content.splitlines():
            if line.startswith("X-KAppMan-Source="):
                exec_path = line.split("=", 1)[1]
                break
        results.append({
            "app_name": desktop_file.stem,
            "exec_path": exec_path,
            "desktop_path": str(desktop_file),
        })
    return results
