"""
kappman.gui
===========
PyQt6 main window for KAppMan.

Layout
------
The window has three logical sections:

1. **Settings panel** (:class:`SettingsPanel`) — watch directory and theme
   selector, both editable inline with a browse button.
2. **Application list** — a :class:`~PyQt6.QtWidgets.QListWidget` that shows
   all AppImages currently tracked by KAppMan (identified by the
   ``X-KAppMan-Source`` key in their ``.desktop`` file).
3. **Action buttons** — integrate, add, remove, open folder, toggle watcher.

Threading
---------
The watcher runs in :class:`WatcherThread`, a :class:`~PyQt6.QtCore.QThread`
subclass.  Stopping the thread is done by calling
:meth:`AppImageWatcher.stop`, which sets a :class:`threading.Event` that
unblocks the ``run_forever`` loop immediately.  The GUI thread then calls
:meth:`QThread.wait` with a generous timeout so it never hangs indefinitely.

Theme system
------------
Themes are plain ``.qss`` files discovered at runtime from a user-configurable
directory (see :mod:`kappman.config`).  The active theme is applied to the
:class:`~PyQt6.QtWidgets.QApplication` instance so that all widgets update
simultaneously.  The selection is persisted between sessions.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kappman.config import (
    get_theme,
    get_themes_dir,
    get_watch_dir,
    list_themes,
    load_theme_stylesheet,
    set_theme,
    set_themes_dir,
    set_watch_dir,
)
from kappman.core import integrate_appimage, list_integrated, remove_appimage
from kappman.watcher import AppImageWatcher

logger = logging.getLogger(__name__)

_FALLBACK_STYLESHEET = "QMainWindow, QWidget { background-color: #1e1e2e; color: #cdd6f4; }"

_WATCHER_STOP_TIMEOUT_MS = 5_000


class WatcherThread(QThread):
    """Runs :class:`~kappman.watcher.AppImageWatcher` on a background thread.

    Signals
    -------
    status_changed(str):
        Emitted when the watcher starts, stops, or encounters an error.
    app_integrated():
        Emitted after each successful integration so the GUI can refresh its
        list without polling.
    """

    status_changed = pyqtSignal(str)
    app_integrated = pyqtSignal()

    def __init__(self, watch_dir: Path) -> None:
        super().__init__()
        self._watcher = AppImageWatcher(watch_dir)

    def run(self) -> None:
        self.status_changed.emit(f"Watching: {self._watcher.watch_dir}")
        self._watcher.run_forever()
        self.status_changed.emit("Watcher stopped")

    def stop(self) -> None:
        """Stop the watcher and block until the thread has exited.

        :meth:`AppImageWatcher.stop` sets the internal stop event which
        immediately unblocks ``run_forever``.  We then wait up to
        ``_WATCHER_STOP_TIMEOUT_MS`` for the thread to finish so the GUI
        remains responsive even if something unexpected delays shutdown.
        """
        self._watcher.stop()
        self.quit()
        if not self.wait(_WATCHER_STOP_TIMEOUT_MS):
            logger.warning("Watcher thread did not exit within timeout; forcing termination")
            self.terminate()
            self.wait()


class SettingsPanel(QWidget):
    """Inline settings row containing the watch directory and theme selector.

    Emits signals whenever either setting changes so the parent window can
    react (e.g. restart the watcher, reload the stylesheet) without polling.

    Signals
    -------
    watch_dir_changed(Path):
        Emitted after the watch directory is committed (Enter key or focus
        lost on the text field, or a directory selected via the dialog).
    theme_changed(str):
        Emitted when the user selects a different theme from the combo box.
    themes_dir_changed(Path):
        Emitted after the themes directory is changed so the parent can
        trigger a theme reload if needed.
    """

    watch_dir_changed = pyqtSignal(Path)
    theme_changed = pyqtSignal(str)
    themes_dir_changed = pyqtSignal(Path)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        wd_label = QLabel("Watch Directory")
        wd_label.setObjectName("sectionLabel")
        layout.addWidget(wd_label)

        wd_row = QHBoxLayout()
        wd_row.setSpacing(4)

        self.dir_edit = QLineEdit(str(get_watch_dir()))
        self.dir_edit.setPlaceholderText("~/AppImages")
        self.dir_edit.editingFinished.connect(self._on_watch_dir_edited)

        browse_wd = QToolButton()
        browse_wd.setText("...")
        browse_wd.setToolTip("Choose watch directory")
        browse_wd.clicked.connect(self._browse_watch_dir)

        wd_row.addWidget(self.dir_edit, stretch=1)
        wd_row.addWidget(browse_wd)
        layout.addLayout(wd_row)

        theme_row = QHBoxLayout()
        theme_row.setSpacing(4)

        theme_label = QLabel("Theme")
        theme_label.setObjectName("sectionLabel")
        theme_label.setFixedWidth(52)
        theme_row.addWidget(theme_label)

        self.theme_combo = QComboBox()
        self.theme_combo.setToolTip("Active theme (select a .qss file from the themes directory)")
        theme_row.addWidget(self.theme_combo, stretch=1)

        self.themes_dir_edit = QLineEdit(str(get_themes_dir()))
        self.themes_dir_edit.setToolTip("Directory scanned for .qss theme files")
        self.themes_dir_edit.editingFinished.connect(self._on_themes_dir_edited)
        theme_row.addWidget(self.themes_dir_edit, stretch=1)

        browse_td = QToolButton()
        browse_td.setText("...")
        browse_td.setToolTip("Choose themes directory")
        browse_td.clicked.connect(self._browse_themes_dir)
        theme_row.addWidget(browse_td)

        layout.addLayout(theme_row)

        self._populate_themes()
        self.theme_combo.currentTextChanged.connect(self._on_theme_selected)

    def _populate_themes(self) -> None:
        """Scan the current themes directory and repopulate the combo box."""
        themes_dir = Path(self.themes_dir_edit.text().strip()).expanduser()
        names = list_themes(themes_dir)
        current = get_theme()
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        self.theme_combo.addItems(names)
        idx = self.theme_combo.findText(current)
        self.theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.theme_combo.blockSignals(False)

    def watch_dir(self) -> Path:
        return Path(self.dir_edit.text().strip()).expanduser()

    def themes_dir(self) -> Path:
        return Path(self.themes_dir_edit.text().strip()).expanduser()

    def _on_watch_dir_edited(self) -> None:
        d = self.watch_dir()
        set_watch_dir(d)
        self.watch_dir_changed.emit(d)

    def _browse_watch_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Select Watch Directory", str(self.watch_dir())
        )
        if chosen:
            self.dir_edit.setText(chosen)
            self._on_watch_dir_edited()

    def _on_themes_dir_edited(self) -> None:
        d = self.themes_dir()
        set_themes_dir(d)
        self._populate_themes()
        self.themes_dir_changed.emit(d)

    def _browse_themes_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Select Themes Directory", str(self.themes_dir())
        )
        if chosen:
            self.themes_dir_edit.setText(chosen)
            self._on_themes_dir_edited()

    def _on_theme_selected(self, name: str) -> None:
        if name:
            set_theme(name)
            self.theme_changed.emit(name)


class KAppManWindow(QMainWindow):
    """The application's main window.

    Composes :class:`SettingsPanel`, the integrated-apps list, and the action
    button row.  Also owns the :class:`WatcherThread` lifecycle: starting it
    when the toggle button is checked and stopping it (via
    :meth:`WatcherThread.stop`) when unchecked or when the window closes.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("KAppMan – AppImage Manager")
        self.setMinimumSize(640, 560)
        self._watcher_thread: WatcherThread | None = None
        self._build_ui()
        self._refresh_list()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("KAppMan")
        title.setObjectName("titleLabel")
        subtitle = QLabel("KDE AppImage Manager")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignBottom)
        header.addWidget(title)
        header.addWidget(subtitle)
        header.addStretch()
        layout.addLayout(header)

        layout.addWidget(self._separator())

        self.settings = SettingsPanel()
        self.settings.watch_dir_changed.connect(self._on_watch_dir_changed)
        self.settings.theme_changed.connect(self._apply_theme)
        layout.addWidget(self.settings)

        layout.addWidget(self._separator())

        section = QLabel("Integrated Applications")
        section.setObjectName("sectionLabel")
        layout.addWidget(section)

        self.app_list = QListWidget()
        self.app_list.setAlternatingRowColors(True)
        layout.addWidget(self.app_list, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_integrate_all = QPushButton("Integrate All")
        self.btn_integrate_all.setObjectName("accentBtn")
        self.btn_integrate_all.setToolTip("Make all AppImages in the watch directory executable and register them")
        self.btn_integrate_all.clicked.connect(self._integrate_all)

        self.btn_add = QPushButton("Add File...")
        self.btn_add.setToolTip("Choose an AppImage to integrate")
        self.btn_add.clicked.connect(self._pick_and_integrate)

        self.btn_remove = QPushButton("Remove")
        self.btn_remove.setObjectName("dangerBtn")
        self.btn_remove.setToolTip("Remove the selected application from the KDE menu")
        self.btn_remove.clicked.connect(self._remove_selected)

        self.btn_open_dir = QPushButton("Open Folder")
        self.btn_open_dir.setToolTip("Open the watch directory in the file manager")
        self.btn_open_dir.clicked.connect(self._open_folder)

        self.btn_watch = QPushButton("Start Watcher")
        self.btn_watch.setCheckable(True)
        self.btn_watch.setToolTip("Monitor the watch directory and auto-integrate new AppImages")
        self.btn_watch.toggled.connect(self._toggle_watcher)

        for btn in (self.btn_integrate_all, self.btn_add, self.btn_remove,
                    self.btn_open_dir, self.btn_watch):
            btn_row.addWidget(btn)

        layout.addLayout(btn_row)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready")

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        return line

    def _apply_theme(self, theme_name: str) -> None:
        """Load and apply a theme by name from the configured themes directory."""
        css = load_theme_stylesheet(theme_name, self.settings.themes_dir())
        QApplication.instance().setStyleSheet(css or _FALLBACK_STYLESHEET)  # type: ignore[union-attr]
        self._status.showMessage(f"Theme applied: {theme_name}")

    def _on_watch_dir_changed(self, new_dir: Path) -> None:
        self._status.showMessage(f"Watch directory: {new_dir}")
        if self._watcher_thread and self._watcher_thread.isRunning():
            self.btn_watch.setChecked(False)
            self.btn_watch.setChecked(True)

    def _refresh_list(self) -> None:
        """Reload the integrated-apps list from disk."""
        self.app_list.clear()
        for entry in list_integrated():
            item = QListWidgetItem(f"  {entry['app_name']}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.app_list.addItem(item)
        count = self.app_list.count()
        self._status.showMessage(f"{count} app{'s' if count != 1 else ''} integrated")

    def _integrate_all(self) -> None:
        watch_dir = self.settings.watch_dir()
        watch_dir.mkdir(parents=True, exist_ok=True)
        appimages = list(watch_dir.glob("*.AppImage")) + list(watch_dir.glob("*.appimage"))
        if not appimages:
            QMessageBox.information(self, "Nothing to integrate",
                                    f"No AppImages found in:\n{watch_dir}")
            return
        ok, fail = 0, 0
        for p in appimages:
            try:
                integrate_appimage(p)
                ok += 1
            except Exception:
                logger.exception("Failed to integrate %s", p)
                fail += 1
        self._refresh_list()
        self._status.showMessage(
            f"{ok} integrated" + (f", {fail} failed" if fail else "")
        )

    def _pick_and_integrate(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select AppImage", str(Path.home()),
            "AppImage Files (*.AppImage *.appimage);;All Files (*)",
        )
        if not path:
            return
        try:
            result = integrate_appimage(path)
            self._refresh_list()
            self._status.showMessage(f"Integrated: {result['app_name']}")
        except Exception as exc:
            QMessageBox.critical(self, "Integration error", str(exc))

    def _remove_selected(self) -> None:
        item = self.app_list.currentItem()
        if not item:
            self._status.showMessage("No application selected")
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Confirm removal",
            f"Remove '{entry['app_name']}' from the KDE application menu?\n"
            "The AppImage file itself will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            remove_appimage(entry["exec_path"])
            self._refresh_list()
            self._status.showMessage(f"Removed: {entry['app_name']}")

    def _open_folder(self) -> None:
        d = self.settings.watch_dir()
        d.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(d)])

    def _toggle_watcher(self, checked: bool) -> None:
        if checked:
            self._watcher_thread = WatcherThread(self.settings.watch_dir())
            self._watcher_thread.status_changed.connect(self._status.showMessage)
            self._watcher_thread.app_integrated.connect(self._refresh_list)
            self._watcher_thread.start()
            self.btn_watch.setText("Stop Watcher")
        else:
            if self._watcher_thread:
                self.btn_watch.setEnabled(False)
                self._watcher_thread.stop()
                self._watcher_thread = None
                self.btn_watch.setEnabled(True)
            self.btn_watch.setText("Start Watcher")
            self._status.showMessage("Watcher stopped")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._watcher_thread:
            self._watcher_thread.stop()
        super().closeEvent(event)


def launch_gui() -> None:
    """Create the :class:`~PyQt6.QtWidgets.QApplication`, apply the persisted
    theme, and show the main window.  Blocks until the window is closed.
    """
    import sys

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("KAppMan")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("KAppMan")
    app.setStyleSheet(load_theme_stylesheet(get_theme()) or _FALLBACK_STYLESHEET)

    font = QFont("Inter")
    font.setPointSize(10)
    app.setFont(font)

    window = KAppManWindow()
    window.show()
    sys.exit(app.exec())
