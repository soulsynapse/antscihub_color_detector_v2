from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                              QSizePolicy, QLabel, QPushButton, QSlider,
                              QSpinBox, QFrame, QGroupBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
import cv2
import numpy as np
from core.color_store import ColorStore
from core.video_manager import VideoManager
from core.mask_builder import build_mask
from gui.histogram_widget import HistogramWidget
from gui.color_list_widget import ColorListWidget


class FrameSearchWorker(QThread):
    found = pyqtSignal(int)
    not_found = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, video_path, bounds, default_bounds, min_area,
                 merge_distance, condition, num_samples=200, start_frame=0):
        super().__init__()
        self.video_path = video_path
        self.bounds = bounds
        self.default_bounds = default_bounds
        self.min_area = min_area
        self.merge_distance = merge_distance
        self.condition = condition
        self.num_samples = num_samples
        self.start_frame = start_frame
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        from core.contour_utils import find_valid_contours

        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            self.not_found.emit("Could not open video")
            return

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30.0

        step = max(1, total // self.num_samples)
        indices = []
        idx = self.start_frame
        while idx < total:
            indices.append(idx)
            idx += step
        idx = 0
        while idx < self.start_frame and len(indices) < self.num_samples:
            indices.append(idx)
            idx += step

        best_frame = -1
        best_count = -1

        for i, frame_idx in enumerate(indices):
            if self._cancelled:
                cap.release()
                return

            cap.set(cv2.CAP_PROP_POS_MSEC, frame_idx * 1000.0 / fps)
            ret, frame = cap.read()
            if not ret:
                continue

            mask = build_mask(frame, self.bounds, self.default_bounds)
            valid = find_valid_contours(mask, self.min_area, self.merge_distance)
            count = len(valid)

            if self.condition == 'doubles' and count == 2:
                cap.release()
                self.found.emit(frame_idx)
                return
            elif self.condition == 'zero' and count == 0:
                cap.release()
                self.found.emit(frame_idx)
                return
            elif self.condition == 'many' and count >= 5:
                cap.release()
                self.found.emit(frame_idx)
                return
            elif self.condition == 'single' and count == 1:
                cap.release()
                self.found.emit(frame_idx)
                return
            elif self.condition == 'max':
                if count > best_count:
                    best_count = count
                    best_frame = frame_idx

            self.progress.emit(int(100 * (i + 1) / len(indices)))

        cap.release()

        if self.condition == 'max' and best_frame >= 0:
            self.found.emit(best_frame)
        else:
            labels = {
                'doubles': 'frame with exactly 2 detections',
                'zero': 'frame with 0 detections',
                'many': 'frame with 5+ detections',
                'single': 'frame with exactly 1 detection',
            }
            self.not_found.emit(f"No {labels.get(self.condition, 'matching frame')} found")


class HistogramTab(QWidget):
    jump_to_frame = pyqtSignal(int)

    def __init__(self, video_manager: VideoManager, color_store: ColorStore):
        super().__init__()
        self.video_manager = video_manager
        self.color_store = color_store
        self.search_worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        self.hint_label = QLabel("Hold SHIFT to hide out-of-bounds colors and show video mask")
        self.hint_label.setStyleSheet(
            "color: #666; font-size: 10px; font-style: italic; padding: 2px;"
        )
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.hint_label)

        # ── HSV Histograms ──
        hist_widget = QWidget()
        hist_layout = QGridLayout(hist_widget)
        hist_layout.setContentsMargins(2, 2, 2, 2)
        hist_layout.setSpacing(4)

        self.hist_widgets = {}
        configs = [
            ('H', 'S', (0, 179), (0, 255), 0, 0),
            ('H', 'V', (0, 179), (0, 255), 0, 1),
            ('S', 'V', (0, 255), (0, 255), 0, 2),
        ]
        for x_name, y_name, x_range, y_range, row, col in configs:
            hw = HistogramWidget(
                x_name, y_name, x_range, y_range, self.color_store
            )
            hw.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            hw.setMinimumSize(180, 140)
            hist_layout.addWidget(hw, row, col)
            self.hist_widgets[(x_name, y_name)] = hw

        layout.addWidget(hist_widget, 1)

        # ── Refinement Tools ──
        tools_group = QGroupBox("Refinement Tools")
        tools_group.setStyleSheet(
            "QGroupBox { color: #aaa; border: 1px solid #444; border-radius: 4px; "
            "margin-top: 8px; padding-top: 14px; font-weight: bold; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
        )
        tools_layout = QVBoxLayout(tools_group)
        tools_layout.setContentsMargins(8, 8, 8, 8)
        tools_layout.setSpacing(6)

        # ── Min area slider ──
        area_row = QHBoxLayout()
        area_label = QLabel("Min area (px):")
        area_label.setStyleSheet("color: #aaa; font-size: 11px;")
        area_label.setFixedWidth(85)
        area_row.addWidget(area_label)

        self.area_spinbox = QSpinBox()
        self.area_spinbox.setRange(1, 50000)
        self.area_spinbox.setValue(self.color_store.min_area)
        self.area_spinbox.setSingleStep(10)
        self.area_spinbox.setStyleSheet(
            "QSpinBox { background: #2a2a2a; color: #ccc; border: 1px solid #555; "
            "padding: 3px; border-radius: 3px; min-width: 70px; }"
        )
        self.area_spinbox.valueChanged.connect(self._on_min_area_changed)
        area_row.addWidget(self.area_spinbox)

        self.area_slider = QSlider(Qt.Orientation.Horizontal)
        self.area_slider.setRange(1, 5000)
        self.area_slider.setValue(min(self.color_store.min_area, self.area_slider.maximum()))
        self.area_slider.setStyleSheet(
            "QSlider::groove:horizontal { background: #333; height: 6px; border-radius: 3px; }"
            "QSlider::handle:horizontal { background: #aaa; width: 12px; margin: -4px 0; border-radius: 6px; }"
            "QSlider::sub-page:horizontal { background: #5a5a8a; border-radius: 3px; }"
        )
        self.area_slider.valueChanged.connect(self._on_area_slider_changed)
        area_row.addWidget(self.area_slider, 1)
        tools_layout.addLayout(area_row)

        # ── Merge distance slider ──
        merge_row = QHBoxLayout()
        merge_label = QLabel("Merge dist (px):")
        merge_label.setStyleSheet("color: #aaa; font-size: 11px;")
        merge_label.setFixedWidth(85)
        merge_label.setToolTip("Merge detections whose centers are within this distance")
        merge_row.addWidget(merge_label)

        self.merge_spinbox = QSpinBox()
        self.merge_spinbox.setRange(0, 1000)
        self.merge_spinbox.setValue(self.color_store.merge_distance)
        self.merge_spinbox.setSingleStep(5)
        self.merge_spinbox.setToolTip("0 = no merging")
        self.merge_spinbox.setStyleSheet(
            "QSpinBox { background: #2a2a2a; color: #ccc; border: 1px solid #555; "
            "padding: 3px; border-radius: 3px; min-width: 70px; }"
        )
        self.merge_spinbox.valueChanged.connect(self._on_merge_spinbox_changed)
        merge_row.addWidget(self.merge_spinbox)

        self.merge_slider = QSlider(Qt.Orientation.Horizontal)
        self.merge_slider.setRange(0, 500)
        self.merge_slider.setValue(min(self.color_store.merge_distance, self.merge_slider.maximum()))
        self.merge_slider.setStyleSheet(
            "QSlider::groove:horizontal { background: #333; height: 6px; border-radius: 3px; }"
            "QSlider::handle:horizontal { background: #aaa; width: 12px; margin: -4px 0; border-radius: 6px; }"
            "QSlider::sub-page:horizontal { background: #8a5a5a; border-radius: 3px; }"
        )
        self.merge_slider.valueChanged.connect(self._on_merge_slider_changed)
        merge_row.addWidget(self.merge_slider, 1)
        tools_layout.addLayout(merge_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #444;")
        tools_layout.addWidget(sep)

        # ── Frame search buttons ──
        search_label = QLabel("Find frames by detection count:")
        search_label.setStyleSheet("color: #aaa; font-size: 11px;")
        tools_layout.addWidget(search_label)

        btn_style = (
            "QPushButton { background: #2a2a2a; color: #aaa; border: 1px solid #555; "
            "padding: 5px 8px; border-radius: 3px; }"
            "QPushButton:hover { background: #3a3a3a; color: #fff; }"
            "QPushButton:disabled { background: #222; color: #555; }"
        )

        btn_row1 = QHBoxLayout()

        self.find_zero_btn = QPushButton("0 detections")
        self.find_zero_btn.setToolTip("Find frame with no detections (missed tracking)")
        self.find_zero_btn.setStyleSheet(btn_style)
        self.find_zero_btn.clicked.connect(lambda: self._start_search('zero'))
        btn_row1.addWidget(self.find_zero_btn)

        self.find_single_btn = QPushButton("Exactly 1")
        self.find_single_btn.setToolTip("Find frame with exactly 1 detection (ideal)")
        self.find_single_btn.setStyleSheet(btn_style)
        self.find_single_btn.clicked.connect(lambda: self._start_search('single'))
        btn_row1.addWidget(self.find_single_btn)

        self.find_doubles_btn = QPushButton("Exactly 2")
        self.find_doubles_btn.setToolTip("Find frame with exactly 2 detections")
        self.find_doubles_btn.setStyleSheet(btn_style)
        self.find_doubles_btn.clicked.connect(lambda: self._start_search('doubles'))
        btn_row1.addWidget(self.find_doubles_btn)

        tools_layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()

        self.find_many_btn = QPushButton("5+ detections")
        self.find_many_btn.setToolTip("Find frame with many detections (likely false positives)")
        self.find_many_btn.setStyleSheet(btn_style)
        self.find_many_btn.clicked.connect(lambda: self._start_search('many'))
        btn_row2.addWidget(self.find_many_btn)

        self.find_max_btn = QPushButton("Most detections")
        self.find_max_btn.setToolTip("Find the frame with the highest detection count")
        self.find_max_btn.setStyleSheet(btn_style)
        self.find_max_btn.clicked.connect(lambda: self._start_search('max'))
        btn_row2.addWidget(self.find_max_btn)

        self.find_next_btn = QPushButton("Find next →")
        self.find_next_btn.setToolTip("Search again from current frame")
        self.find_next_btn.setStyleSheet(
            "QPushButton { background: #2a3a4a; color: #aaddff; border: 1px solid #4a6a8a; "
            "padding: 5px 8px; border-radius: 3px; }"
            "QPushButton:hover { background: #3a4a5a; color: #fff; }"
            "QPushButton:disabled { background: #222; color: #555; }"
        )
        self.find_next_btn.setEnabled(False)
        self.find_next_btn.clicked.connect(self._find_next)
        btn_row2.addWidget(self.find_next_btn)

        tools_layout.addLayout(btn_row2)

        # Search status
        self.search_status = QLabel("")
        self.search_status.setStyleSheet(
            "color: #888; font-family: monospace; font-size: 10px; padding: 2px;"
        )
        tools_layout.addWidget(self.search_status)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #444;")
        tools_layout.addWidget(sep2)

        # Current frame quick stats
        self.frame_stats_label = QLabel("Scrub video to see detection stats")
        self.frame_stats_label.setStyleSheet(
            "color: #aaa; background: #1a1a1a; padding: 6px; border: 1px solid #333; "
            "border-radius: 3px; font-family: monospace; font-size: 11px;"
        )
        self.frame_stats_label.setWordWrap(True)
        tools_layout.addWidget(self.frame_stats_label)

        layout.addWidget(tools_group)

        # ── Color controls bar ──
        self.color_list_widget = ColorListWidget(self.color_store)
        layout.addWidget(self.color_list_widget)

        self._last_search_type = None

    # ── Slider callbacks ──

    def _on_min_area_changed(self, value):
        self.area_slider.blockSignals(True)
        self.area_slider.setValue(min(value, self.area_slider.maximum()))
        self.area_slider.blockSignals(False)
        self.color_store.min_area = value
        self._update_frame_stats()

    def _on_area_slider_changed(self, value):
        self.area_spinbox.blockSignals(True)
        self.area_spinbox.setValue(value)
        self.area_spinbox.blockSignals(False)
        self.color_store.min_area = value
        self._update_frame_stats()

    def _on_merge_spinbox_changed(self, value):
        self.merge_slider.blockSignals(True)
        self.merge_slider.setValue(min(value, self.merge_slider.maximum()))
        self.merge_slider.blockSignals(False)
        self.color_store.merge_distance = value
        self._update_frame_stats()

    def _on_merge_slider_changed(self, value):
        self.merge_spinbox.blockSignals(True)
        self.merge_spinbox.setValue(value)
        self.merge_spinbox.blockSignals(False)
        self.color_store.merge_distance = value
        self._update_frame_stats()

    def sync_detection_controls(self):
        # Spinboxes drive their sliders and write back to the store (a no-op when equal).
        self.area_spinbox.setValue(self.color_store.min_area)
        self.merge_spinbox.setValue(self.color_store.merge_distance)

    # ── Search ──

    def _start_search(self, condition):
        if not self.video_manager.is_loaded():
            self.search_status.setText("No video loaded")
            return
        if not self.color_store.has_any_bounds():
            self.search_status.setText("Set color bounds first")
            return

        self._last_search_type = condition
        self._set_search_buttons_enabled(False)
        self.search_status.setText(f"Searching for '{condition}'...")

        start = self.video_manager.current_frame_idx + 1
        if start >= self.video_manager.total_frames:
            start = 0

        self.search_worker = FrameSearchWorker(
            self.video_manager.video_path,
            self.color_store.get_bounds(),
            self.color_store.DEFAULT_BOUNDS,
            self.color_store.min_area,
            self.color_store.merge_distance,
            condition,
            num_samples=200,
            start_frame=start,
        )
        self.search_worker.found.connect(self._on_search_found)
        self.search_worker.not_found.connect(self._on_search_not_found)
        self.search_worker.progress.connect(self._on_search_progress)
        self.search_worker.start()

    def _find_next(self):
        if self._last_search_type:
            self._start_search(self._last_search_type)

    def _on_search_progress(self, pct):
        self.search_status.setText(f"Searching for '{self._last_search_type}'... {pct}%")

    def _on_search_found(self, frame_idx):
        self._set_search_buttons_enabled(True)
        self.find_next_btn.setEnabled(True)
        self.search_status.setText(
            f"Found '{self._last_search_type}' at frame {frame_idx}"
        )
        self.jump_to_frame.emit(frame_idx)

    def _on_search_not_found(self, message):
        self._set_search_buttons_enabled(True)
        self.search_status.setText(message)

    def _set_search_buttons_enabled(self, enabled):
        self.find_zero_btn.setEnabled(enabled)
        self.find_single_btn.setEnabled(enabled)
        self.find_doubles_btn.setEnabled(enabled)
        self.find_many_btn.setEnabled(enabled)
        self.find_max_btn.setEnabled(enabled)
        self.find_next_btn.setEnabled(enabled and self._last_search_type is not None)

    def _update_frame_stats(self):
        if not self.video_manager.is_loaded() or not self.color_store.has_any_bounds():
            return

        from core.contour_utils import find_valid_contours

        frame = self.video_manager.get_current_frame()
        if frame is None:
            return

        bounds = self.color_store.get_bounds()
        default_bounds = self.color_store.DEFAULT_BOUNDS
        mask = build_mask(frame, bounds, default_bounds)

        valid = find_valid_contours(mask, self.color_store.min_area,
                                     self.color_store.merge_distance)

        mask_px = int(np.sum(mask > 0))
        total_px = mask.shape[0] * mask.shape[1]
        coverage = 100.0 * mask_px / total_px

        text = f"Frame {self.video_manager.current_frame_idx}: "
        text += f"{len(valid)} detections | {mask_px} mask px ({coverage:.2f}%)"

        if self.color_store.merge_distance > 0:
            text += f" | merge: {self.color_store.merge_distance}px"

        if valid:
            areas = sorted([cv2.contourArea(c) for c in valid], reverse=True)
            text += f"\nAreas: {', '.join(f'{a:.0f}' for a in areas[:8])}"
            if len(areas) > 8:
                text += f" ... +{len(areas) - 8} more"

        self.frame_stats_label.setText(text)

    # ── Shift mask ──

    def set_shift_mask(self, masked: bool):
        for hw in self.hist_widgets.values():
            hw.show_masked = masked
            hw.update()
        if masked:
            self.hint_label.setText("SHIFT held — showing only in-bounds colors | video masked")
            self.hint_label.setStyleSheet(
                "color: #aaa; font-size: 10px; font-weight: bold; "
                "padding: 2px; background: #2a2a2a; border: 1px solid #555;"
            )
        else:
            self.hint_label.setText("Hold SHIFT to hide out-of-bounds colors and show video mask")
            self.hint_label.setStyleSheet(
                "color: #666; font-size: 10px; font-style: italic; padding: 2px;"
            )

    def update_histograms(self):
        colors = self.color_store.get_all_colors()
        for key, hw in self.hist_widgets.items():
            hw.set_color_points(colors)
            hw.update()
        self._update_frame_stats()
