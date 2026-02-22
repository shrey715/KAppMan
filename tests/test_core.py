"""Tests for kappman.core"""

import os
import stat
from pathlib import Path

import pytest

from kappman.core import (
    APPLICATIONS_DIR,
    integrate_appimage,
    list_integrated,
    remove_appimage,
)


@pytest.fixture()
def dummy_appimage(tmp_path: Path) -> Path:
    """Create a fake AppImage file in a temp directory."""
    p = tmp_path / "MyTestApp.AppImage"
    p.write_text("#!/bin/sh\necho hello\n")
    return p


def test_integrate_makes_executable(dummy_appimage: Path) -> None:
    integrate_appimage(dummy_appimage)
    assert os.access(dummy_appimage, os.X_OK), "AppImage should be executable"


def test_integrate_creates_desktop_entry(dummy_appimage: Path) -> None:
    result = integrate_appimage(dummy_appimage)
    dp = Path(result["desktop_path"])
    assert dp.exists(), f"Desktop entry should exist at {dp}"
    content = dp.read_text()
    assert "Name=MyTestApp" in content
    assert str(dummy_appimage) in content
    assert "X-KAppMan-Source=" in content


def test_integrate_returns_correct_dict(dummy_appimage: Path) -> None:
    result = integrate_appimage(dummy_appimage)
    assert result["app_name"] == "MyTestApp"
    assert result["exec_path"] == str(dummy_appimage)


def test_remove_deletes_desktop_entry(dummy_appimage: Path) -> None:
    result = integrate_appimage(dummy_appimage)
    dp = Path(result["desktop_path"])
    assert dp.exists()

    removed = remove_appimage(dummy_appimage)
    assert removed is True
    assert not dp.exists(), "Desktop entry should be deleted after removal"


def test_remove_returns_false_when_not_found(tmp_path: Path) -> None:
    ghost = tmp_path / "NonExistentApp.AppImage"
    removed = remove_appimage(ghost)
    assert removed is False


def test_list_integrated_includes_integrated_app(dummy_appimage: Path) -> None:
    integrate_appimage(dummy_appimage)
    apps = list_integrated()
    names = [a["app_name"] for a in apps]
    assert "MyTestApp" in names


def test_list_integrated_excludes_non_kappman_entries() -> None:
    """Desktop entries without X-KAppMan-Source should not appear."""
    apps = list_integrated()
    for a in apps:
        dp = Path(a["desktop_path"])
        assert "X-KAppMan-Source=" in dp.read_text()


def test_integrate_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        integrate_appimage("/tmp/definitely_does_not_exist.AppImage")


def test_appimage_suffix_stripped() -> None:
    """Both .AppImage and .appimage suffixes should be stripped."""
    from kappman.core import _sanitize_name
    assert _sanitize_name(Path("Foo.AppImage")) == "Foo"
    assert _sanitize_name(Path("foo.appimage")) == "foo"
    assert _sanitize_name(Path("NoSuffix")) == "NoSuffix"
