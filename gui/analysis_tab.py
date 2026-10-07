# gui/analysis_tab.py
import cv2
import numpy as np
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QProgressBar, QScrollArea, QGroupBox,
                              QGridLayout, QSizePolicy, QFrame)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QFont, QMouseEvent
from core.color_store import ColorStore
from core.video_manager import VideoManager

# In gui/analysis_tab.py, replace the AnalysisWorker class with this:

# gui/analysis_tab.py - just replace the AnalysisWorker.run method's mask building section
# Here's the complete updated AnalysisWorker:

# gui/analysis_tab.py - Replace ONLY the AnalysisWorker class

class AnalysisWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(dict)

    def __init__(self, video_manager: VideoManager, color_store: ColorStore, frame_step: int = 1):
        super().__init__()
        self.video_manager = video_manager
        self.color_store = color_store
        self.frame_step = frame_step
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        from core.mask_builder import build_mask
        from core.contour_utils import find_valid_contours

        bounds = self.color_store.get_bounds()
        default_bounds = self.color_store.DEFAULT_BOUNDS
        min_area = self.color_store.min_area
        merge_distance = self.color_store.merge_distance

        if not self.color_store.has_any_bounds():
            self.finished.emit({})
            return

        cap = cv2.VideoCapture(self.video_manager.video_path)
        if not cap.isOpened():
            self.finished.emit({})
            return

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30.0

        frames_to_analyze = list(range(0, total, self.frame_step))
        num_to_analyze = len(frames_to_analyze)

        detection_timeline = [False] * total
        sizes = []
        circularities = []
        count_per_frame = [0] * total
        heatmap = np.zeros((h, w), dtype=np.float64)

        if self.frame_step == 1:
            # Sequential read — fastest for every frame
            for frame_idx in range(total):
                if self._cancelled:
                    cap.release()
                    self.finished.emit({})
                    return

                ret, frame = cap.read()
                if not ret:
                    continue

                mask = build_mask(frame, bounds, default_bounds)
                valid = find_valid_contours(mask, min_area, merge_distance)

                detection_timeline[frame_idx] = len(valid) > 0
                count_per_frame[frame_idx] = len(valid)

                for c in valid:
                    area = cv2.contourArea(c)
                    perimeter = cv2.arcLength(c, True)
                    sizes.append(area)
                    if perimeter > 0:
                        circ = min(4.0 * np.pi * area / (perimeter * perimeter), 1.0)
                    else:
                        circ = 0.0
                    circularities.append(circ)

                heatmap += (mask.astype(np.float64) / 255.0)

                if frame_idx % 30 == 0:
                    self.progress.emit(int(100 * frame_idx / max(1, total)))
        else:
            # Seek mode — only decode frames we need
            for progress_idx, frame_idx in enumerate(frames_to_analyze):
                if self._cancelled:
                    cap.release()
                    self.finished.emit({})
                    return

                cap.set(cv2.CAP_PROP_POS_MSEC, frame_idx * 1000.0 / fps)
                ret, frame = cap.read()
                if not ret:
                    continue

                mask = build_mask(frame, bounds, default_bounds)
                valid = find_valid_contours(mask, min_area, merge_distance)

                detection_timeline[frame_idx] = len(valid) > 0
                count_per_frame[frame_idx] = len(valid)

                for c in valid:
                    area = cv2.contourArea(c)
                    perimeter = cv2.arcLength(c, True)
                    sizes.append(area)
                    if perimeter > 0:
                        circ = min(4.0 * np.pi * area / (perimeter * perimeter), 1.0)
                    else:
                        circ = 0.0
                    circularities.append(circ)

                heatmap += (mask.astype(np.float64) / 255.0)

                if progress_idx % 5 == 0:
                    self.progress.emit(int(100 * progress_idx / max(1, num_to_analyze)))

        cap.release()

        if heatmap.max() > 0:
            heatmap = heatmap / heatmap.max()

        results = {
            'detection_timeline': detection_timeline,
            'sizes': sizes,
            'circularities': circularities,
            'count_per_frame': count_per_frame,
            'heatmap': heatmap,
            'total_frames': total,
            'frames_analyzed': num_to_analyze,
            'frame_step': self.frame_step,
        }

        self.progress.emit(100)
        self.finished.emit(results)


class PlotWidget(QWidget):
    """Simple custom plot widget for drawing line/bar charts."""

    def __init__(self, title=""):
        super().__init__()
        self.title = title
        self.data = []
        self.plot_type = 'line'
        self.color = QColor(0, 200, 100)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, data, plot_type='line', color=None):
        self.data = data
        self.plot_type = plot_type
        if color:
            self.color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.fillRect(self.rect(), QColor(25, 25, 25))

        margin_l, margin_r, margin_t, margin_b = 10, 10, 24, 10
        plot_x = margin_l
        plot_y = margin_t
        plot_w = self.width() - margin_l - margin_r
        plot_h = self.height() - margin_t - margin_b

        painter.setPen(QColor(180, 180, 180))
        painter.setFont(QFont("Sans", 9, QFont.Weight.Bold))
        painter.drawText(plot_x, 16, self.title)

        if not self.data or plot_w <= 0 or plot_h <= 0:
            painter.setPen(QColor(100, 100, 100))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data")
            painter.end()
            return

        painter.fillRect(plot_x, plot_y, plot_w, plot_h, QColor(15, 15, 15))

        data = self.data
        n = len(data)
        max_val = max(data) if max(data) > 0 else 1

        if self.plot_type == 'binary':
            bar_w = max(1, plot_w / n)
            for i, val in enumerate(data):
                x = plot_x + i * plot_w / n
                if val:
                    painter.fillRect(int(x), plot_y, max(1, int(bar_w) + 1), plot_h,
                                     QColor(0, 180, 0, 160))
                else:
                    painter.fillRect(int(x), plot_y, max(1, int(bar_w) + 1), plot_h,
                                     QColor(60, 20, 20, 80))

        elif self.plot_type == 'bar':
            bar_w = max(1, plot_w / n)
            for i, val in enumerate(data):
                x = plot_x + i * plot_w / n
                h = (val / max_val) * plot_h
                painter.fillRect(int(x), int(plot_y + plot_h - h),
                                 max(1, int(bar_w)), int(h),
                                 self.color)

        elif self.plot_type == 'line':
            pen = QPen(self.color, 1.5)
            painter.setPen(pen)
            prev_point = None
            for i, val in enumerate(data):
                x = plot_x + i * plot_w / (n - 1) if n > 1 else plot_x
                y = plot_y + plot_h - (val / max_val) * plot_h
                point = (int(x), int(y))
                if prev_point:
                    painter.drawLine(prev_point[0], prev_point[1], point[0], point[1])
                prev_point = point

        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(plot_x, plot_y, plot_w, plot_h)

        painter.end()


class FilterableHistogramWidget(QWidget):
    """
    A 1D histogram with draggable left/right bounds for filtering.
    Emits bounds_changed when the user drags the bars.
    """
    bounds_changed = pyqtSignal(float, float)

    MARGIN_L = 40
    MARGIN_R = 10
    MARGIN_T = 24
    MARGIN_B = 24
    BAR_HIT = 8

    def __init__(self, title="", num_bins=50, data_range=(0, 1)):
        super().__init__()
        self.title = title
        self.num_bins = num_bins
        self.data_range = data_range
        self.raw_data = []
        self.bin_counts = []
        self.bin_edges = []

        self.lo = data_range[0]
        self.hi = data_range[1]

        self._dragging = None
        self.setMouseTracking(True)
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, data):
        self.raw_data = list(data)
        if len(data) > 0:
            self.bin_counts, self.bin_edges = np.histogram(
                data, bins=self.num_bins,
                range=(self.data_range[0], self.data_range[1])
            )
        else:
            self.bin_counts = []
            self.bin_edges = []
        self.update()

    def get_filtered_mask(self):
        """Return boolean array of which raw_data items pass the filter."""
        arr = np.array(self.raw_data)
        return (arr >= self.lo) & (arr <= self.hi)

    def get_bounds(self):
        return (self.lo, self.hi)

    def _plot_rect(self):
        from PyQt6.QtCore import QRect
        return QRect(
            self.MARGIN_L, self.MARGIN_T,
            self.width() - self.MARGIN_L - self.MARGIN_R,
            self.height() - self.MARGIN_T - self.MARGIN_B
        )

    def _data_to_px(self, val):
        r = self._plot_rect()
        frac = (val - self.data_range[0]) / max(1e-9, self.data_range[1] - self.data_range[0])
        return r.left() + frac * r.width()

    def _px_to_data(self, px):
        r = self._plot_rect()
        frac = (px - r.left()) / max(1, r.width())
        frac = np.clip(frac, 0, 1)
        return self.data_range[0] + frac * (self.data_range[1] - self.data_range[0])

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(25, 25, 25))

        r = self._plot_rect()

        # Title
        painter.setPen(QColor(180, 180, 180))
        painter.setFont(QFont("Sans", 9, QFont.Weight.Bold))
        painter.drawText(r.left(), 16, self.title)

        if len(self.bin_counts) == 0:
            painter.setPen(QColor(100, 100, 100))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data")
            painter.end()
            return

        painter.fillRect(r, QColor(15, 15, 15))

        max_count = max(self.bin_counts) if max(self.bin_counts) > 0 else 1
        n_bins = len(self.bin_counts)
        bin_w_px = r.width() / n_bins

        lo_px = self._data_to_px(self.lo)
        hi_px = self._data_to_px(self.hi)

        for i in range(n_bins):
            x = r.left() + i * bin_w_px
            h = (self.bin_counts[i] / max_count) * r.height()
            bin_center = (self.bin_edges[i] + self.bin_edges[i + 1]) / 2.0

            if self.lo <= bin_center <= self.hi:
                color = QColor(0, 180, 120, 200)
            else:
                color = QColor(80, 40, 40, 120)

            painter.fillRect(int(x), int(r.bottom() - h),
                             max(1, int(bin_w_px)), int(h), color)

        # Draw bound lines
        pen = QPen(QColor(0, 255, 0, 220), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(int(lo_px), r.top(), int(lo_px), r.bottom())
        painter.drawLine(int(hi_px), r.top(), int(hi_px), r.bottom())

        # Shade outside regions
        painter.fillRect(r.left(), r.top(), int(lo_px - r.left()), r.height(),
                         QColor(0, 0, 0, 100))
        painter.fillRect(int(hi_px), r.top(), int(r.right() - hi_px), r.height(),
                         QColor(0, 0, 0, 100))

        # Bound value labels
        painter.setPen(QColor(0, 255, 0, 200))
        painter.setFont(QFont("Monospace", 7))
        lo_text = f"{self.lo:.2f}" if isinstance(self.lo, float) else str(int(self.lo))
        hi_text = f"{self.hi:.2f}" if isinstance(self.hi, float) else str(int(self.hi))
        painter.drawText(int(lo_px) + 3, r.top() + 12, lo_text)
        painter.drawText(int(hi_px) + 3, r.top() + 12, hi_text)

        # Axis labels
        painter.setPen(QColor(150, 150, 150))
        painter.setFont(QFont("Monospace", 7))
        range_lo = f"{self.data_range[0]:.1f}" if isinstance(self.data_range[0], float) else str(self.data_range[0])
        range_hi = f"{self.data_range[1]:.1f}" if isinstance(self.data_range[1], float) else str(self.data_range[1])
        painter.drawText(r.left(), r.bottom() + 14, range_lo)
        painter.drawText(r.right() - len(range_hi) * 6, r.bottom() + 14, range_hi)

        # Count of items in range
        in_range = sum(1 for v in self.raw_data if self.lo <= v <= self.hi)
        total = len(self.raw_data)
        pct = (in_range / total * 100) if total > 0 else 0
        painter.setPen(QColor(200, 200, 200))
        painter.setFont(QFont("Sans", 8))
        painter.drawText(r.right() - 120, 16, f"{in_range}/{total} ({pct:.1f}%)")

        # Border
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(r)

        painter.end()

    def _hit_test(self, pos):
        r = self._plot_rect()
        px = pos.x()
        py = pos.y()
        if not (r.top() - 10 <= py <= r.bottom() + 10):
            return None
        lo_px = self._data_to_px(self.lo)
        hi_px = self._data_to_px(self.hi)
        if abs(px - lo_px) < self.BAR_HIT:
            return 'lo'
        if abs(px - hi_px) < self.BAR_HIT:
            return 'hi'
        return None

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_test(event.pos())
            if hit:
                self._dragging = hit

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            val = self._px_to_data(event.pos().x())
            val = max(self.data_range[0], min(self.data_range[1], val))
            if self._dragging == 'lo':
                self.lo = min(val, self.hi)
            else:
                self.hi = max(val, self.lo)
            self.update()
            self.bounds_changed.emit(self.lo, self.hi)
        else:
            hit = self._hit_test(event.pos())
            if hit:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = None
            self.bounds_changed.emit(self.lo, self.hi)


class HeatmapWidget(QWidget):
    """Displays a heatmap image."""

    def __init__(self, title=""):
        super().__init__()
        self.title = title
        self._pixmap = None
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_heatmap(self, heatmap_array):
        """heatmap_array: 2D float array normalized 0-1"""
        if heatmap_array is None or heatmap_array.size == 0:
            self._pixmap = None
            self.update()
            return

        # Apply colormap
        heatmap_uint8 = (heatmap_array * 255).astype(np.uint8)
        colored = cv2.applyColorMap(heatmap_uint8, cv2.COLORMAP_JET)
        rgb = cv2.cvtColor(colored, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self._pixmap = QPixmap.fromImage(qimg.copy())
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(25, 25, 25))

        painter.setPen(QColor(180, 180, 180))
        painter.setFont(QFont("Sans", 9, QFont.Weight.Bold))
        painter.drawText(10, 16, self.title)

        if self._pixmap:
            margin_t = 24
            available = self.rect().adjusted(4, margin_t, -4, -4)
            scaled = self._pixmap.scaled(
                available.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            x = available.left() + (available.width() - scaled.width()) // 2
            y = available.top() + (available.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.setPen(QColor(100, 100, 100))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data")

        painter.end()


class AnalysisTab(QWidget):
    def __init__(self, video_manager: VideoManager, color_store: ColorStore):
        super().__init__()
        self.video_manager = video_manager
        self.color_store = color_store
        self.worker = None
        self.results = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Controls bar
        controls = QHBoxLayout()

        # Frame step selection
        step_label = QLabel("Analyze:")
        step_label.setStyleSheet("color: #aaa; font-weight: bold;")
        controls.addWidget(step_label)

        self.step_buttons = {}
        self.frame_step = 1

        self._btn_style_normal = (
            "QPushButton { background: #2a2a2a; color: #aaa; border: 1px solid #555; "
            "padding: 6px 12px; border-radius: 3px; min-width: 90px; }"
            "QPushButton:hover { background: #3a3a3a; }"
        )
        self._btn_style_selected = (
            "QPushButton { background: #2a4a6a; color: #aaddff; border: 1px solid #4a8aba; "
            "padding: 6px 12px; border-radius: 3px; font-weight: bold; min-width: 90px; }"
        )

        step_options = [
            ("Every Frame", 1),
            ("Every 2nd", 2),
            ("Every 10th", 10),
            ("Every 100th", 100),
        ]

        for label_text, step_val in step_options:
            btn = QPushButton(label_text)
            if step_val == 1:
                btn.setStyleSheet(self._btn_style_selected)
            else:
                btn.setStyleSheet(self._btn_style_normal)
            # Use default arg to capture step_val correctly
            btn.clicked.connect(lambda checked, s=step_val: self._set_frame_step(s))
            controls.addWidget(btn)
            self.step_buttons[step_val] = btn

        controls.addSpacing(20)

        # Run button
        self.run_btn = QPushButton("▶ Run Full Analysis")
        self.run_btn.setStyleSheet(
            "QPushButton { background: #2a4a2a; color: #aaffaa; border: 1px solid #4a4a4a; "
            "padding: 8px 16px; font-weight: bold; border-radius: 4px; }"
            "QPushButton:hover { background: #3a6a3a; }"
            "QPushButton:disabled { background: #333; color: #666; }"
        )
        self.run_btn.clicked.connect(self._run_analysis)
        controls.addWidget(self.run_btn)

        # Cancel button
        self.cancel_btn = QPushButton("✕ Cancel")
        self.cancel_btn.setStyleSheet(
            "QPushButton { background: #4a2a2a; color: #ffaaaa; border: 1px solid #4a4a4a; "
            "padding: 8px 16px; border-radius: 4px; }"
            "QPushButton:hover { background: #6a3a3a; }"
        )
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_analysis)
        controls.addWidget(self.cancel_btn)

        controls.addStretch()

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #aaa;")
        controls.addWidget(self.status_label)

        layout.addLayout(controls)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #444; background: #222; border-radius: 3px; text-align: center; color: #aaa; }"
            "QProgressBar::chunk { background: #2a8a2a; }"
        )
        layout.addWidget(self.progress_bar)

        # Scrollable results area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: #1a1a1a; }")

        self.results_widget = QWidget()
        self.results_layout = QVBoxLayout(self.results_widget)
        self.results_layout.setContentsMargins(4, 4, 4, 4)
        self.results_layout.setSpacing(6)

        # Stats summary
        self.stats_label = QLabel("Run analysis to see results.")
        self.stats_label.setStyleSheet(
            "color: #ccc; background: #222; padding: 8px; border: 1px solid #444; border-radius: 4px; font-family: monospace;"
        )
        self.stats_label.setWordWrap(True)
        self.results_layout.addWidget(self.stats_label)

        # Detection timeline
        self.timeline_plot = PlotWidget("Detection Timeline (green = detected)")
        self.results_layout.addWidget(self.timeline_plot)

        # Detection count per frame
        self.count_plot = PlotWidget("Detections Per Frame")
        self.results_layout.addWidget(self.count_plot)

        # Size histogram with filterable bounds
        self.size_histogram = FilterableHistogramWidget(
            title="Detection Size Distribution (area in px²)",
            num_bins=60,
            data_range=(0, 10000)
        )
        self.size_histogram.bounds_changed.connect(self._on_size_bounds_changed)
        self.results_layout.addWidget(self.size_histogram)

        # Size stats label (updates when bounds change)
        self.size_stats_label = QLabel("")
        self.size_stats_label.setStyleSheet(
            "color: #aaa; background: #1e1e1e; padding: 4px; border: 1px solid #333; "
            "border-radius: 3px; font-family: monospace; font-size: 10px;"
        )
        self.results_layout.addWidget(self.size_stats_label)

        # Circularity histogram with filterable bounds
        self.circularity_histogram = FilterableHistogramWidget(
            title="Circularity Distribution (1.0 = perfect circle, 0.0 = jagged/elongated)",
            num_bins=50,
            data_range=(0.0, 1.0)
        )
        self.circularity_histogram.bounds_changed.connect(self._on_circularity_bounds_changed)
        self.results_layout.addWidget(self.circularity_histogram)

        # Circularity stats label
        self.circularity_stats_label = QLabel("")
        self.circularity_stats_label.setStyleSheet(
            "color: #aaa; background: #1e1e1e; padding: 4px; border: 1px solid #333; "
            "border-radius: 3px; font-family: monospace; font-size: 10px;"
        )
        self.results_layout.addWidget(self.circularity_stats_label)

        # Heatmap
        self.heatmap_widget = HeatmapWidget("Detection Heatmap (accumulated mask)")
        self.heatmap_widget.setMinimumHeight(300)
        self.results_layout.addWidget(self.heatmap_widget)

        self.results_layout.addStretch()

        self.scroll.setWidget(self.results_widget)
        layout.addWidget(self.scroll)

    def on_video_loaded(self):
        self.status_label.setText("Video loaded. Set color bounds and run analysis.")
        self.progress_bar.setValue(0)

    def _set_frame_step(self, step):
        self.frame_step = step
        for s, btn in self.step_buttons.items():
            if s == step:
                btn.setStyleSheet(self._btn_style_selected)
            else:
                btn.setStyleSheet(self._btn_style_normal)

    def _run_analysis(self):
        if not self.video_manager.is_loaded():
            self.status_label.setText("No video loaded!")
            return

        if not self.color_store.has_any_bounds():
            self.status_label.setText("No color bounds set! Adjust histograms in Color Isolation tab first.")
            return

        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status_label.setText("Analyzing...")
        self.progress_bar.setValue(0)

        self.worker = AnalysisWorker(self.video_manager, self.color_store, self.frame_step)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _cancel_analysis(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
            self.status_label.setText("Cancelled.")
            self.run_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)

    def _on_progress(self, value):
        self.progress_bar.setValue(value)

    def _on_finished(self, results):
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        if not results:
            self.status_label.setText("Analysis failed or no bounds set.")
            return

        self.results = results
        self.status_label.setText("Analysis complete!")
        self.progress_bar.setValue(100)

        # Keep only the analyzed frames so skipped ones don't read as misses
        step = results['frame_step']
        timeline = results['detection_timeline'][::step]
        sizes = results['sizes']
        circularities = results['circularities']
        counts = results['count_per_frame'][::step]
        heatmap = results['heatmap']
        total_frames = results['total_frames']
        analyzed = results['frames_analyzed']

        # Stats summary
        detected_frames = sum(1 for t in timeline if t)
        total_detections = sum(counts)
        avg_size = np.mean(sizes) if sizes else 0
        median_size = np.median(sizes) if sizes else 0
        avg_circ = np.mean(circularities) if circularities else 0

        stats_text = (
            f"Total Frames: {total_frames}\n"
            f"Frames Analyzed: {analyzed} (every {step})\n"
            f"Frames with Detection: {detected_frames} ({100 * detected_frames / max(1, analyzed):.1f}%)\n"
            f"Total Detections: {total_detections}\n"
            f"Avg Detections/Frame: {total_detections / max(1, analyzed):.2f}\n"
            f"Avg Detection Size: {avg_size:.1f} px²\n"
            f"Median Detection Size: {median_size:.1f} px²\n"
            f"Avg Circularity: {avg_circ:.3f}\n"
        )
        self.stats_label.setText(stats_text)

        # Timeline
        self.timeline_plot.set_data(timeline, plot_type='binary')

        # Count per frame
        self.count_plot.set_data(counts, plot_type='bar', color=QColor(100, 150, 255))

        # Size histogram
        if sizes:
            max_size = max(sizes)
            # Set a sensible range
            nice_max = max(1000, int(np.percentile(sizes, 99) * 1.2)) if len(sizes) > 10 else max(1000, int(max_size * 1.2))
            self.size_histogram.data_range = (0, nice_max)
            self.size_histogram.lo = 0
            self.size_histogram.hi = nice_max
            self.size_histogram.num_bins = min(80, max(20, nice_max // 50))
            self.size_histogram.set_data(sizes)
            self._update_size_stats()
        else:
            self.size_histogram.set_data([])
            self.size_stats_label.setText("No detections.")

        # Circularity histogram
        if circularities:
            self.circularity_histogram.data_range = (0.0, 1.0)
            self.circularity_histogram.lo = 0.0
            self.circularity_histogram.hi = 1.0
            self.circularity_histogram.set_data(circularities)
            self._update_circularity_stats()
        else:
            self.circularity_histogram.set_data([])
            self.circularity_stats_label.setText("No detections.")

        # Heatmap
        self.heatmap_widget.set_heatmap(heatmap)

    def _on_size_bounds_changed(self, lo, hi):
        self._update_size_stats()

    def _on_circularity_bounds_changed(self, lo, hi):
        self._update_circularity_stats()

    def _update_size_stats(self):
        if not self.results or not self.results['sizes']:
            return
        sizes = np.array(self.results['sizes'])
        lo, hi = self.size_histogram.get_bounds()
        mask = (sizes >= lo) & (sizes <= hi)
        filtered = sizes[mask]
        total = len(sizes)
        count = len(filtered)
        if count > 0:
            self.size_stats_label.setText(
                f"Range: [{lo:.0f}, {hi:.0f}] px²  |  "
                f"In range: {count}/{total} ({100 * count / total:.1f}%)  |  "
                f"Mean: {np.mean(filtered):.1f}  |  "
                f"Median: {np.median(filtered):.1f}  |  "
                f"Std: {np.std(filtered):.1f}  |  "
                f"Min: {np.min(filtered):.1f}  |  "
                f"Max: {np.max(filtered):.1f}"
            )
        else:
            self.size_stats_label.setText(f"Range: [{lo:.0f}, {hi:.0f}] px²  |  No detections in range.")

    def _update_circularity_stats(self):
        if not self.results or not self.results['circularities']:
            return
        circs = np.array(self.results['circularities'])
        lo, hi = self.circularity_histogram.get_bounds()
        mask = (circs >= lo) & (circs <= hi)
        filtered = circs[mask]
        total = len(circs)
        count = len(filtered)
        if count > 0:
            self.circularity_stats_label.setText(
                f"Range: [{lo:.3f}, {hi:.3f}]  |  "
                f"In range: {count}/{total} ({100 * count / total:.1f}%)  |  "
                f"Mean: {np.mean(filtered):.3f}  |  "
                f"Median: {np.median(filtered):.3f}  |  "
                f"Std: {np.std(filtered):.3f}  |  "
                f"Min: {np.min(filtered):.3f}  |  "
                f"Max: {np.max(filtered):.3f}"
            )
        else:
            self.circularity_stats_label.setText(f"Range: [{lo:.3f}, {hi:.3f}]  |  No detections in range.")