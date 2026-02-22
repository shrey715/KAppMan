# KAppMan – KDE AppImage Manager

> A lightweight, KDE-native AppImage manager built with Python + PyQt6.

## Features

- **Auto-integrate** AppImages from any directory you choose
- **Desktop entries** auto-generated in `~/.local/share/applications/` (XDG compliant)
- **Folder watcher** — drop an AppImage and it's integrated instantly
- **Configurable watch directory** — set it from the GUI or CLI
- **Live theme switching** — pick any `.qss` file from a directory; ships with four themes:
  - Catppuccin Mocha (default)
  - Catppuccin Macchiato
  - Catppuccin Latte
  - Breeze Dark
- **Custom themes** — drop your own `.qss` into the themes directory and it appears in the selector instantly

---

## Install

```bash
# Requires uv — https://docs.astral.sh/uv/
git clone https://github.com/you/KAppMan
cd KAppMan
uv sync
```

---

## Usage

```bash
# Launch the GUI (default)
uv run kappman

# Headless folder watcher (default dir: ~/AppImages)
uv run kappman --watch

# Watch a custom directory
uv run kappman --watch /mnt/storage/Apps

# One-shot: integrate a single AppImage
uv run kappman --integrate ~/Downloads/MyApp.AppImage

# Remove a desktop entry
uv run kappman --remove ~/AppImages/MyApp.AppImage

# List all KAppMan-integrated apps
uv run kappman --list
```

---

## Adding Themes

1. Create a `.qss` file (standard Qt stylesheet syntax)
2. Drop it into `kappman/themes/` **or** any custom directory
3. In the GUI, point the **Themes Directory** field to your folder
4. Select your theme from the dropdown — applied instantly, no restart needed

Your theme choice and directory are persisted to `~/.config/kappman/config.ini`.

---

## KDE Autostart

To auto-run the watcher on every login:

```bash
cp kappman/autostart/kappman-watcher.desktop ~/.config/autostart/
```

---

## Development

```bash
uv sync
uv run pytest tests/ -v
```

---

## License

MIT

---

## Disclaimer

This project was built with the assistance of AI (Google Deepmind's Antigravity). The code has been reviewed and is maintained by the author.
