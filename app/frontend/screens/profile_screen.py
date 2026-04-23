"""
ProfileScreen — per-user statistics, cognitive profile, and account management.
Accessed by clicking the user badge at the bottom-left of the sidebar.
"""

import math
from datetime import date, datetime
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen,
    QPainterPath, QPolygonF, QPixmap,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPushButton, QFileDialog, QMessageBox, QDialog,
)

from frontend.styles import Colors
from frontend.utils import fmt_seconds as _fmt_seconds
from backend.engine import METRICS
from backend.database import Database

_AVATAR_DIR = Path.home() / "skywave_data" / "avatars"


def _avatar_path(user_id: int) -> Path:
    return _AVATAR_DIR / f"{user_id}.png"


def _fmt_hour(h: int | None) -> str:
    if h is None:
        return "—"
    suffix = "am" if h < 12 else "pm"
    display = h if h <= 12 else h - 12
    display = display or 12
    return f"{display}{suffix}"


def _longest_streak(days: list[str]) -> int:
    if not days:
        return 0
    dates = sorted(set(date.fromisoformat(d) for d in days if d))
    if not dates:
        return 0
    longest = current = 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


def _brain_type(avgs: dict) -> tuple[str, str, str]:
    """Return (label, colour, description) based on average scores."""
    f = avgs.get("focus")   or 0
    r = avgs.get("relax")   or 0
    s = avgs.get("stress")  or 0
    w = avgs.get("flow")    or 0
    t = avgs.get("fatigue") or 0

    if f > 55 and s < 35:
        return ("Deep Concentrator", "#7F77DD",
                "Your brain sustains focused states with minimal cognitive tension — "
                "a hallmark of experienced practitioners and high-performers. "
                "Beta-wave engagement is strong while low-alpha stress markers stay quiet.")
    if r > 55 and s < 30:
        return ("Natural Meditator", "#1D9E75",
                "You access calm alpha and theta states with unusual ease. "
                "Your nervous system de-activates quickly, producing the relaxed "
                "waveform signature seen in long-term meditators.")
    if w > 48 and t < 40:
        return ("Creative Thinker", "#EF9F27",
                "Theta-based flow states appear naturally in your sessions, "
                "pointing to a brain that gravitates toward imaginative, "
                "associative processing — the signature of creative immersion.")
    if f > 50 and w > 42:
        return ("Peak Performer", "#7F77DD",
                "You combine focused beta engagement with theta-based flow — "
                "the dual-mode signature associated with elite cognitive performance, "
                "skilled problem-solving, and 'in-the-zone' states.")
    if s > 58:
        return ("High Arousal Mind", "#D85A30",
                "Your brain habitually runs in a high-arousal state. "
                "Elevated high-beta and stress markers suggest a fast-processing, "
                "highly activated cortex. Relaxation neurofeedback may help balance this.")
    if t > 55:
        return ("Recovery Mode", "#378ADD",
                "Delta and theta elevation suggests accumulated mental fatigue. "
                "Your brain is signalling a need for rest. "
                "Shorter sessions and sleep prioritisation will restore baseline performance.")
    return ("Balanced Brain", "#7F77DD",
            "Your metrics show a well-rounded cognitive profile without strong outliers — "
            "a versatile neural signature that adapts well across different task demands.")


# ── Avatar widget ─────────────────────────────────────────────────────────────

class _AvatarWidget(QWidget):
    """Circular avatar — shows photo or initial letter. Click to upload."""

    SIZE = 110

    def __init__(self, user_id: int, user_name: str, on_upload, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._user_id   = user_id
        self._user_name = user_name
        self._on_upload = on_upload
        self._pixmap: QPixmap | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click to upload profile photo")
        self._reload()

    def _reload(self) -> None:
        p = _avatar_path(self._user_id)
        self._pixmap = (
            QPixmap(str(p)).scaled(
                self.SIZE, self.SIZE,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ) if p.exists() else None
        )
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        S = self.SIZE

        if self._pixmap:
            clip = QPainterPath()
            clip.addEllipse(0, 0, S, S)
            p.setClipPath(clip)
            p.drawPixmap(0, 0, self._pixmap)
            p.setClipping(False)
        else:
            bg = QColor(Colors.ACCENT)
            bg.setAlphaF(0.18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawEllipse(0, 0, S, S)
            font = QFont("Inter")
            font.setPixelSize(44)
            font.setBold(True)
            p.setFont(font)
            p.setPen(QColor(Colors.ACCENT))
            p.drawText(0, 0, S, S, Qt.AlignmentFlag.AlignCenter,
                       (self._user_name[0].upper() if self._user_name else "?"))

        # Camera overlay badge (bottom-right)
        CS = 26
        cx, cy = S - CS - 2, S - CS - 2
        badge_bg = QColor("#111114")
        badge_bg.setAlphaF(0.88)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(badge_bg)
        p.drawEllipse(cx, cy, CS, CS)
        font2 = QFont("Inter")
        font2.setPixelSize(12)
        p.setFont(font2)
        p.setPen(QColor(Colors.TEXT_SECONDARY))
        p.drawText(cx, cy, CS, CS, Qt.AlignmentFlag.AlignCenter, "\u2295")
        p.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_upload()

    def refresh(self) -> None:
        self._reload()


# ── Radar chart ───────────────────────────────────────────────────────────────

class _RadarChart(QWidget):
    """Spider / radar chart for 5 EEG metrics."""

    SIZE = 210

    def __init__(self, values: dict, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._values = values   # {metric_key: 0–100}
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = cy = self.SIZE // 2
        R  = cx - 28   # leave room for labels
        n  = len(METRICS)

        def pt(i: int, radius_frac: float) -> QPointF:
            angle = math.pi / 2 - i * 2 * math.pi / n
            return QPointF(
                cx + radius_frac * R * math.cos(angle),
                cy - radius_frac * R * math.sin(angle),
            )

        # Concentric reference rings
        for frac in (0.25, 0.5, 0.75, 1.0):
            ring = QPolygonF([pt(i, frac) for i in range(n)])
            pen  = QPen(QColor(Colors.BORDER), 0.8)
            pen.setStyle(Qt.PenStyle.DotLine if frac < 1.0 else Qt.PenStyle.SolidLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPolygon(ring)

        # Axis spokes
        p.setPen(QPen(QColor(Colors.BORDER), 0.8))
        for i in range(n):
            p.drawLine(QPointF(cx, cy), pt(i, 1.0))

        # Data polygon
        vals = [min(1.0, (self._values.get(key) or 0) / 100) for key, *_ in METRICS]
        data_poly = QPolygonF([pt(i, vals[i]) for i in range(n)])
        fill = QColor(Colors.ACCENT)
        fill.setAlphaF(0.12)
        p.setBrush(fill)
        p.setPen(QPen(QColor(Colors.ACCENT), 1.5))
        p.drawPolygon(data_poly)

        # Metric dots and labels
        for i, (key, label, color, *_) in enumerate(METRICS):
            v = vals[i]
            dot = pt(i, v)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawEllipse(dot, 5, 5)

            lbl_pt = pt(i, 1.22)
            font = QFont("Inter")
            font.setPixelSize(10)
            font.setBold(True)
            p.setFont(font)
            p.setPen(QColor(color))
            p.drawText(
                int(lbl_pt.x()) - 28, int(lbl_pt.y()) - 8, 56, 16,
                Qt.AlignmentFlag.AlignCenter, label,
            )

        p.end()


# ── Mini bar (for score rows in interpretation panel) ─────────────────────────

class _MiniBar(QWidget):

    def __init__(self, label: str, value: float | None, color: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        l = QHBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(10)

        lbl = QLabel(label.upper())
        lbl.setFixedWidth(54)
        lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-weight: 700; letter-spacing: 0.8px;"
        )
        l.addWidget(lbl)

        track = QWidget()
        track.setFixedHeight(6)
        track.setStyleSheet(f"background: {Colors.BG_SURFACE}; border-radius: 3px;")
        track.setMinimumWidth(120)

        fill_pct = max(0.0, min(1.0, (value or 0) / 100))
        fill = QWidget(track)
        fill.setFixedHeight(6)
        fill.setStyleSheet(f"background: {color}; border-radius: 3px;")
        fill.setGeometry(0, 0, int(fill_pct * 140), 6)
        l.addWidget(track, 1)

        val_lbl = QLabel(f"{value:.0f}" if value is not None else "—")
        val_lbl.setFixedWidth(28)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        val_lbl.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 700;"
        )
        l.addWidget(val_lbl)


# ── Stat card ─────────────────────────────────────────────────────────────────

def _stat_card(label: str, value: str, color: str = Colors.TEXT_PRIMARY) -> QWidget:
    w = QWidget()
    w.setStyleSheet(f"background: {Colors.BG_CARD}; border-radius: 10px;")
    l = QVBoxLayout(w)
    l.setContentsMargins(16, 14, 16, 14)
    l.setSpacing(4)
    lbl = QLabel(label.upper())
    lbl.setStyleSheet(
        f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-weight: 700; letter-spacing: 1px;"
    )
    val = QLabel(value)
    val.setStyleSheet(
        f"color: {color}; font-size: 22px; font-weight: 700; letter-spacing: -0.5px;"
    )
    l.addWidget(lbl)
    l.addWidget(val)
    return w


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-weight: 700; letter-spacing: 1.5px;"
    )
    return lbl


# ── Profile screen ────────────────────────────────────────────────────────────

class ProfileScreen(QWidget):

    back_requested   = pyqtSignal()
    logout_requested = pyqtSignal()
    user_deleted     = pyqtSignal()

    def __init__(self, db: Database, user_id: int, user_name: str, parent=None):
        super().__init__(parent)
        self._db        = db
        self._user_id   = user_id
        self._user_name = user_name
        _AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        self._build_ui()
        self._load()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self._root = QVBoxLayout(inner)
        self._root.setContentsMargins(36, 24, 36, 36)
        self._root.setSpacing(0)

        # ── Top nav ───────────────────────────────────────────────────────────
        nav_row = QHBoxLayout()
        back_btn = QPushButton("\u2190 Back")
        back_btn.setFixedHeight(30)
        back_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; "
            f"color: {Colors.TEXT_MUTED}; font-size: 12px; }}"
            f"QPushButton:hover {{ color: {Colors.TEXT_PRIMARY}; }}"
        )
        back_btn.clicked.connect(self.back_requested)
        nav_row.addWidget(back_btn)
        nav_row.addStretch()
        self._root.addLayout(nav_row)
        self._root.addSpacing(16)

        # ── Hero card ─────────────────────────────────────────────────────────
        hero = QWidget()
        hero.setStyleSheet(
            f"background: {Colors.BG_CARD}; border-radius: 16px;"
        )
        hero_l = QHBoxLayout(hero)
        hero_l.setContentsMargins(28, 28, 28, 28)
        hero_l.setSpacing(24)

        self._avatar = _AvatarWidget(
            self._user_id, self._user_name, self._upload_photo
        )
        hero_l.addWidget(self._avatar, 0, Qt.AlignmentFlag.AlignTop)

        info_col = QVBoxLayout()
        info_col.setSpacing(6)
        info_col.setContentsMargins(0, 0, 0, 0)

        self._name_lbl = QLabel(self._user_name)
        self._name_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 26px; font-weight: 700; "
            f"letter-spacing: -0.5px;"
        )
        info_col.addWidget(self._name_lbl)

        self._type_badge = QLabel()
        self._type_badge.setFixedHeight(22)
        info_col.addWidget(self._type_badge)

        self._since_lbl = QLabel()
        self._since_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11px;"
        )
        info_col.addWidget(self._since_lbl)

        info_col.addSpacing(10)

        upload_btn = QPushButton("\u2295  Upload photo")
        upload_btn.setFixedHeight(26)
        upload_btn.setFixedWidth(130)
        upload_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {Colors.BORDER_LIGHT}; "
            f"border-radius: 6px; color: {Colors.TEXT_MUTED}; font-size: 10px; }}"
            f"QPushButton:hover {{ border-color: {Colors.ACCENT}; color: {Colors.ACCENT}; }}"
        )
        upload_btn.clicked.connect(self._upload_photo)
        info_col.addWidget(upload_btn)
        info_col.addStretch()

        hero_l.addLayout(info_col, 1)
        self._root.addWidget(hero)
        self._root.addSpacing(20)

        # ── Overview stats row ────────────────────────────────────────────────
        self._root.addWidget(_section_label("OVERVIEW"))
        self._root.addSpacing(10)
        self._stats_row = QHBoxLayout()
        self._stats_row.setSpacing(10)
        self._root.addLayout(self._stats_row)
        self._root.addSpacing(24)

        # ── Brain signature ───────────────────────────────────────────────────
        self._root.addWidget(_section_label("YOUR BRAIN SIGNATURE"))
        self._root.addSpacing(10)
        sig_card = QWidget()
        sig_card.setStyleSheet(f"background: {Colors.BG_CARD}; border-radius: 12px;")
        sig_l = QHBoxLayout(sig_card)
        sig_l.setContentsMargins(24, 24, 24, 24)
        sig_l.setSpacing(28)

        self._radar = _RadarChart({})
        sig_l.addWidget(self._radar, 0, Qt.AlignmentFlag.AlignVCenter)

        interp_col = QVBoxLayout()
        interp_col.setSpacing(0)
        self._type_title = QLabel()
        self._type_title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; letter-spacing: -0.3px;"
        )
        interp_col.addWidget(self._type_title)
        interp_col.addSpacing(8)

        self._type_desc = QLabel()
        self._type_desc.setWordWrap(True)
        self._type_desc.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 12px; line-height: 160%;"
        )
        interp_col.addWidget(self._type_desc)
        interp_col.addSpacing(16)

        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {Colors.BORDER};")
        interp_col.addWidget(div)
        interp_col.addSpacing(14)

        self._bars_col = QVBoxLayout()
        self._bars_col.setSpacing(6)
        interp_col.addLayout(self._bars_col)
        interp_col.addStretch()
        sig_l.addLayout(interp_col, 1)
        self._root.addWidget(sig_card)
        self._root.addSpacing(24)

        # ── Session activity ──────────────────────────────────────────────────
        self._root.addWidget(_section_label("SESSION ACTIVITY"))
        self._root.addSpacing(10)
        self._activity_row = QHBoxLayout()
        self._activity_row.setSpacing(10)
        self._root.addLayout(self._activity_row)
        self._root.addSpacing(24)

        # ── Peak performance ──────────────────────────────────────────────────
        self._root.addWidget(_section_label("PERSONAL BESTS"))
        self._root.addSpacing(10)
        self._bests_row = QHBoxLayout()
        self._bests_row.setSpacing(10)
        self._root.addLayout(self._bests_row)
        self._root.addSpacing(24)

        # ── Training records ──────────────────────────────────────────────────
        self._root.addWidget(_section_label("TRAINING RECORDS"))
        self._root.addSpacing(10)
        self._training_area = QVBoxLayout()
        self._training_area.setSpacing(10)
        self._root.addLayout(self._training_area)
        self._root.addSpacing(32)

        # ── Logout / Delete ───────────────────────────────────────────────────
        div2 = QFrame()
        div2.setFixedHeight(1)
        div2.setStyleSheet(f"background: {Colors.BORDER};")
        self._root.addWidget(div2)
        self._root.addSpacing(20)

        logout_btn = QPushButton("↪  Log out of  " + self._user_name)
        logout_btn.setFixedHeight(42)
        logout_btn.setStyleSheet(
            f"QPushButton {{ background: rgba(216, 90, 48, 0.08); "
            f"border: 1px solid rgba(216, 90, 48, 0.28); border-radius: 8px; "
            f"color: {Colors.DANGER}; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: rgba(216, 90, 48, 0.18); "
            f"border-color: rgba(216, 90, 48, 0.50); }}"
        )
        logout_btn.clicked.connect(self.logout_requested)
        self._root.addWidget(logout_btn)
        self._root.addSpacing(12)

        delete_btn = QPushButton("Delete account permanently")
        delete_btn.setFixedHeight(36)
        delete_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {Colors.BORDER}; "
            f"border-radius: 8px; color: {Colors.TEXT_MUTED}; font-size: 11px; }}"
            f"QPushButton:hover {{ border-color: rgba(216, 90, 48, 0.50); "
            f"color: rgba(216, 90, 48, 0.70); }}"
        )
        delete_btn.clicked.connect(self._confirm_delete)
        self._root.addWidget(delete_btn)
        self._root.addSpacing(32)
        self._root.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        user_row = self._db.get_user(self._user_id)
        stats    = self._db.get_user_extended_stats(self._user_id)
        training = self._db.get_training_stats_by_metric(user_id=self._user_id)

        basic    = stats["basic"]
        tr       = stats["training"]
        hour     = stats["active_hour"]
        days     = stats["active_days"]

        # ── Member since ──────────────────────────────────────────────────────
        if user_row and user_row["created_at"]:
            try:
                dt = datetime.fromisoformat(user_row["created_at"])
                self._since_lbl.setText(f"Member since {dt.strftime('%B %Y')}")
            except Exception:
                pass

        # ── Brain type badge & interpretation ─────────────────────────────────
        avgs = {}
        if basic:
            for key, *_ in METRICS:
                avgs[key] = basic[f"avg_{key}"]

        btype, bcolor, bdesc = _brain_type(avgs)
        self._type_badge.setText(f"  {btype}  ")
        self._type_badge.setStyleSheet(
            f"background: {bcolor}22; color: {bcolor}; "
            f"border: 1px solid {bcolor}55; border-radius: 10px; "
            f"font-size: 11px; font-weight: 700; letter-spacing: 0.5px;"
        )
        self._type_title.setText(btype)
        self._type_title.setStyleSheet(
            f"color: {bcolor}; font-size: 16px; font-weight: 700;"
        )
        self._type_desc.setText(bdesc)

        # ── Radar ─────────────────────────────────────────────────────────────
        self._radar._values = avgs
        self._radar.update()

        # ── Mini bars ─────────────────────────────────────────────────────────
        while self._bars_col.count():
            item = self._bars_col.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for key, label, color, *_ in METRICS:
            self._bars_col.addWidget(_MiniBar(label, avgs.get(key), color))

        # ── Overview stats ────────────────────────────────────────────────────
        while self._stats_row.count():
            item = self._stats_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        total_s        = int(basic["total_seconds"] or 0)   if basic else 0
        total_sess     = int(basic["total_sessions"] or 0)  if basic else 0
        total_readings = int(basic["total_readings"] or 0)  if basic else 0
        act_days       = int(basic["active_days"] or 0)     if basic else 0
        tr_sess        = int(tr["training_sessions"] or 0)  if tr else 0

        for label, value, color in [
            ("Sessions",          str(total_sess),         Colors.TEXT_PRIMARY),
            ("Recording Time",    _fmt_seconds(total_s),   Colors.ACCENT),
            ("Active Days",       str(act_days),           Colors.SUCCESS),
            ("Training Sessions", str(tr_sess),            Colors.WARNING),
            ("Total Readings",    str(total_readings),     Colors.TEXT_PRIMARY),
        ]:
            self._stats_row.addWidget(_stat_card(label, value, color))

        # ── Activity stats ────────────────────────────────────────────────────
        while self._activity_row.count():
            item = self._activity_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        streak   = _longest_streak(days)
        avg_dur  = _fmt_seconds(total_s / total_sess) if total_sess else "—"
        avg_reads = f"{total_readings // total_sess}" if total_sess else "—"

        for label, value in [
            ("Avg Session",            avg_dur),
            ("Most Active At",         _fmt_hour(hour)),
            ("Longest Streak",         f"{streak} day{'s' if streak != 1 else ''}"),
            ("Avg Readings / Session", avg_reads),
        ]:
            self._activity_row.addWidget(_stat_card(label, value))

        # ── Personal bests ────────────────────────────────────────────────────
        while self._bests_row.count():
            item = self._bests_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if basic:
            for key, label, color, *_ in METRICS:
                best = basic[f"best_{key}"]
                val  = f"{best:.0f}" if best is not None else "—"
                self._bests_row.addWidget(_stat_card(label, val, color))

        # ── Training records ──────────────────────────────────────────────────
        while self._training_area.count():
            item = self._training_area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if training:
            plain = QWidget()
            plain.setStyleSheet("background: transparent;")
            pl = QHBoxLayout(plain)
            pl.setContentsMargins(0, 0, 0, 0)
            pl.setSpacing(10)
            for row in training:
                metric = row["target_metric"]
                color  = next((c for k, _, c, *_ in METRICS if k == metric), Colors.TEXT_PRIMARY)
                card   = QWidget()
                card.setStyleSheet(f"background: {Colors.BG_CARD}; border-radius: 10px;")
                cl = QVBoxLayout(card)
                cl.setContentsMargins(0, 0, 0, 0)
                outer2 = QHBoxLayout()
                outer2.setContentsMargins(0, 0, 0, 0)
                bar_f = QFrame()
                bar_f.setFixedWidth(3)
                bar_f.setStyleSheet(f"background: {color}; border-radius: 2px;")
                outer2.addWidget(bar_f)
                inner2 = QVBoxLayout()
                inner2.setContentsMargins(14, 12, 14, 12)
                inner2.setSpacing(3)
                m_lbl = QLabel(metric.upper())
                m_lbl.setStyleSheet(
                    f"color: {color}; font-size: 9px; font-weight: 700; letter-spacing: 1px;"
                )
                s_lbl = QLabel(f"{int(row['session_count'] or 0)}")
                s_lbl.setStyleSheet(
                    f"color: {Colors.TEXT_PRIMARY}; font-size: 22px; font-weight: 700;"
                )
                sub_lbl = QLabel("training sessions")
                sub_lbl.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 9px;")
                avg_s  = row["avg_seconds"]
                best_s = int(row["best_seconds"] or 0)
                perf_lbl = QLabel(
                    f"avg {avg_s:.0f}s  \u00b7  best {best_s}s" if avg_s else "—"
                )
                perf_lbl.setStyleSheet(
                    f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;"
                )
                inner2.addWidget(m_lbl)
                inner2.addWidget(s_lbl)
                inner2.addWidget(sub_lbl)
                inner2.addSpacing(4)
                inner2.addWidget(perf_lbl)
                outer2.addLayout(inner2)
                cl.addLayout(outer2)
                pl.addWidget(card)
            pl.addStretch()
            self._training_area.addWidget(plain)
        else:
            no_lbl = QLabel("No training sessions yet — start training to track your progress.")
            no_lbl.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-size: 12px; font-style: italic;"
            )
            self._training_area.addWidget(no_lbl)

    # ── Photo upload ──────────────────────────────────────────────────────────

    def _upload_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose profile photo", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not path:
            return
        src = QPixmap(path)
        if src.isNull():
            return
        # Crop to square from center, resize to 200×200
        side = min(src.width(), src.height())
        x    = (src.width()  - side) // 2
        y    = (src.height() - side) // 2
        src  = src.copy(x, y, side, side).scaled(
            200, 200,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        dest = _avatar_path(self._user_id)
        src.save(str(dest), "PNG")
        self._avatar.refresh()

    # ── Delete account ────────────────────────────────────────────────────────

    def _confirm_delete(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Delete account")
        dlg.setFixedWidth(400)
        dlg.setStyleSheet(f"background: {Colors.BG_SURFACE}; color: #f0f0f5;")

        l = QVBoxLayout(dlg)
        l.setContentsMargins(28, 24, 28, 24)
        l.setSpacing(12)

        title = QLabel(f"Delete <b>{self._user_name}</b>?")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        l.addWidget(title)

        body = QLabel(
            "This will permanently erase all sessions, training records, and "
            "readings for this profile. This cannot be undone."
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 12px;")
        l.addWidget(body)
        l.addSpacing(8)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(34)
        cancel.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {Colors.BORDER}; "
            f"border-radius: 6px; color: {Colors.TEXT_MUTED}; font-size: 12px; padding: 0 20px; }}"
            f"QPushButton:hover {{ border-color: {Colors.TEXT_SECONDARY}; color: {Colors.TEXT_PRIMARY}; }}"
        )
        cancel.clicked.connect(dlg.reject)

        delete_btn = QPushButton("Delete permanently")
        delete_btn.setFixedHeight(34)
        delete_btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.DANGER}; border: none; "
            f"border-radius: 6px; color: white; font-size: 12px; font-weight: 600; padding: 0 20px; }}"
            f"QPushButton:hover {{ background: {Colors.DANGER}cc; }}"
        )
        delete_btn.clicked.connect(dlg.accept)

        btn_row.addWidget(cancel)
        btn_row.addWidget(delete_btn)
        l.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        # Delete avatar file if present
        avatar = _avatar_path(self._user_id)
        if avatar.exists():
            avatar.unlink(missing_ok=True)
        self._db.delete_user(self._user_id)
        self.user_deleted.emit()

    # ── Public refresh ────────────────────────────────────────────────────────

    def refresh(self) -> None:
        self._load()
