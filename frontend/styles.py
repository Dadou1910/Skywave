from PyQt6.QtGui import QFont


# ── Palette ───────────────────────────────────────────────────────────────────
class Colors:
    BG_APP       = "#0d0d0f"   # outermost background
    BG_SIDEBAR   = "#111114"   # left nav
    BG_CARD      = "#18181c"   # metric cards, panels
    BG_SURFACE   = "#1e1e24"   # slightly elevated surfaces
    BG_INPUT     = "#26262e"   # inputs, sliders

    BORDER       = "#2a2a35"
    BORDER_LIGHT = "#3a3a48"

    TEXT_PRIMARY   = "#f0f0f5"
    TEXT_SECONDARY = "#a8a8b4"
    TEXT_MUTED     = "#76767f"

    ACCENT       = "#7F77DD"   # matches focus colour — used for active nav etc.
    DANGER       = "#D85A30"
    SUCCESS      = "#1D9E75"
    WARNING      = "#EF9F27"

    # Per-metric
    FOCUS   = "#7F77DD"
    RELAX   = "#1D9E75"
    STRESS  = "#D85A30"
    FLOW    = "#EF9F27"
    FATIGUE = "#378ADD"

    @staticmethod
    def metric(key: str) -> str:
        return {
            "focus":   Colors.FOCUS,
            "relax":   Colors.RELAX,
            "stress":  Colors.STRESS,
            "flow":    Colors.FLOW,
            "fatigue": Colors.FATIGUE,
        }.get(key, Colors.TEXT_PRIMARY)


# ── Typography ────────────────────────────────────────────────────────────────
class Fonts:
    @staticmethod
    def default(size: int = 10) -> QFont:
        f = QFont("Inter")
        f.setPixelSize(size)
        return f

    @staticmethod
    def mono(size: int = 10) -> QFont:
        f = QFont("JetBrains Mono, Fira Mono, monospace")
        f.setPixelSize(size)
        return f

    @staticmethod
    def title(size: int = 22) -> QFont:
        f = QFont("Inter")
        f.setPixelSize(size)
        f.setWeight(QFont.Weight.Bold)
        return f

    @staticmethod
    def label(size: int = 11) -> QFont:
        f = QFont("Inter")
        f.setPixelSize(size)
        f.setWeight(QFont.Weight.Medium)
        return f


# ── Reusable component styles ─────────────────────────────────────────────────
# Accent-tinted button — same rgba purple as the active nav pill.
# Use setStyleSheet(ACCENT_BTN) instead of setProperty("accent", True)
# when you want the softer tinted look (dark bg + purple text/border).
ACCENT_BTN = (
    "QPushButton {"
    " background: rgba(127, 119, 221, 0.10);"
    " border: 1px solid rgba(127, 119, 221, 0.28);"
    " border-radius: 8px;"
    " color: #7F77DD;"
    " font-weight: 600;"
    "}"
    "QPushButton:hover {"
    " background: rgba(127, 119, 221, 0.20);"
    " border-color: rgba(127, 119, 221, 0.50);"
    "}"
)

# ── Global stylesheet ─────────────────────────────────────────────────────────
# Applied once to QApplication — all widgets inherit from this.
GLOBAL_STYLESHEET = f"""
* {{
    font-family: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    color: {Colors.TEXT_PRIMARY};
    outline: none;
}}

QMainWindow, QWidget {{
    background-color: {Colors.BG_APP};
}}

QLabel {{
    background: transparent;
    color: {Colors.TEXT_PRIMARY};
}}

QPushButton {{
    background-color: {Colors.BG_SURFACE};
    border: 1px solid {Colors.BORDER};
    border-radius: 6px;
    padding: 8px 18px;
    font-size: 13px;
    color: {Colors.TEXT_PRIMARY};
}}
QPushButton:hover {{
    background-color: {Colors.BG_INPUT};
    border-color: {Colors.BORDER_LIGHT};
}}
QPushButton:pressed {{
    background-color: {Colors.BG_CARD};
}}
QPushButton:disabled {{
    color: {Colors.TEXT_MUTED};
    border-color: {Colors.BORDER};
}}

QPushButton[accent="true"] {{
    background-color: {Colors.ACCENT};
    border: none;
    color: white;
    font-weight: 600;
}}
QPushButton[accent="true"]:hover {{
    background-color: #9490e8;
}}
QPushButton[accent="true"]:pressed {{
    background-color: #6b64c4;
}}

QSlider::groove:horizontal {{
    background: {Colors.BG_INPUT};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {Colors.ACCENT};
    width: 14px;
    height: 14px;
    border-radius: 7px;
    margin: -5px 0;
}}
QSlider::sub-page:horizontal {{
    background: {Colors.ACCENT};
    border-radius: 2px;
}}

QComboBox {{
    background-color: {Colors.BG_INPUT};
    border: 1px solid {Colors.BORDER};
    border-radius: 6px;
    padding: 6px 12px;
    color: {Colors.TEXT_PRIMARY};
    font-size: 13px;
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background-color: {Colors.BG_SURFACE};
    border: 1px solid {Colors.BORDER};
    selection-background-color: {Colors.BG_INPUT};
    color: {Colors.TEXT_PRIMARY};
}}

QScrollBar:vertical {{
    background: {Colors.BG_APP};
    width: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {Colors.BORDER_LIGHT};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QScrollBar:horizontal {{
    background: {Colors.BG_APP};
    height: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:horizontal {{
    background: {Colors.BORDER_LIGHT};
    border-radius: 3px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QSplitter::handle {{
    background: {Colors.BORDER};
}}

QToolTip {{
    background-color: {Colors.BG_SURFACE};
    border: 1px solid {Colors.BORDER};
    color: {Colors.TEXT_PRIMARY};
    padding: 4px 8px;
    border-radius: 4px;
}}
"""
