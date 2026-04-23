"""
HistoryScreen — two-panel session browser.

Left panel  : tab-switched list of recording sessions / training sessions.
Right panel : detail view for the selected item — metric bars, note, and
              (for recording sessions) a static time-series chart.

Memory / lifetime notes
-----------------------
* __init__ only builds the static skeleton; no DB work happens there.
* Data is loaded lazily on the first showEvent.  refresh() forces a full
  reload (wired to the Refresh button).
* Dynamic list sections are rebuilt via _clear_layout(), which calls
  takeAt() + deleteLater() for every removed widget.  The local reference
  `w` drops to zero each iteration so CPython can release it immediately;
  Qt's deferred-deletion pass handles the C++ side.
* _sel_session_row / _sel_training_row hold a pointer to the currently
  highlighted list item.  Both are set to None BEFORE _clear_layout() is
  called so we never touch a widget that has been scheduled for deletion.
* The pyqtgraph PlotWidget (_plot_widget) is created once in
  _build_session_detail() and lives for the screen's lifetime.  Only its
  data changes (_plot_curve.setData) — no widget is ever recreated.
* All signal connections use bound methods; no lambda captures self in a
  long-lived connection.
* No background threads.  DB queries are lightweight and run synchronously,
  consistent with every other screen in the app.
"""

from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QComboBox, QStackedWidget,
    QSizePolicy,
)

from backend.database import Database
from backend.engine import METRICS
from frontend.styles import Colors, ACCENT_BTN
from frontend.utils import fmt_seconds as _fmt_seconds, fmt_duration as _fmt_duration, fmt_date as _fmt_date


def _rgba(hex_color: str, alpha: float) -> str:
    """
    Return an unambiguous 'rgba(r, g, b, alpha)' string from a '#RRGGBB' hex.

    Never append hex digits directly to a color string in Qt stylesheets.
    Qt parses 8-digit hex as #AARRGGBB (alpha first), which is the opposite
    of CSS4 (#RRGGBBAA) and produces completely wrong colours.  rgba() has
    no such ambiguity.
    """
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha:.2f})"


def _clear_layout(layout) -> None:
    """
    Remove all items from *layout* and schedule their widgets for deletion.

    takeAt() severs layout ownership.  deleteLater() defers C++ destruction
    to after the current event-loop turn.  The local `w` reference is
    released at the end of each iteration.
    """
    while layout.count():
        item = layout.takeAt(0)
        w    = item.widget()
        if w is not None:
            w.deleteLater()


# ── Small static-UI helpers ────────────────────────────────────────────────────

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {Colors.TEXT_MUTED}; font-size: 9px; "
        f"font-weight: 700; letter-spacing: 1.5px;"
    )
    return lbl


def _rule() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {Colors.BORDER};")
    return f


def _empty_hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(
        f"color: {Colors.TEXT_MUTED}; font-size: 11px; font-style: italic;"
    )
    return lbl


# ── Metric bar (used in the detail panel) ─────────────────────────────────────

class _MetricBar(QWidget):
    """Horizontal label + track + value row for one metric average."""

    def __init__(self, key: str, label: str, color: str,
                 value: float | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(26)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        lbl = QLabel(label.upper())
        lbl.setFixedWidth(52)
        lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 9px; "
            f"font-weight: 700; letter-spacing: 0.8px;"
        )
        row.addWidget(lbl)

        track = QWidget()
        track.setFixedHeight(5)
        track.setStyleSheet(
            f"background: {Colors.BG_SURFACE}; border-radius: 2px;"
        )
        track.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        fill_w = int(max(0.0, min(1.0, (value or 0) / 100)) * 160)
        fill = QWidget(track)          # parented to track — lives with it
        fill.setFixedHeight(5)
        fill.setStyleSheet(f"background: {color}; border-radius: 2px;")
        fill.setGeometry(0, 0, fill_w, 5)
        row.addWidget(track, 1)

        val_lbl = QLabel(f"{value:.0f}" if value is not None else "—")
        val_lbl.setFixedWidth(28)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        val_lbl.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 700;"
        )
        row.addWidget(val_lbl)


# ── List-item row widgets ──────────────────────────────────────────────────────

_ITEM_H          = 58
_ITEM_NORMAL_SS  = (
    f"background: transparent; border-radius: 8px;"
)
_ITEM_HOVER_SS   = (
    f"background: rgba(127,119,221,0.07); border-radius: 8px;"
)
_ITEM_ACTIVE_SS  = (
    f"background: rgba(127,119,221,0.15); border-radius: 8px;"
)


class _SessionItem(QWidget):
    """Clickable list row for one recording session."""

    def __init__(self, row, on_click, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # on_click is a bound method on HistoryScreen; no closure.
        self._on_click   = on_click
        self._row        = row
        self._active     = False
        self.setFixedHeight(_ITEM_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(_ITEM_NORMAL_SS)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(3)

        date_lbl = QLabel(_fmt_date(row["started_at"]))
        date_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: 600;"
        )
        lay.addWidget(date_lbl)

        src = row["source_name"] or "Unknown"
        dur = _fmt_duration(row["started_at"], row["ended_at"])
        cnt = int(row["reading_count"] or 0)
        sub = QLabel(f"{src}  ·  {dur}  ·  {cnt} pts")
        sub.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px;")
        lay.addWidget(sub)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setStyleSheet(_ITEM_ACTIVE_SS if active else _ITEM_NORMAL_SS)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click(self)

    def enterEvent(self, event) -> None:
        if not self._active:
            self.setStyleSheet(_ITEM_HOVER_SS)

    def leaveEvent(self, event) -> None:
        if not self._active:
            self.setStyleSheet(_ITEM_NORMAL_SS)


class _TrainingItem(QWidget):
    """Clickable list row for one training session."""

    def __init__(self, row, on_click, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on_click = on_click
        self._row      = row
        self._active   = False
        self.setFixedHeight(_ITEM_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(_ITEM_NORMAL_SS)

        metric = row["target_metric"] or "focus"
        color  = Colors.metric(metric)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 14, 0)
        lay.setSpacing(0)

        bar = QFrame()
        bar.setFixedWidth(3)
        bar.setStyleSheet(
            f"background: {color}; "
            f"border-top-left-radius: 8px; border-bottom-left-radius: 8px;"
        )
        lay.addWidget(bar)
        lay.addSpacing(12)

        info = QVBoxLayout()
        info.setSpacing(3)
        info.setContentsMargins(0, 0, 0, 0)

        date_lbl = QLabel(_fmt_date(row["started_at"]))
        date_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: 600;"
        )
        info.addWidget(date_lbl)

        thr = float(row["target_threshold"] or 0)
        sot = _fmt_seconds(row["seconds_on_target"])
        sub = QLabel(f"≥ {thr:.0f}  ·  {sot} on target")
        sub.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px;")
        info.addWidget(sub)
        lay.addLayout(info, 1)

        badge = QLabel(f"  {metric.upper()}  ")
        badge.setFixedHeight(18)
        badge.setStyleSheet(
            f"background: {_rgba(color, 0.12)}; color: {color}; "
            f"border: 1px solid {_rgba(color, 0.35)}; border-radius: 4px; "
            f"font-size: 9px; font-weight: 700; letter-spacing: 0.8px;"
        )
        lay.addWidget(badge)

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setStyleSheet(_ITEM_ACTIVE_SS if active else _ITEM_NORMAL_SS)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click(self)

    def enterEvent(self, event) -> None:
        if not self._active:
            self.setStyleSheet(_ITEM_HOVER_SS)

    def leaveEvent(self, event) -> None:
        if not self._active:
            self.setStyleSheet(_ITEM_NORMAL_SS)


# ── History screen ────────────────────────────────────────────────────────────

class HistoryScreen(QWidget):
    """
    Two-panel history browser.

    Left  — tab-switched list (Sessions | Training) with per-metric filter
            for the training tab.
    Right — detail panel; a QStackedWidget of:
              0  placeholder
              1  recording-session detail (metric bars + note + chart)
              2  training-session detail  (metric bars + note + stats)
    """

    def __init__(
        self,
        db: Database,
        user_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db      = db
        self._user_id = user_id
        self._loaded  = False

        # Currently highlighted list-item widgets.
        # Nulled BEFORE _clear_layout() so we never reference a zombie.
        self._sel_session_row:  _SessionItem  | None = None
        self._sel_training_row: _TrainingItem | None = None

        # Readings for the charts (replaced on each selection, old list GC'd).
        self._session_readings:  list = []
        self._training_readings: list = []
        # Set of currently visible metrics in the session chart.  Kept as
        # instance state so the selection survives switching between sessions.
        self._active_metrics: set[str] = {"focus"}

        self._build_ui()

    # ── UI skeleton ───────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_left_panel())

        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background: {Colors.BORDER};")
        root.addWidget(sep)

        root.addWidget(self._build_right_panel(), 1)

    # ── Left panel ────────────────────────────────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(270)
        panel.setStyleSheet(f"background: {Colors.BG_SIDEBAR};")

        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # ── Title ─────────────────────────────────────────────────────────────
        title_row = QWidget()
        title_row.setFixedHeight(56)
        title_row.setStyleSheet("background: transparent;")
        tr = QHBoxLayout(title_row)
        tr.setContentsMargins(20, 0, 16, 0)
        title_lbl = QLabel("History")
        title_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 18px; font-weight: 700;"
        )
        tr.addWidget(title_lbl)
        tr.addStretch()
        vbox.addWidget(title_row)
        vbox.addWidget(_rule())

        # ── Tab bar ───────────────────────────────────────────────────────────
        tab_bar = QWidget()
        tab_bar.setFixedHeight(40)
        tab_bar.setStyleSheet("background: transparent;")
        tb = QHBoxLayout(tab_bar)
        tb.setContentsMargins(12, 6, 12, 6)
        tb.setSpacing(6)

        self._tab_sessions  = self._make_tab_btn("Sessions")
        self._tab_training  = self._make_tab_btn("Training")
        self._tab_sessions.clicked.connect(self._show_sessions_tab)
        self._tab_training.clicked.connect(self._show_training_tab)

        tb.addWidget(self._tab_sessions)
        tb.addWidget(self._tab_training)
        vbox.addWidget(tab_bar)
        vbox.addWidget(_rule())

        # ── Training metric filter (hidden when Sessions tab active) ──────────
        self._filter_row = QWidget()
        self._filter_row.setFixedHeight(36)
        self._filter_row.setStyleSheet("background: transparent;")
        fr = QHBoxLayout(self._filter_row)
        fr.setContentsMargins(12, 0, 12, 0)
        fr.setSpacing(6)
        fr.addWidget(QLabel("Metric:"))
        self._filter_row.layout().itemAt(0).widget().setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 10px;"
        )

        self._metric_combo = QComboBox()
        self._metric_combo.addItem("All", None)
        for key, label, *_ in METRICS:
            self._metric_combo.addItem(label, key)
        self._metric_combo.setFixedHeight(22)
        self._metric_combo.setStyleSheet(
            f"QComboBox {{ background: {Colors.BG_INPUT}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 5px; "
            f"padding: 0 8px; color: {Colors.TEXT_PRIMARY}; font-size: 11px; }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ background: {Colors.BG_SURFACE}; "
            f"border: 1px solid {Colors.BORDER}; color: {Colors.TEXT_PRIMARY}; }}"
        )
        self._metric_combo.currentIndexChanged.connect(self._on_metric_filter_changed)
        fr.addWidget(self._metric_combo, 1)
        self._filter_row.hide()
        vbox.addWidget(self._filter_row)

        # ── List stack (sessions / training) ──────────────────────────────────
        self._list_stack = QStackedWidget()
        self._list_stack.setStyleSheet("background: transparent;")

        # Sessions scroll
        self._sessions_scroll, self._sessions_list_layout = self._make_scroll_list()
        self._list_stack.addWidget(self._sessions_scroll)   # index 0

        # Training scroll
        self._training_scroll, self._training_list_layout = self._make_scroll_list()
        self._list_stack.addWidget(self._training_scroll)   # index 1

        vbox.addWidget(self._list_stack, 1)
        vbox.addWidget(_rule())

        # ── Refresh button ────────────────────────────────────────────────────
        refresh_btn = QPushButton("↺  Refresh")
        refresh_btn.setFixedHeight(32)
        refresh_btn.setStyleSheet(ACCENT_BTN)
        refresh_btn.setContentsMargins(12, 0, 12, 0)
        refresh_btn.clicked.connect(self.refresh)   # bound method, no lambda

        btn_wrap = QWidget()
        btn_wrap.setFixedHeight(48)
        btn_wrap.setStyleSheet("background: transparent;")
        bw = QHBoxLayout(btn_wrap)
        bw.setContentsMargins(12, 8, 12, 8)
        bw.addWidget(refresh_btn)
        vbox.addWidget(btn_wrap)

        # Start on Sessions tab
        self._show_sessions_tab()
        return panel

    @staticmethod
    def _make_tab_btn(label: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedHeight(26)
        btn.setCheckable(True)
        btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {Colors.BORDER}; "
            f"border-radius: 6px; color: {Colors.TEXT_MUTED}; font-size: 11px; "
            f"font-weight: 500; }}"
            f"QPushButton:checked {{ background: rgba(127,119,221,0.15); "
            f"border-color: rgba(127,119,221,0.40); color: {Colors.ACCENT}; "
            f"font-weight: 600; }}"
        )
        return btn

    @staticmethod
    def _make_scroll_list() -> tuple[QScrollArea, QVBoxLayout]:
        """Return (scroll_area, inner_vbox) for a list panel."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)
        lay.addStretch()

        scroll.setWidget(inner)
        return scroll, lay

    # ── Right panel ───────────────────────────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        self._detail_stack = QStackedWidget()
        self._detail_stack.setStyleSheet("background: transparent;")

        self._detail_stack.addWidget(self._build_placeholder())   # 0
        self._detail_stack.addWidget(self._build_session_detail()) # 1
        self._detail_stack.addWidget(self._build_training_detail()) # 2

        self._detail_stack.setCurrentIndex(0)
        return self._detail_stack

    def _build_placeholder(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("◷")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 42px;"
        )
        msg = QLabel("Select a session from the list")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 13px; font-style: italic;"
        )
        lay.addWidget(icon)
        lay.addSpacing(10)
        lay.addWidget(msg)
        return w

    def _build_session_detail(self) -> QWidget:
        """
        Static skeleton for a recording-session detail view.
        Labels and the chart data are updated on selection — nothing is
        recreated.
        """
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        outer.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.setStyleSheet("background: transparent;")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(inner)
        vbox.setContentsMargins(32, 28, 32, 32)
        vbox.setSpacing(0)

        # ── Session header ────────────────────────────────────────────────────
        self._sess_date_lbl = QLabel()
        self._sess_date_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 18px; font-weight: 700; "
            f"letter-spacing: -0.3px;"
        )
        vbox.addWidget(self._sess_date_lbl)
        vbox.addSpacing(4)

        self._sess_meta_lbl = QLabel()
        self._sess_meta_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11px;"
        )
        vbox.addWidget(self._sess_meta_lbl)
        vbox.addSpacing(20)

        # ── Note ──────────────────────────────────────────────────────────────
        self._sess_note_frame = QWidget()
        self._sess_note_frame.setStyleSheet(
            f"background: {Colors.BG_CARD}; border-radius: 8px;"
        )
        nf_lay = QVBoxLayout(self._sess_note_frame)
        nf_lay.setContentsMargins(16, 12, 16, 12)
        nf_lbl = QLabel("NOTE")
        nf_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-weight: 700; "
            f"letter-spacing: 1.2px;"
        )
        self._sess_note_lbl = QLabel()
        self._sess_note_lbl.setWordWrap(True)
        self._sess_note_lbl.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 12px;"
        )
        nf_lay.addWidget(nf_lbl)
        nf_lay.addWidget(self._sess_note_lbl)
        vbox.addWidget(self._sess_note_frame)
        vbox.addSpacing(20)

        # ── Metric averages ───────────────────────────────────────────────────
        vbox.addWidget(_section_label("AVERAGES"))
        vbox.addSpacing(10)
        self._sess_bars_layout = QVBoxLayout()
        self._sess_bars_layout.setSpacing(6)
        vbox.addLayout(self._sess_bars_layout)
        vbox.addSpacing(24)

        # ── Chart section ─────────────────────────────────────────────────────
        vbox.addWidget(_section_label("TIME SERIES"))
        vbox.addSpacing(10)

        # Metric selector pills — each toggles its curve independently.
        pill_row = QHBoxLayout()
        pill_row.setSpacing(6)
        self._metric_pills: dict[str, QPushButton] = {}
        for key, label, color, *_ in METRICS:
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.setCheckable(True)
            btn.setProperty("metric_key", key)
            btn.setProperty("metric_color", color)
            active = key in self._active_metrics
            btn.setChecked(active)
            btn.setStyleSheet(self._pill_style(color, active=active))
            btn.clicked.connect(self._on_pill_clicked)  # bound method
            self._metric_pills[key] = btn
            pill_row.addWidget(btn)
        pill_row.addStretch()
        vbox.addLayout(pill_row)
        vbox.addSpacing(10)

        # PlotWidget — created once; all five curves live inside it for the
        # screen's lifetime.  Inactive curves are hidden via setData([], [])
        # rather than being removed/re-added (no item-tree churn).
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground(Colors.BG_CARD)
        self._plot_widget.setFixedHeight(200)
        self._plot_widget.setMouseEnabled(x=False, y=False)
        self._plot_widget.hideButtons()
        self._plot_widget.setMenuEnabled(False)
        self._plot_widget.setYRange(-5, 105, padding=0)
        self._plot_widget.showAxis("top",    False)
        self._plot_widget.showAxis("right",  False)

        left_ax = self._plot_widget.getAxis("left")
        left_ax.setTicks([[(0, "0"), (50, "50"), (100, "100")]])
        left_ax.setStyle(tickFont=pg.QtGui.QFont("Inter", 7))
        left_ax.setTextPen(pg.mkPen(Colors.TEXT_MUTED))
        left_ax.setPen(pg.mkPen(Colors.BORDER))
        left_ax.setWidth(32)

        bot_ax = self._plot_widget.getAxis("bottom")
        bot_ax.setStyle(tickFont=pg.QtGui.QFont("Inter", 7))
        bot_ax.setTextPen(pg.mkPen(Colors.TEXT_MUTED))
        bot_ax.setPen(pg.mkPen(Colors.BORDER))

        for y_ref in (30, 70):
            self._plot_widget.addItem(pg.InfiniteLine(
                pos=y_ref, angle=0,
                pen=pg.mkPen(Colors.BORDER, width=1,
                             style=Qt.PenStyle.DashLine),
            ))

        # One PlotDataItem per metric — all added once at construction time.
        # Data is updated (or cleared) via setData() on every selection change.
        self._plot_curves: dict[str, pg.PlotDataItem] = {}
        for key, _label, color, *_ in METRICS:
            curve = self._plot_widget.plot(
                [], [], pen=pg.mkPen(color, width=2), antialias=True
            )
            self._plot_curves[key] = curve

        vbox.addWidget(self._plot_widget)
        vbox.addStretch()

        outer.setWidget(inner)
        return outer

    def _build_training_detail(self) -> QWidget:
        """
        Static skeleton for a training-session detail view.

        Shows only the trained metric (not all five) and a chart of that
        metric over the session window.  The PlotWidget and threshold line
        are created once here and updated via setData() / setPos() on each
        selection — nothing is ever recreated.
        """
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        outer.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.setStyleSheet("background: transparent;")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(inner)
        vbox.setContentsMargins(32, 28, 32, 32)
        vbox.setSpacing(0)

        # ── Training header ───────────────────────────────────────────────────
        self._tr_date_lbl = QLabel()
        self._tr_date_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 18px; font-weight: 700; "
            f"letter-spacing: -0.3px;"
        )
        vbox.addWidget(self._tr_date_lbl)
        vbox.addSpacing(4)

        self._tr_meta_lbl = QLabel()
        self._tr_meta_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11px;"
        )
        vbox.addWidget(self._tr_meta_lbl)
        vbox.addSpacing(16)

        # ── Stats cards row ───────────────────────────────────────────────────
        self._tr_stats_layout = QHBoxLayout()
        self._tr_stats_layout.setSpacing(10)
        vbox.addLayout(self._tr_stats_layout)
        vbox.addSpacing(20)

        # ── Note ──────────────────────────────────────────────────────────────
        self._tr_note_frame = QWidget()
        self._tr_note_frame.setStyleSheet(
            f"background: {Colors.BG_CARD}; border-radius: 8px;"
        )
        tnf_lay = QVBoxLayout(self._tr_note_frame)
        tnf_lay.setContentsMargins(16, 12, 16, 12)
        tnf_hdr = QLabel("NOTE")
        tnf_hdr.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-weight: 700; "
            f"letter-spacing: 1.2px;"
        )
        self._tr_note_lbl = QLabel()
        self._tr_note_lbl.setWordWrap(True)
        self._tr_note_lbl.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 12px;"
        )
        tnf_lay.addWidget(tnf_hdr)
        tnf_lay.addWidget(self._tr_note_lbl)
        vbox.addWidget(self._tr_note_frame)
        vbox.addSpacing(20)

        # ── Single-metric average bar (label updated on selection) ────────────
        vbox.addWidget(_section_label("AVERAGE  (during session)"))
        vbox.addSpacing(10)
        # Container replaced each selection via _clear_layout.
        self._tr_bar_layout = QVBoxLayout()
        self._tr_bar_layout.setSpacing(0)
        vbox.addLayout(self._tr_bar_layout)
        vbox.addSpacing(24)

        # ── Chart ─────────────────────────────────────────────────────────────
        vbox.addWidget(_section_label("TIME SERIES"))
        vbox.addSpacing(10)

        # PlotWidget — created once, lives for the screen's lifetime.
        self._tr_plot_widget = pg.PlotWidget()
        self._tr_plot_widget.setBackground(Colors.BG_CARD)
        self._tr_plot_widget.setFixedHeight(200)
        self._tr_plot_widget.setMouseEnabled(x=False, y=False)
        self._tr_plot_widget.hideButtons()
        self._tr_plot_widget.setMenuEnabled(False)
        self._tr_plot_widget.setYRange(-5, 105, padding=0)
        self._tr_plot_widget.showAxis("top",   False)
        self._tr_plot_widget.showAxis("right", False)

        tr_left = self._tr_plot_widget.getAxis("left")
        tr_left.setTicks([[(0, "0"), (50, "50"), (100, "100")]])
        tr_left.setStyle(tickFont=pg.QtGui.QFont("Inter", 7))
        tr_left.setTextPen(pg.mkPen(Colors.TEXT_MUTED))
        tr_left.setPen(pg.mkPen(Colors.BORDER))
        tr_left.setWidth(32)

        tr_bot = self._tr_plot_widget.getAxis("bottom")
        tr_bot.setStyle(tickFont=pg.QtGui.QFont("Inter", 7))
        tr_bot.setTextPen(pg.mkPen(Colors.TEXT_MUTED))
        tr_bot.setPen(pg.mkPen(Colors.BORDER))

        # Reference lines at 30 / 70
        for y_ref in (30, 70):
            self._tr_plot_widget.addItem(pg.InfiniteLine(
                pos=y_ref, angle=0,
                pen=pg.mkPen(Colors.BORDER, width=1,
                             style=Qt.PenStyle.DashLine),
            ))

        # Threshold line — position updated via setPos(), pen updated via
        # setPen() on each selection; the object itself is never recreated.
        self._tr_threshold_line = pg.InfiniteLine(
            pos=70, angle=0,
            pen=pg.mkPen(Colors.ACCENT, width=1,
                         style=Qt.PenStyle.DashLine),
        )
        self._tr_plot_widget.addItem(self._tr_threshold_line)

        # Single data curve — pen updated on each selection.
        self._tr_plot_curve = self._tr_plot_widget.plot(
            [], [], pen=pg.mkPen(Colors.ACCENT, width=2), antialias=True
        )

        vbox.addWidget(self._tr_plot_widget)
        vbox.addStretch()

        outer.setWidget(inner)
        return outer

    # ── Tab switching ─────────────────────────────────────────────────────────

    def _show_sessions_tab(self) -> None:
        self._tab_sessions.setChecked(True)
        self._tab_training.setChecked(False)
        self._filter_row.hide()
        self._list_stack.setCurrentIndex(0)

    def _show_training_tab(self) -> None:
        self._tab_sessions.setChecked(False)
        self._tab_training.setChecked(True)
        self._filter_row.show()
        self._list_stack.setCurrentIndex(1)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        metric_filter: str | None = self._metric_combo.currentData()

        sessions = self._db.get_sessions(limit=100, user_id=self._user_id)
        training = self._db.get_training_history(
            target_metric=metric_filter, limit=100, user_id=self._user_id
        )

        self._populate_sessions(sessions)
        self._populate_training(training)

        # Clear the detail panel — the previously selected item no longer exists.
        self._sel_session_row  = None
        self._sel_training_row = None
        self._detail_stack.setCurrentIndex(0)

    def _populate_sessions(self, sessions) -> None:
        # Null the selection pointer BEFORE clearing so we never access a
        # widget that has been handed to deleteLater().
        self._sel_session_row = None

        lay = self._sessions_list_layout
        # Remove the trailing stretch before clearing items.
        stretch_item = lay.takeAt(lay.count() - 1) if lay.count() else None  # noqa: F841

        _clear_layout(lay)

        if not sessions:
            lay.addWidget(_empty_hint("No sessions recorded yet."))
        else:
            for row in sessions:
                lay.addWidget(_SessionItem(row, self._on_session_clicked))

        lay.addStretch()

    def _populate_training(self, training) -> None:
        self._sel_training_row = None

        lay = self._training_list_layout
        stretch_item = lay.takeAt(lay.count() - 1) if lay.count() else None  # noqa: F841

        _clear_layout(lay)

        if not training:
            lay.addWidget(_empty_hint("No training sessions yet."))
        else:
            for row in training:
                lay.addWidget(_TrainingItem(row, self._on_training_clicked))

        lay.addStretch()

    # ── Item selection ────────────────────────────────────────────────────────

    def _on_session_clicked(self, item: _SessionItem) -> None:
        if self._sel_session_row is not None:
            self._sel_session_row.set_active(False)
        self._sel_session_row = item
        item.set_active(True)
        self._show_session_detail(item._row)

    def _on_training_clicked(self, item: _TrainingItem) -> None:
        if self._sel_training_row is not None:
            self._sel_training_row.set_active(False)
        self._sel_training_row = item
        item.set_active(True)
        self._show_training_detail(item._row)

    # ── Detail population ─────────────────────────────────────────────────────

    def _show_session_detail(self, row) -> None:
        # Header
        self._sess_date_lbl.setText(_fmt_date(row["started_at"]))
        src = row["source_name"] or "Unknown"
        dur = _fmt_duration(row["started_at"], row["ended_at"])
        cnt = int(row["reading_count"] or 0)
        self._sess_meta_lbl.setText(f"{src}  ·  {dur}  ·  {cnt} readings")

        # Note
        note = (row["note"] or "").strip()
        if note:
            self._sess_note_lbl.setText(note)
            self._sess_note_frame.show()
        else:
            self._sess_note_frame.hide()

        # Metric averages
        _clear_layout(self._sess_bars_layout)
        for key, label, color, *_ in METRICS:
            val = row[f"avg_{key}"]
            self._sess_bars_layout.addWidget(_MetricBar(key, label, color, val))

        # Chart — load readings and repaint all currently active curves.
        self._session_readings = self._db.get_session_readings(row["id"])
        self._update_curves()

        self._detail_stack.setCurrentIndex(1)

    def _show_training_detail(self, row) -> None:
        metric = row["target_metric"] or "focus"
        # Use the explicit helper — avoids any generator-unpacking ambiguity.
        color  = Colors.metric(metric)
        label  = next((lb for k, lb, *_ in METRICS if k == metric), metric.title())

        thr = float(row["target_threshold"] or 0)
        dur = _fmt_duration(row["started_at"], row["ended_at"])
        sot = _fmt_seconds(row["seconds_on_target"])

        # ── Header ────────────────────────────────────────────────────────────
        self._tr_date_lbl.setText(_fmt_date(row["started_at"]))
        self._tr_meta_lbl.setText(
            f"{metric.upper()}  ·  target ≥ {thr:.0f}  ·  {dur}  ·  {sot} on target"
        )

        # ── Stats cards ───────────────────────────────────────────────────────
        _clear_layout(self._tr_stats_layout)
        for card_label, value, card_color in [
            ("Duration",  dur,            Colors.TEXT_PRIMARY),
            ("On Target", sot,            color),
            ("Threshold", f"≥ {thr:.0f}", color),
        ]:
            card = QWidget()
            card.setStyleSheet(
                f"background: {Colors.BG_CARD}; border-radius: 10px;"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)
            cl.setSpacing(4)
            lbl_w = QLabel(card_label.upper())
            lbl_w.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-size: 9px; "
                f"font-weight: 700; letter-spacing: 1px;"
            )
            val_w = QLabel(value)
            val_w.setStyleSheet(
                f"color: {card_color}; font-size: 20px; font-weight: 700;"
            )
            cl.addWidget(lbl_w)
            cl.addWidget(val_w)
            self._tr_stats_layout.addWidget(card)
        self._tr_stats_layout.addStretch()

        # ── Note ──────────────────────────────────────────────────────────────
        note = (row["note"] or "").strip()
        if note:
            self._tr_note_lbl.setText(note)
            self._tr_note_frame.show()
        else:
            self._tr_note_frame.hide()

        # ── Single-metric average bar ─────────────────────────────────────────
        # Fetch readings once; reuse for both the bar and the chart.
        self._training_readings = self._db.get_training_session_readings(row["id"])

        _clear_layout(self._tr_bar_layout)
        if self._training_readings:
            vals = [
                float(r[metric])
                for r in self._training_readings
                if r[metric] is not None
            ]
            avg = sum(vals) / len(vals) if vals else None
            self._tr_bar_layout.addWidget(_MetricBar(metric, label, color, avg))
        else:
            self._tr_bar_layout.addWidget(
                _empty_hint("No readings recorded during this session.")
            )

        # ── Chart — update curve pen, threshold line, and data ────────────────
        self._tr_plot_curve.setPen(pg.mkPen(color, width=2))
        self._tr_threshold_line.setPen(
            pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine)
        )
        self._tr_threshold_line.setPos(thr)

        if self._training_readings:
            y_raw = [
                r[metric] if r[metric] is not None else math.nan
                for r in self._training_readings
            ]
            x = np.arange(len(y_raw), dtype=float)
            y = np.array(y_raw, dtype=float)
            self._tr_plot_curve.setData(x, y)
            self._tr_plot_widget.setXRange(0, float(x[-1]), padding=0.02)
        else:
            self._tr_plot_curve.setData([], [])

        self._detail_stack.setCurrentIndex(2)

    # ── Chart helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _pill_style(color: str, active: bool) -> str:
        # Never append hex digits to a color string — Qt parses 8-digit hex
        # as #AARRGGBB (alpha first), yielding completely wrong colours.
        # Use rgba() which is unambiguous.
        # Do NOT use QPushButton:checked here: without an explicit :checked
        # rule the platform theme injects its own colour (often green on GTK).
        # We manage active state entirely through setStyleSheet().
        if active:
            return (
                f"QPushButton {{"
                f" background: {_rgba(color, 0.15)};"
                f" color: {color};"
                f" border: 1px solid {_rgba(color, 0.50)};"
                f" border-radius: 5px;"
                f" font-size: 10px; font-weight: 700; padding: 0 10px; }}"
                f"QPushButton:hover {{"
                f" background: {_rgba(color, 0.25)}; }}"
                # Explicit :checked rule prevents the platform theme from
                # overriding the colours when the button is in checked state.
                f"QPushButton:checked {{"
                f" background: {_rgba(color, 0.15)};"
                f" color: {color};"
                f" border: 1px solid {_rgba(color, 0.50)}; }}"
            )
        return (
            f"QPushButton {{"
            f" background: transparent; color: {Colors.TEXT_MUTED};"
            f" border: 1px solid {Colors.BORDER}; border-radius: 5px;"
            f" font-size: 10px; font-weight: 500; padding: 0 10px; }}"
            f"QPushButton:hover {{"
            f" border-color: {_rgba(color, 0.40)}; color: {color}; }}"
            f"QPushButton:checked {{"
            f" background: {_rgba(color, 0.15)};"
            f" color: {color};"
            f" border: 1px solid {_rgba(color, 0.50)}; }}"
        )

    def _on_pill_clicked(self) -> None:
        """Toggle one metric in/out of the active set and refresh the chart."""
        btn = self.sender()
        if btn is None:
            return
        key = btn.property("metric_key")
        if not key:
            return
        color = btn.property("metric_color")

        # Toggle membership in the active set.
        if key in self._active_metrics:
            self._active_metrics.discard(key)
        else:
            self._active_metrics.add(key)

        # Sync the pill's visual state (checked state already flipped by Qt).
        btn.setStyleSheet(self._pill_style(color, active=(key in self._active_metrics)))

        self._update_curves()

    def _update_curves(self) -> None:
        """
        Push fresh data to every curve based on _active_metrics.

        Active metrics get their readings array; inactive ones get empty arrays
        (setData([], []) hides the curve without removing it from the plot —
        the PlotDataItem stays in the plot's item list for the screen's entire
        lifetime, so there is no item-tree churn and no memory leak).
        """
        if not self._session_readings:
            for curve in self._plot_curves.values():
                curve.setData([], [])
            return

        n = len(self._session_readings)
        x = np.arange(n, dtype=float)
        max_x = float(x[-1]) if n else 1.0

        for key, curve in self._plot_curves.items():
            if key in self._active_metrics:
                y_raw = [
                    r[key] if r[key] is not None else math.nan
                    for r in self._session_readings
                ]
                curve.setData(x, np.array(y_raw, dtype=float))
            else:
                curve.setData([], [])

        self._plot_widget.setXRange(0, max_x, padding=0.02)

    # ── Metric filter (training tab) ──────────────────────────────────────────

    def _on_metric_filter_changed(self, _index: int) -> None:
        if not self._loaded:
            return
        metric_filter: str | None = self._metric_combo.currentData()
        training = self._db.get_training_history(
            target_metric=metric_filter, limit=100, user_id=self._user_id
        )
        self._populate_training(training)
        # Detail panel is stale — reset to placeholder.
        self._detail_stack.setCurrentIndex(0)

    # ── Qt events ─────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Force-reload all data from the database."""
        self._loaded = True
        self._load()
