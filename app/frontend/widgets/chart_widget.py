import math
from collections import deque

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from frontend.styles import Colors
from backend.engine import METRICS, WARMUP_PACKETS

HISTORY_LEN = 60


class ChartWidget(QWidget):

    def __init__(self, metric_key: str, height: int = 100, parent=None):
        super().__init__(parent)

        self._meta = next(m for m in METRICS if m[0] == metric_key)
        key, label, color, low_desc, high_desc = self._meta

        self._key         = key
        self._color       = color
        self._history     = deque(maxlen=HISTORY_LEN)
        self._tick        = 0
        self._blink_ticks = []
        self._blink_lines = []

        self._build_ui(label, color, low_desc, high_desc)

    def _build_ui(self, label, color, low_desc, high_desc):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(36, 0, 4, 0)
        legend_row.addStretch()
        blink_hint = QLabel("╌╌  blink")
        blink_hint.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 9px; letter-spacing: 0.3px;"
        )
        legend_row.addWidget(blink_hint)
        layout.addLayout(legend_row)

        self._plot = pg.PlotWidget()
        self._plot.setBackground(Colors.BG_CARD)
        self._plot.setFixedHeight(110)
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.hideButtons()
        self._plot.setMenuEnabled(False)

        self._plot.setXRange(0, HISTORY_LEN - 1, padding=0)
        self._plot.setYRange(-5, 105, padding=0)

        self._plot.showAxis("top",    False)
        self._plot.showAxis("right",  False)
        self._plot.showAxis("bottom", False)

        left_ax = self._plot.getAxis("left")
        left_ax.setTicks([[(0, "0"), (50, "50"), (100, "100")]])
        left_ax.setStyle(tickFont=pg.QtGui.QFont("Inter", 7))
        left_ax.setTextPen(pg.mkPen(Colors.TEXT_SECONDARY))
        left_ax.setPen(pg.mkPen(Colors.BORDER))
        left_ax.setWidth(32)

        for y in (30, 70):
            ref = pg.InfiniteLine(
                pos=y, angle=0,
                pen=pg.mkPen(Colors.BORDER, width=1, style=Qt.PenStyle.DashLine),
            )
            self._plot.addItem(ref)

        self._curve = self._plot.plot(
            [], [],
            pen=pg.mkPen(color, width=2),
            antialias=True,
        )

        layout.addWidget(self._plot)

    def push(self, score: float | None, blink: int | None = None) -> None:
        self._tick += 1
        self._history.append(score)

        if blink is not None:
            self._blink_ticks.append(self._tick)

        self._redraw()

    def clear(self) -> None:
        self._history.clear()
        self._tick        = 0
        self._blink_ticks = []
        self._remove_blink_lines()
        self._curve.setData([], [])

    def _redraw(self) -> None:
        n            = len(self._history)
        window_size  = n
        # how many ticks have scrolled off the left edge of the deque
        window_start = self._tick - n

        x = np.arange(window_size, dtype=float)
        y = np.array(
            [v if v is not None else math.nan for v in self._history],
            dtype=float,
        )

        self._curve.setData(x, y)
        self._plot.setXRange(0, HISTORY_LEN - 1, padding=0)

        self._remove_blink_lines()
        for abs_tick in self._blink_ticks:
            wx = abs_tick - window_start - 1
            if 0 <= wx < window_size:
                line = pg.InfiniteLine(
                    pos=wx, angle=90,
                    pen=pg.mkPen((180, 180, 180, 120), width=1,
                                 style=Qt.PenStyle.DashLine),
                )
                self._plot.addItem(line)
                self._blink_lines.append(line)

        cutoff = self._tick - HISTORY_LEN
        self._blink_ticks = [t for t in self._blink_ticks if t > cutoff]

    def _remove_blink_lines(self) -> None:
        for line in self._blink_lines:
            self._plot.removeItem(line)
        self._blink_lines = []
