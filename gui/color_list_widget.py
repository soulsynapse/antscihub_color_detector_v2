# gui/color_list_widget.py
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QFileDialog
from core.color_store import ColorStore


class ColorListWidget(QWidget):
    def __init__(self, color_store: ColorStore):
        super().__init__()
        self.color_store = color_store

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        self.count_label = QLabel("0 colors picked (0 in bounds)")
        self.count_label.setStyleSheet("color: #aaa; font-family: monospace; font-size: 11px;")
        layout.addWidget(self.count_label)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-family: monospace; font-size: 10px;")
        layout.addWidget(self.status_label)

        layout.addStretch()

        save_btn = QPushButton("Save Settings")
        save_btn.setToolTip("Save bounds, picked colors, and detection settings to JSON")
        save_btn.setStyleSheet(
            "QPushButton { color: #aaddff; background: #2a2a2a; border: 1px solid #555; "
            "padding: 4px 10px; border-radius: 3px; }"
            "QPushButton:hover { background: #243846; }"
        )
        save_btn.clicked.connect(self._save_settings)
        layout.addWidget(save_btn)

        load_btn = QPushButton("Load Settings")
        load_btn.setToolTip("Load bounds, picked colors, and detection settings from JSON (replaces current)")
        load_btn.setStyleSheet(
            "QPushButton { color: #aaddff; background: #2a2a2a; border: 1px solid #555; "
            "padding: 4px 10px; border-radius: 3px; }"
            "QPushButton:hover { background: #243846; }"
        )
        load_btn.clicked.connect(self._load_settings)
        layout.addWidget(load_btn)

        clear_excluded_btn = QPushButton("Clear Excluded")
        clear_excluded_btn.setToolTip("Remove all colors that fall outside current bounds")
        clear_excluded_btn.setStyleSheet(
            "QPushButton { color: #ffcc66; background: #2a2a2a; border: 1px solid #555; "
            "padding: 4px 10px; border-radius: 3px; }"
            "QPushButton:hover { background: #3a3a22; }"
        )
        clear_excluded_btn.clicked.connect(self._clear_excluded)
        layout.addWidget(clear_excluded_btn)

        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.setStyleSheet(
            "QPushButton { color: #ff8888; background: #2a2a2a; border: 1px solid #555; "
            "padding: 4px 10px; border-radius: 3px; }"
            "QPushButton:hover { background: #442222; }"
        )
        clear_all_btn.clicked.connect(self.color_store.clear_colors)
        layout.addWidget(clear_all_btn)

    def _save_settings(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Color Settings",
            "color_settings.json",
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        ok, message = self.color_store.save_settings(path)
        self._show_status(ok, message)

    def _load_settings(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Color Settings",
            "",
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        ok, message = self.color_store.load_settings(path)
        self._show_status(ok, message)

    def _show_status(self, ok: bool, message: str):
        color = "#66cc66" if ok else "#ff8888"
        self.status_label.setStyleSheet(f"color: {color}; font-family: monospace; font-size: 10px;")
        self.status_label.setText(message)

    def _clear_excluded(self):
        colors = self.color_store.get_all_colors()
        to_remove = []
        for i, c in enumerate(colors):
            if not self.color_store.is_color_in_bounds(c):
                to_remove.append(i)
        for i in reversed(to_remove):
            self.color_store._colors.pop(i)
        if to_remove:
            self.color_store.colors_changed.emit()

    def refresh(self):
        colors = self.color_store.get_all_colors()
        in_count = sum(1 for c in colors if self.color_store.is_color_in_bounds(c))
        total = len(colors)
        self.count_label.setText(f"{total} colors picked ({in_count} in bounds)")
