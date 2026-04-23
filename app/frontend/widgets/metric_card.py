from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
)
from PyQt6.QtGui import QColor

from frontend.styles import Colors
from backend.engine import METRICS


class MetricCard(QWidget):

    def __init__(self, metric_key: str, parent=None):
        super().__init__(parent)

        meta = next(m for m in METRICS if m[0] == metric_key)
        _, label, color, low_desc, high_desc = meta

        self._color    = color
        self._key      = metric_key
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(0)

        bar = QFrame()
        bar.setFixedWidth(4)
        bar.setStyleSheet(f"background: {color}; border-radius: 2px;")
        layout.addWidget(bar)
        layout.addSpacing(10)

        name_lbl = QLabel(label.upper())
        name_lbl.setFixedWidth(70)
        name_lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: 700; "
            f"letter-spacing: 1px;"
        )
        layout.addWidget(name_lbl)
        layout.addSpacing(8)

        low_lbl = QLabel(f"low: {low_desc}")
        low_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-style: italic;"
        )
        layout.addWidget(low_lbl)

        layout.addStretch()

        high_lbl = QLabel(f"high: {high_desc}")
        high_lbl.setStyleSheet(
            f"color: {color}; font-size: 9px; font-style: italic; opacity: 0.7;"
        )
        layout.addWidget(high_lbl)
        layout.addSpacing(24)

        self._score_lbl = QLabel("—")
        self._score_lbl.setFixedWidth(34)
        self._score_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._score_lbl.setStyleSheet(
            f"color: {color}; font-size: 15px; font-weight: 700;"
        )
        layout.addWidget(self._score_lbl)
        layout.addSpacing(8)

        self._tag_lbl = QLabel("")
        self._tag_lbl.setFixedWidth(120)
        self._tag_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._tag_lbl.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;"
        )
        layout.addWidget(self._tag_lbl)

        self.setStyleSheet(f"background: transparent;")

    def update_score(self, score: float | None) -> None:
        if score is None:
            self._score_lbl.setText("—")
            self._tag_lbl.setText("")
            return

        self._score_lbl.setText(str(int(score)))

        if score < 30:
            tag   = _low_tag(self._key)
            color = Colors.TEXT_SECONDARY
        elif score > 70:
            tag   = _high_tag(self._key)
            color = self._color
        else:
            tag   = "neutral"
            color = Colors.TEXT_MUTED

        self._tag_lbl.setText(tag)
        self._tag_lbl.setStyleSheet(
            f"color: {color}; font-size: 10px;"
        )


_LOW_TAGS = {
    "focus":   "mind wandering",
    "relax":   "tense",
    "stress":  "calm",
    "flow":    "scattered",
    "fatigue": "fresh",
}
_HIGH_TAGS = {
    "focus":   "focused",
    "relax":   "relaxed",
    "stress":  "stressed",
    "flow":    "in the zone",
    "fatigue": "tired",
}

def _low_tag(key: str)  -> str: return _LOW_TAGS.get(key,  "low")
def _high_tag(key: str) -> str: return _HIGH_TAGS.get(key, "high")
