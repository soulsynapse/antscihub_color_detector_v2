# gui/main_window.py (COMPLETE UPDATED VERSION)
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QSplitter, QFileDialog
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent, QKeySequence, QShortcut
from gui.video_panel import VideoPanel
from gui.right_panel import RightPanel
from core.color_store import ColorStore
from core.video_manager import VideoManager


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HSV Color Detector")
        self.setMinimumSize(1400, 800)
        self.resize(1600, 900)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.color_store = ColorStore()
        self.video_manager = VideoManager()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.video_panel = VideoPanel(self.video_manager, self.color_store)
        self.right_panel = RightPanel(self.video_manager, self.color_store)

        splitter.addWidget(self.video_panel)
        splitter.addWidget(self.right_panel)
        splitter.setSizes([800, 800])

        layout.addWidget(splitter)

        # Connect signals
        self.color_store.colors_changed.connect(self.right_panel.histogram_tab.update_histograms)
        self.color_store.colors_changed.connect(self.right_panel.histogram_tab.color_list_widget.refresh)
        self.color_store.bounds_changed.connect(self._on_bounds_changed)
        self.color_store.detection_settings_changed.connect(self._on_detection_settings_changed)
        self.video_manager.frame_changed.connect(self.video_panel.display_frame)

        # Jump to frame from search
        self.right_panel.histogram_tab.jump_to_frame.connect(self._jump_to_frame)

        # Update frame stats when scrubbing
        self.video_panel.scrubber.valueChanged.connect(
            lambda v: self.right_panel.histogram_tab._update_frame_stats()
        )

        self._shift_held = False
        self._setup_menu()
        self._setup_shortcuts()

    def _setup_menu(self):
        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        open_action = file_menu.addAction("Open Video")
        open_action.triggered.connect(self._open_video)

    def _setup_shortcuts(self):
        self.space_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space.value), self)
        self.space_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.space_shortcut.setAutoRepeat(False)
        self.space_shortcut.activated.connect(self.video_panel.toggle_playback)

    def _open_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Video", "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.wmv);;All Files (*)"
        )
        if path:
            self.video_manager.load_video(path)
            self.video_panel.on_video_loaded()
            self.right_panel.on_video_loaded()

    def _on_bounds_changed(self):
        self.video_panel.update_mask_overlay()
        self.video_panel.invalidate_detection_markers()
        self.right_panel.histogram_tab.update_histograms()
        self.right_panel.histogram_tab.color_list_widget.refresh()

    def _on_detection_settings_changed(self):
        self.video_panel.update_mask_overlay()
        self.video_panel.invalidate_detection_markers()
        self.right_panel.histogram_tab._update_frame_stats()

    def _jump_to_frame(self, frame_idx):
        self.video_panel.scrubber.setValue(frame_idx)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Shift and not self._shift_held:
            self._shift_held = True
            self._set_global_mask(True)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Shift and self._shift_held:
            self._shift_held = False
            self._set_global_mask(False)
        super().keyReleaseEvent(event)

    def _set_global_mask(self, masked: bool):
        self.video_panel.set_shift_mask(masked)
        self.right_panel.histogram_tab.set_shift_mask(masked)
