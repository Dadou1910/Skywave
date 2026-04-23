"""
Startup user picker dialog.
Shown once before the main window opens.
Returns the selected user_id, or None if cancelled.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QWidget, QScrollArea,
    QFrame,
)
from frontend.styles import Colors
from backend.database import Database


class UserDialog(QDialog):
    """
    Modal dialog: pick an existing user or create a new one.
    After accept(), read .selected_user_id and .selected_user_name.
    """

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self._db = db
        self.selected_user_id:   int | None = None
        self.selected_user_name: str        = ""

        self.setWindowTitle("SkyWave")
        self.setFixedSize(420, 520)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setStyleSheet(
            f"background: {Colors.BG_CARD}; border-radius: 14px;"
        )
        self._build_ui()
        self._load_users()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 32)
        root.setSpacing(0)

        # ── OS-style window buttons ───────────────────────────────────────────
        hdr = QHBoxLayout()
        close_btn = QPushButton()
        close_btn.setFixedSize(13, 13)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { background: #ff5f57; border-radius: 6px; border: none; }"
            "QPushButton:hover { background: #e04040; }"
        )
        close_btn.setToolTip("Quit SkyWave")
        close_btn.clicked.connect(lambda: __import__("sys").exit(0))
        hdr.addWidget(close_btn)
        hdr.addSpacing(6)
        for color, hover in (("#febc2e", "#d4a020"), ("#28c840", "#1da030")):
            dot = QPushButton()
            dot.setFixedSize(13, 13)
            dot.setCursor(Qt.CursorShape.PointingHandCursor)
            dot.setStyleSheet(
                f"QPushButton {{ background: {color}; border-radius: 6px; border: none; }}"
                f"QPushButton:hover {{ background: {hover}; }}"
            )
            hdr.addWidget(dot)
            hdr.addSpacing(6)
        hdr.addStretch()
        root.addLayout(hdr)
        root.addSpacing(16)

        # ── Header ────────────────────────────────────────────────────────────
        logo = QLabel("SkyWave")
        logo.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 24px; font-weight: 800; "
            f"letter-spacing: -0.5px;"
        )
        root.addWidget(logo)
        root.addSpacing(4)

        sub = QLabel("Who's training today?")
        sub.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 12px;"
        )
        root.addWidget(sub)
        root.addSpacing(28)

        # ── User list ─────────────────────────────────────────────────────────
        list_lbl = QLabel("SELECT PROFILE")
        list_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-weight: 700; "
            f"letter-spacing: 1.5px;"
        )
        root.addWidget(list_lbl)
        root.addSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(220)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"background: {Colors.BG_APP}; border-radius: 10px;"
        )

        self._list_inner = QWidget()
        self._list_inner.setStyleSheet(f"background: {Colors.BG_APP};")
        self._list_layout = QVBoxLayout(self._list_inner)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        scroll.setWidget(self._list_inner)
        root.addWidget(scroll)

        root.addSpacing(24)

        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {Colors.BORDER};")
        root.addWidget(div)
        root.addSpacing(20)

        # ── New user ──────────────────────────────────────────────────────────
        new_lbl = QLabel("NEW PROFILE")
        new_lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 9px; font-weight: 700; "
            f"letter-spacing: 1.5px;"
        )
        root.addWidget(new_lbl)
        root.addSpacing(8)

        input_row = QHBoxLayout()
        input_row.setSpacing(10)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Enter your name...")
        self._name_input.setFixedHeight(38)
        self._name_input.setStyleSheet(
            f"background: {Colors.BG_APP}; border: 1px solid {Colors.BORDER_LIGHT}; "
            f"border-radius: 8px; padding: 0 14px; color: {Colors.TEXT_PRIMARY}; "
            f"font-size: 13px;"
        )
        self._name_input.returnPressed.connect(self._create_user)
        input_row.addWidget(self._name_input)

        add_btn = QPushButton("Add")
        add_btn.setFixedSize(64, 38)
        add_btn.setProperty("accent", True)
        add_btn.clicked.connect(self._create_user)
        input_row.addWidget(add_btn)

        root.addLayout(input_row)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet(
            f"color: {Colors.DANGER}; font-size: 10px;"
        )
        self._error_lbl.setFixedHeight(18)
        root.addWidget(self._error_lbl)

        root.addStretch()

        # ── Continue as guest ─────────────────────────────────────────────────
        guest_btn = QPushButton("Continue without a profile")
        guest_btn.setFixedHeight(34)
        guest_btn.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        guest_btn.clicked.connect(self._select_guest)
        root.addWidget(guest_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _load_users(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        users = self._db.get_users()

        if not users:
            empty = QLabel("No profiles yet — add one below")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-size: 11px; "
                f"font-style: italic; padding: 20px 0;"
            )
            self._list_layout.addWidget(empty)
        else:
            for user in users:
                row = _UserRow(user["id"], user["name"], self._select_user)
                self._list_layout.addWidget(row)

        self._list_layout.addStretch()

    def _select_user(self, user_id: int, name: str):
        self.selected_user_id   = user_id
        self.selected_user_name = name
        self.accept()

    def _select_guest(self):
        self.selected_user_id   = None
        self.selected_user_name = "Guest"
        self.accept()

    def _create_user(self):
        name = self._name_input.text().strip()
        if not name:
            self._error_lbl.setText("Please enter a name.")
            return
        if len(name) > 40:
            self._error_lbl.setText("Name too long (max 40 characters).")
            return

        try:
            user_id = self._db.add_user(name)
            self._error_lbl.setText("")
            self._name_input.clear()
            self._select_user(user_id, name)
        except Exception:
            self._error_lbl.setText("A profile with that name already exists.")


class _UserRow(QWidget):

    def __init__(self, user_id: int, name: str, on_select, parent=None):
        super().__init__(parent)
        self._user_id  = user_id
        self._name     = name
        self._callback = on_select

        self.setFixedHeight(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        avatar = QLabel(name[0].upper())
        avatar.setFixedSize(30, 30)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background: {Colors.ACCENT}22; color: {Colors.ACCENT}; "
            f"border-radius: 15px; font-size: 13px; font-weight: 700;"
        )
        layout.addWidget(avatar)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 14px; font-weight: 500;"
        )
        layout.addWidget(name_lbl)
        layout.addStretch()

        arrow = QLabel("→")
        arrow.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 14px;")
        self._arrow = arrow
        layout.addWidget(arrow)

        sep = QFrame(self)
        sep.setGeometry(16, 47, self.width() - 32, 1)
        sep.setStyleSheet(f"background: {Colors.BORDER};")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._callback(self._user_id, self._name)

    def enterEvent(self, event):
        self.setStyleSheet(f"background: {Colors.BG_SURFACE};")
        self._arrow.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 14px;"
        )

    def leaveEvent(self, event):
        self.setStyleSheet("background: transparent;")
        self._arrow.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 14px;"
        )
