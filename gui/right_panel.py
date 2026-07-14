# gui/right_panel.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from core.color_store import ColorStore
from core.video_manager import VideoManager
from gui.histogram_tab import HistogramTab
from gui.analysis_tab import AnalysisTab


class RightPanel(QWidget):
    def __init__(self, video_manager: VideoManager, color_store: ColorStore):
        super().__init__()
        self.video_manager = video_manager
        self.color_store = color_store

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        self.tabs = QTabWidget()

        self.histogram_tab = HistogramTab(video_manager, color_store)
        self.analysis_tab = AnalysisTab(video_manager, color_store)

        self.tabs.addTab(self.histogram_tab, "Color Isolation")
        self.tabs.addTab(self.analysis_tab, "Full Video Analysis")

        layout.addWidget(self.tabs)

    def on_video_loaded(self):
        self.analysis_tab.on_video_loaded()