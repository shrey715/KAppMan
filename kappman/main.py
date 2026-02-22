"""
kappman.main
============
Command-line entry point for KAppMan.

This module is registered as the ``kappman`` console script in
``pyproject.toml``.  All heavy imports (PyQt6, watchdog) are deferred to
the individual branches so that ``--help`` and ``--list`` remain fast even
without a display server.

Modes
-----
kappman
    Launch the PyQt6 GUI (default when no flag is given).
kappman --watch [DIR]
    Run a headless watcher daemon.  If DIR is omitted the configured watch
    directory (``~/.config/kappman/config.ini``) is used.
kappman --integrate PATH
    Make a single AppImage executable and create its desktop entry, then exit.
kappman --remove PATH
    Remove the desktop entry for PATH, then exit.
kappman --list
    Print all KAppMan-managed applications and exit.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=logging.DEBUG if verbose else logging.INFO,
    )


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate mode.

    Parameters
    ----------
    argv:
        Argument list; defaults to ``sys.argv[1:]`` when ``None``.

    Returns
    -------
    int
        Exit code (0 on success, 1 on error).
    """
    parser = argparse.ArgumentParser(
        prog="kappman",
        description="KDE AppImage Manager — watch, integrate, and manage AppImages",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug-level logging")

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--watch", metavar="DIR", nargs="?",
        const=None,
        help="Run as a headless watcher daemon (omit DIR to use configured directory)",
    )
    group.add_argument(
        "--integrate", metavar="PATH",
        help="Integrate a single AppImage and exit",
    )
    group.add_argument(
        "--remove", metavar="PATH",
        help="Remove the desktop entry for an AppImage and exit",
    )
    group.add_argument(
        "--list", action="store_true",
        help="List all KAppMan-integrated applications and exit",
    )

    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    if args.watch is not None or (len(sys.argv) > 1 and "--watch" in sys.argv):
        from kappman.watcher import AppImageWatcher
        watch_dir = args.watch if args.watch else None
        watcher = AppImageWatcher(watch_dir)
        print(f"Watching: {watcher.watch_dir}  (Ctrl-C to stop)")
        watcher.run_forever()
        return 0

    if args.integrate:
        from kappman.core import integrate_appimage
        try:
            result = integrate_appimage(args.integrate)
            print(f"Integrated:   {result['app_name']}")
            print(f"Executable:   {result['exec_path']}")
            print(f"Desktop file: {result['desktop_path']}")
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.remove:
        from kappman.core import remove_appimage
        removed = remove_appimage(args.remove)
        if removed:
            print(f"Removed desktop entry for: {Path(args.remove).stem}")
        else:
            print("No matching desktop entry found.", file=sys.stderr)
            return 1
        return 0

    if args.list:
        from kappman.core import list_integrated
        apps = list_integrated()
        if not apps:
            print("No KAppMan-integrated applications found.")
            return 0
        print(f"{'Application':<30}  Source")
        print("-" * 70)
        for app in apps:
            print(f"{app['app_name']:<30}  {app['exec_path']}")
        return 0

    from kappman.gui import launch_gui
    launch_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
