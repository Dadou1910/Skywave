from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QSlider, QFrame, QStackedWidget,
)
from frontend.styles import Colors, ACCENT_BTN
from frontend.widgets.chart_widget import ChartWidget
from frontend.widgets.metric_card import MetricCard
from frontend.screens.monitor_screen import _ask_note
from backend.engine import METRICS
from backend.sound import SoundAlert

METRIC_DIRECTION = {
    "focus":   "above",
    "relax":   "above",
    "stress":  "below",
    "flow":    "above",
    "fatigue": "below",
}
THRESHOLD_LABEL = {
    "above": "Alert when below",
    "below": "Alert when above",
}


class TrainingScreen(QWidget):

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self._engine    = engine
        self._key       = METRICS[0][0]
        self._threshold = 70
        self._secs_on   = 0
        self._secs_tot  = 0
        self._on_target = False
        self._sound     = SoundAlert()
        self._charts: dict[str, ChartWidget] = {}
        self._cards:  dict[str, MetricCard]  = {}
        self._build_ui()
        self._engine.new_scores.connect(self._on_scores, Qt.ConnectionType.QueuedConnection)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(0)

        title = QLabel("Training Mode")
        title.setStyleSheet("font-size: 22px; font-weight: 700; letter-spacing: -0.5px;")
        root.addWidget(title)
        root.addSpacing(4)
        sub = QLabel("Focus on a mental state. Get real-time feedback when you enter or leave the target zone.")
        sub.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        root.addWidget(sub)
        root.addSpacing(24)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(24)

        mc = QVBoxLayout()
        mc.setSpacing(6)
        mc.addWidget(_micro("Target metric"))
        self._combo = QComboBox()
        for key, label, *_ in METRICS:
            self._combo.addItem(label, key)
        self._combo.setFixedWidth(150)
        self._combo.currentIndexChanged.connect(self._metric_changed)
        mc.addWidget(self._combo)
        ctrl.addLayout(mc)

        tc = QVBoxLayout()
        tc.setSpacing(6)
        self._thresh_lbl = _micro(f"Alert when below: {self._threshold}")
        tc.addWidget(self._thresh_lbl)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(10, 90)
        self._slider.setValue(self._threshold)
        self._slider.setFixedWidth(220)
        self._slider.valueChanged.connect(self._thresh_changed)
        tc.addWidget(self._slider)
        ctrl.addLayout(tc)

        ctrl.addStretch()

        self._start_btn = QPushButton("Start Training")
        self._start_btn.setStyleSheet(ACCENT_BTN)
        self._start_btn.setFixedSize(148, 36)
        self._start_btn.clicked.connect(self._toggle)
        ctrl.addWidget(self._start_btn, alignment=Qt.AlignmentFlag.AlignBottom)
        root.addLayout(ctrl)
        root.addSpacing(24)

        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {Colors.BORDER};")
        root.addWidget(div)
        root.addSpacing(24)

        live = QHBoxLayout()
        live.setSpacing(32)

        left = QVBoxLayout()
        left.setSpacing(0)

        self._big = QLabel("—")
        self._big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._big.setStyleSheet(
            f"font-size: 96px; font-weight: 800; color: {Colors.TEXT_MUTED}; letter-spacing: -4px;"
        )
        left.addWidget(self._big)

        self._metric_lbl = QLabel("FOCUS")
        self._metric_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._metric_lbl.setStyleSheet(
            f"color: {Colors.FOCUS}; font-size: 11px; font-weight: 700; letter-spacing: 3px;"
        )
        left.addWidget(self._metric_lbl)
        left.addSpacing(20)

        self._banner = _Banner()
        left.addWidget(self._banner)
        left.addSpacing(24)

        stats = QHBoxLayout()
        stats.setSpacing(0)
        self._w_on    = _StatBlock("On target")
        self._w_total = _StatBlock("Elapsed")
        self._w_ratio = _StatBlock("Ratio")
        for w in (self._w_on, _Divider(), self._w_total, _Divider(), self._w_ratio):
            stats.addWidget(w)
        stats.addStretch()
        left.addLayout(stats)
        left.addStretch()
        live.addLayout(left, 5)

        right = QVBoxLayout()
        right.setSpacing(4)

        self._card_stack  = QStackedWidget()
        self._chart_stack = QStackedWidget()
        self._card_stack.setStyleSheet("background: transparent;")
        self._chart_stack.setStyleSheet("background: transparent;")
        self._chart_stack.setFixedHeight(180)

        for i, (key, *_) in enumerate(METRICS):
            card  = MetricCard(key)
            chart = ChartWidget(key, height=180)
            self._cards[key]  = card
            self._charts[key] = chart
            self._card_stack.addWidget(card)
            self._chart_stack.addWidget(chart)

        right.addWidget(self._card_stack)
        right.addWidget(self._chart_stack)
        right.addStretch()
        live.addLayout(right, 6)

        root.addLayout(live)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self._sync_stack()

    def _sync_stack(self):
        idx = next(i for i, (k, *_) in enumerate(METRICS) if k == self._key)
        self._card_stack.setCurrentIndex(idx)
        self._chart_stack.setCurrentIndex(idx)

    def _on_scores(self, pkt):
        if pkt.is_warmup:
            return
        score = pkt.scores.get(self._key)
        self._cards[self._key].update_score(score)
        self._charts[self._key].push(score)
        if score is None:
            return
        color = Colors.metric(self._key)
        self._big.setText(str(int(score)))
        self._big.setStyleSheet(
            f"font-size: 96px; font-weight: 800; color: {color}; letter-spacing: -4px;"
        )
        if self._engine.training_active:
            direction = METRIC_DIRECTION.get(self._key, "above")
            on = score >= self._threshold if direction == "above" else score <= self._threshold
            if on and not self._on_target:
                self._sound.play_enter()
            elif not on and self._on_target:
                self._sound.play_exit()
            self._banner.set_state(on, score, self._threshold, direction)
            self._on_target = on

    def _metric_changed(self, idx):
        self._key = self._combo.itemData(idx)
        color = Colors.metric(self._key)
        self._metric_lbl.setText(self._combo.currentText().upper())
        self._metric_lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: 700; letter-spacing: 3px;"
        )
        direction = METRIC_DIRECTION.get(self._key, "above")
        self._thresh_lbl.setText(f"{THRESHOLD_LABEL[direction]}: {self._threshold}")
        self._big.setText("—")
        self._big.setStyleSheet(
            f"font-size: 96px; font-weight: 800; color: {Colors.TEXT_MUTED}; letter-spacing: -4px;"
        )
        self._banner.set_idle()
        self._sync_stack()

    def _thresh_changed(self, v):
        self._threshold = v
        direction = METRIC_DIRECTION.get(self._key, "above")
        self._thresh_lbl.setText(f"{THRESHOLD_LABEL[direction]}: {v}")

    def _toggle(self):
        if not self._engine.training_active:
            self._secs_on = self._secs_tot = 0
            self._engine.start_training(self._key, self._threshold)
            self._start_btn.setText("Stop Training")
            self._start_btn.setStyleSheet(
                f"background: {Colors.DANGER}33; border: 1px solid {Colors.DANGER}66; "
                f"color: {Colors.DANGER}; font-weight: 600; border-radius: 8px;"
            )
            self._combo.setEnabled(False)
            self._slider.setEnabled(False)
            self._timer.start(1000)
        else:
            note = _ask_note(self)
            self._engine.stop_training(note)
            self._start_btn.setText("Start Training")
            self._start_btn.setStyleSheet(ACCENT_BTN)
            self._combo.setEnabled(True)
            self._slider.setEnabled(True)
            self._timer.stop()
            self._banner.set_idle()

    def _tick(self):
        self._secs_tot += 1
        if self._on_target:
            self._secs_on += 1
        self._w_on.set_value(f"{self._secs_on}s")
        self._w_total.set_value(f"{self._secs_tot}s")
        if self._secs_tot:
            self._w_ratio.set_value(f"{self._secs_on/self._secs_tot*100:.0f}%")


def _micro(text):
    l = QLabel(text)
    l.setStyleSheet(
        f"color: {Colors.TEXT_MUTED}; font-size: 10px; font-weight: 600; letter-spacing: 0.5px;"
    )
    return l


class _Banner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setStyleSheet(f"background: {Colors.BG_SURFACE}; border-radius: 10px;")
        l = QHBoxLayout(self)
        l.setContentsMargins(20, 0, 20, 0)
        self._lbl = QLabel("Start training to begin")
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 13px; font-weight: 500;")
        l.addWidget(self._lbl)

    def set_state(self, on, score, threshold, direction="above"):
        if on:
            self.setStyleSheet(f"background: {Colors.SUCCESS}18; border-radius: 10px; border: 1px solid {Colors.SUCCESS}40;")
            msg = f"✓  on target  ·  {score:.0f} {'≥' if direction == 'above' else '≤'} {threshold}"
            self._lbl.setText(msg)
            self._lbl.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 13px; font-weight: 600;")
        else:
            self.setStyleSheet(f"background: {Colors.DANGER}18; border-radius: 10px; border: 1px solid {Colors.DANGER}40;")
            msg = f"{'↓ below' if direction == 'above' else '↑ above'} target  ·  {score:.0f} {'<' if direction == 'above' else '>'} {threshold}"
            self._lbl.setText(msg)
            self._lbl.setStyleSheet(f"color: {Colors.DANGER}; font-size: 13px; font-weight: 600;")

    def set_idle(self):
        self.setStyleSheet(f"background: {Colors.BG_SURFACE}; border-radius: 10px;")
        self._lbl.setText("Start training to begin")
        self._lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 13px; font-weight: 500;")


class _StatBlock(QWidget):
    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.setFixedWidth(90)
        l = QVBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(3)
        lb = QLabel(label.upper())
        lb.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px; letter-spacing: 0.8px;")
        self._val = QLabel("—")
        self._val.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: 22px; font-weight: 700;")
        l.addWidget(lb)
        l.addWidget(self._val)

    def set_value(self, v):
        self._val.setText(v)


class _Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(1, 36)
        self.setStyleSheet(f"background: {Colors.BORDER};")
        self.setContentsMargins(12, 0, 12, 0)
