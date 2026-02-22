"""Tests for kappman.config"""

from pathlib import Path

import pytest

from kappman import config as cfg_mod


def test_get_watch_dir_returns_path() -> None:
    d = cfg_mod.get_watch_dir()
    assert isinstance(d, Path)


def test_list_themes_returns_builtin_themes() -> None:
    builtin = cfg_mod._BUILTIN_THEMES_DIR
    themes = cfg_mod.list_themes(builtin)
    assert "catppuccin_mocha" in themes
    assert "catppuccin_latte" in themes
    assert "breeze_dark" in themes


def test_load_theme_stylesheet_nonempty() -> None:
    css = cfg_mod.load_theme_stylesheet(
        "catppuccin_mocha", cfg_mod._BUILTIN_THEMES_DIR
    )
    assert len(css) > 0
    assert "background-color" in css


def test_load_theme_stylesheet_unknown_returns_empty() -> None:
    css = cfg_mod.load_theme_stylesheet("nonexistent_theme_xyz")
    assert css == ""


def test_list_themes_empty_dir(tmp_path: Path) -> None:
    assert cfg_mod.list_themes(tmp_path) == []


def test_list_themes_custom_dir(tmp_path: Path) -> None:
    (tmp_path / "my_theme.qss").write_text("QWidget { color: red; }")
    themes = cfg_mod.list_themes(tmp_path)
    assert "my_theme" in themes
