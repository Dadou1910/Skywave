from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame,
    QDialog, QPlainTextEdit,
)

from frontend.styles import Colors, ACCENT_BTN
from frontend.widgets.chart_widget import ChartWidget
from frontend.widgets.metric_card import MetricCard
from backend.engine import METRICS, WARMUP_PACKETS


class MonitorScreen(QWidget):

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self._engine  = engine
        self._running = False

        self._charts: dict[str, ChartWidget]  = {}
        self._cards:  dict[str, MetricCard]   = {}

        self._build_ui()
        self._engine.new_scores.connect(self._on_scores, Qt.ConnectionType.QueuedConnection)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(0)

        top = QHBoxLayout()

        title = QLabel("Live Monitor")
        title.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #f0f0f5;"
        )
        top.addWidget(title)
        top.addStretch()

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px;")
        top.addWidget(self._status_dot)
        self._status_lbl = QLabel("connecting...")
        self._status_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 12px; margin-left: 6px;"
        )
        top.addWidget(self._status_lbl)
        top.addSpacing(16)

        self._signal_dot = QLabel("◉")
        self._signal_dot.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px;")
        top.addWidget(self._signal_dot)
        self._signal_lbl = QLabel("no signal")
        self._signal_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11px; margin-left: 4px;"
        )
        top.addWidget(self._signal_lbl)
        top.addSpacing(20)

        self._rec_btn = QPushButton("● Start Recording")
        self._rec_btn.setStyleSheet(ACCENT_BTN)
        self._rec_btn.setFixedHeight(34)
        self._rec_btn.clicked.connect(self._toggle_recording)
        top.addWidget(self._rec_btn)

        root.addLayout(top)
        root.addSpacing(20)

        self._warmup_bar = _WarmupBanner(WARMUP_PACKETS)
        self._warmup_bar.setVisible(True)
        root.addWidget(self._warmup_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setStyleSheet(f"background: {Colors.BG_APP};")
        charts_layout = QVBoxLayout(inner)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.setSpacing(12)

        for key, label, color, low_desc, high_desc in METRICS:
            card = MetricCard(key)
            self._cards[key] = card
            charts_layout.addWidget(card)

            chart = ChartWidget(key)
            self._charts[key] = chart
            charts_layout.addWidget(chart)

            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"color: {Colors.BORDER};")
            sep.setFixedHeight(1)
            charts_layout.addWidget(sep)

        charts_layout.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll)

        info = QHBoxLayout()
        self._session_lbl = QLabel("No active session")
        self._session_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 10px;"
        )
        info.addWidget(self._session_lbl)
        info.addStretch()
        root.addSpacing(8)
        root.addLayout(info)

        self._conn_timer = QTimer(self)
        self._conn_timer.timeout.connect(self._update_status)
        self._conn_timer.start(2000)
        self._update_status()

    def _on_scores(self, pkt) -> None:
        self._update_signal_quality(pkt.signal_quality)

        if pkt.is_warmup:
            self._warmup_bar.set_count(pkt.warmup_count)
            self._warmup_bar.setVisible(True)
            return

        self._warmup_bar.setVisible(False)

        for key, *_ in METRICS:
            score = pkt.scores.get(key)
            self._cards[key].update_score(score)
            self._charts[key].push(score, pkt.blink)

    def _toggle_recording(self) -> None:
        if not self._engine.session_active:
            self._engine.begin_session()
            self._rec_btn.setText("■ Stop Recording")
            self._rec_btn.setStyleSheet(
                f"background: {Colors.DANGER}; border: none; "
                f"color: white; font-weight: 600; border-radius: 6px;"
            )
            self._session_lbl.setText("Recording in progress...")
        else:
            note = _ask_note(self)
            self._engine.end_session(note)
            self._rec_btn.setText("● Start Recording")
            self._rec_btn.setStyleSheet(ACCENT_BTN)
            self._session_lbl.setText("Session saved.")

    def _update_signal_quality(self, quality: int) -> None:
        if quality == -1:
            return
        if quality == 200:
            color = Colors.DANGER
            text  = "no electrode contact"
        elif quality == 0:
            color = Colors.SUCCESS
            text  = "signal: perfect"
        elif quality < 50:
            color = Colors.SUCCESS
            text  = f"signal: good  ({quality}/200)"
        else:
            color = Colors.WARNING
            text  = f"signal: poor  ({quality}/200)"
        self._signal_dot.setStyleSheet(f"color: {color}; font-size: 10px;")
        self._signal_lbl.setStyleSheet(f"color: {color}; font-size: 11px; margin-left: 4px;")
        self._signal_lbl.setText(text)

    def _update_status(self) -> None:
        if self._engine.is_connected():
            self._status_dot.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 10px;")
            self._status_lbl.setText("connected")
        else:
            self._status_dot.setStyleSheet(f"color: {Colors.DANGER}; font-size: 10px;")
            self._status_lbl.setText("connecting…")


class _WarmupBanner(QWidget):

    def __init__(self, total: int, parent=None):
        super().__init__(parent)
        self._total = total
        self.setFixedHeight(44)
        self.setStyleSheet(
            f"background: {Colors.BG_SURFACE}; border-radius: 8px;"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)

        self._lbl = QLabel(f"Calibrating...  (0 / {total} packets)")
        self._lbl.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 12px;"
        )
        layout.addWidget(self._lbl)
        layout.addStretch()

        hint = QLabel("sit still and relax — establishing your personal baseline")
        hint.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 10px; font-style: italic;"
        )
        layout.addWidget(hint)

    def set_count(self, count: int) -> None:
        self._lbl.setText(f"Calibrating...  ({count} / {self._total} packets)")


def _ask_note(parent) -> str:
    dlg = QDialog(parent)
    dlg.setWindowTitle("Session note")
    dlg.setFixedWidth(420)
    dlg.setStyleSheet(f"background: {Colors.BG_SURFACE}; color: #f0f0f5;")

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setSpacing(12)

    lbl = QLabel("Add a note to this session  (optional)")
    lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
    layout.addWidget(lbl)

    hint = QLabel('e.g.  "coding sprint"  ·  "morning meditation"  ·  "post-workout"')
    hint.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; font-style: italic;")
    layout.addWidget(hint)

    text = QPlainTextEdit()
    text.setFixedHeight(72)
    text.setPlaceholderText("What were you doing?")
    text.setStyleSheet(
        f"background: {Colors.BG_APP}; color: #f0f0f5; "
        f"border: 1px solid {Colors.BORDER}; border-radius: 6px; "
        f"padding: 6px; font-size: 12px;"
    )
    layout.addWidget(text)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)
    btn_row.addStretch()

    cancel = QPushButton("Cancel")
    cancel.setFixedHeight(32)
    cancel.setStyleSheet(
        f"QPushButton {{ background: transparent; border: 1px solid {Colors.BORDER}; "
        f"border-radius: 6px; color: {Colors.TEXT_MUTED}; font-size: 12px; padding: 0 16px; }}"
        f"QPushButton:hover {{ border-color: {Colors.TEXT_SECONDARY}; color: {Colors.TEXT_PRIMARY}; }}"
    )
    cancel.clicked.connect(dlg.reject)

    save = QPushButton("Save note")
    save.setFixedHeight(32)
    save.setStyleSheet(
        f"QPushButton {{ background: {Colors.ACCENT}; border: none; "
        f"border-radius: 6px; color: white; font-size: 12px; font-weight: 600; padding: 0 20px; }}"
        f"QPushButton:hover {{ background: {Colors.ACCENT}cc; }}"
    )
    save.clicked.connect(dlg.accept)

    btn_row.addWidget(cancel)
    btn_row.addWidget(save)
    layout.addLayout(btn_row)

    if dlg.exec() == QDialog.DialogCode.Accepted:
        return text.toPlainText().strip()
    return ""
