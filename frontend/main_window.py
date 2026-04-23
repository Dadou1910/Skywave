from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QStackedWidget, QFrame, QPushButton, QSizePolicy, QApplication,
)

from frontend.styles import Colors
from frontend.screens.monitor_screen  import MonitorScreen
from frontend.screens.training_screen import TrainingScreen
from frontend.screens.history_screen  import HistoryScreen
from frontend.screens.waves_screen    import WavesScreen
from frontend.screens.profile_screen  import ProfileScreen
from backend.engine import DataEngine
from backend.database import Database


class MainWindow(QMainWindow):

    logout_requested = pyqtSignal()

    def __init__(self, engine: DataEngine, db: Database, user_name: str = "Guest",
                 user_id: int | None = None):
        super().__init__()
        self._engine    = engine
        self._db        = db
        self._user_name = user_name
        self._user_id   = user_id
        self._drag_pos: QPoint | None = None
        self._prev_index = 0
        self._is_logout  = False
        self.setWindowTitle("SkyWave")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(1000, 680)
        self.resize(1240, 800)
        self._build_ui()
        self._switch(0)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def _build_ui(self):
        root = QFrame()
        root.setObjectName("AppBorder")
        root.setStyleSheet(
            "QFrame#AppBorder {"
            " background: #0d0d0f;"
            " border-left:   1px solid rgba(255,255,255,0.06);"
            " border-right:  1px solid rgba(255,255,255,0.06);"
            " border-bottom: 1px solid rgba(255,255,255,0.06);"
            "}"
        )
        self.setCentralWidget(root)

        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        vbox.addWidget(_TitleBar(self))

        content = QWidget()
        outer = QHBoxLayout(content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(_Sidebar(self._switch, self._user_name, self._user_id, self,
                                 logout_cb=self.logout_requested.emit))

        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background: {Colors.BORDER};")
        outer.addWidget(sep)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(f"background: {Colors.BG_APP};")
        self._monitor_screen  = MonitorScreen(self._engine)
        self._training_screen = TrainingScreen(self._engine)
        self._history_screen  = HistoryScreen(self._db, user_id=self._user_id)
        self._waves_screen    = WavesScreen(self._engine)
        self._stack.addWidget(self._monitor_screen)   # 0
        self._stack.addWidget(self._training_screen)  # 1
        self._stack.addWidget(self._history_screen)   # 2
        self._stack.addWidget(self._waves_screen)     # 3
        self._profile_screen = ProfileScreen(self._db, self._user_id or 0, self._user_name)
        self._stack.addWidget(self._profile_screen)   # 4
        self._profile_screen.back_requested.connect(lambda: self._switch(self._prev_index))
        self._profile_screen.logout_requested.connect(self.logout_requested)
        self._profile_screen.user_deleted.connect(self.logout_requested)
        outer.addWidget(self._stack, 1)

        vbox.addWidget(content, 1)

    def _switch(self, index: int) -> None:
        if index != 4:
            self._prev_index = self._stack.currentIndex()
        self._stack.setCurrentIndex(index)
        sidebar = self.centralWidget().findChild(_Sidebar)
        if sidebar:
            sidebar.set_active(index)

    def closeEvent(self, event):
        self._engine.stop()
        event.accept()
        if not self._is_logout:
            QApplication.instance().quit()


class _TitleBar(QWidget):

    HEIGHT = 34

    def __init__(self, window: QMainWindow, parent=None):
        super().__init__(parent)
        self._window   = window
        self._drag_pos: QPoint | None = None
        self.setFixedHeight(self.HEIGHT)
        self.setStyleSheet(
            "background: #2a2a2e;"
            "border-bottom: 1px solid rgba(255,255,255,0.07);"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        for color, hover, action in [
            ("#ff5f57", "#e04040", lambda: window.close()),
            ("#febc2e", "#d4a020", lambda: window.showMinimized()),
            ("#28c840", "#1da030", lambda: (
                window.showNormal() if window.isMaximized() else window.showMaximized()
            )),
        ]:
            btn = QPushButton()
            btn.setFixedSize(13, 13)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background: {color}; border-radius: 6px; border: none; }}"
                f"QPushButton:hover {{ background: {hover}; }}"
            )
            btn.clicked.connect(action)
            layout.addWidget(btn)

        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


class _Sidebar(QWidget):

    def __init__(self, switch_cb, user_name: str = "Guest", user_id: int | None = None,
                 parent=None, logout_cb=None):
        super().__init__(parent)
        self._switch_cb  = switch_cb
        self._logout_cb  = logout_cb
        self._user_id    = user_id
        self._items: list[_NavItem] = []
        self.setFixedWidth(200)
        self.setStyleSheet(f"background: {Colors.BG_SIDEBAR};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addSpacing(14)
        logo = QWidget()
        logo.setFixedHeight(48)
        logo_l = QVBoxLayout(logo)
        logo_l.setContentsMargins(24, 0, 0, 0)
        logo_l.setSpacing(0)

        name = QLabel("SkyWave")
        name.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 20px; font-weight: 700; "
            f"letter-spacing: -0.5px;"
        )
        sub = QLabel("Brain Interface")
        sub.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 10px; letter-spacing: 1.5px;"
        )
        logo_l.addWidget(name)
        logo_l.addWidget(sub)
        logo_l.addStretch()
        layout.addWidget(logo)

        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {Colors.BORDER};")
        layout.addWidget(div)
        layout.addSpacing(12)

        nav_container = QWidget()
        nav_container.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setContentsMargins(10, 2, 10, 2)
        nav_layout.setSpacing(2)

        nav_data = [
            ("Monitor",  "monitor",  0),
            ("Training", "training", 1),
            ("History",  "history",  2),
            ("Waves",    "waves",    3),
        ]
        for label, icon_key, idx in nav_data:
            item = _NavItem(label, icon_key, idx, switch_cb)
            self._items.append(item)
            nav_layout.addWidget(item)

        layout.addWidget(nav_container)
        layout.addStretch()

        div2 = QFrame()
        div2.setFixedHeight(1)
        div2.setStyleSheet(f"background: {Colors.BORDER};")
        layout.addWidget(div2)

        badge = QWidget()
        badge.setFixedHeight(52)
        badge_l = QHBoxLayout(badge)
        badge_l.setContentsMargins(12, 0, 12, 0)
        badge_l.setSpacing(10)

        avatar = QLabel(user_name[0].upper())
        avatar.setFixedSize(28, 28)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background: {Colors.ACCENT}22; color: {Colors.ACCENT}; "
            f"border-radius: 14px; font-size: 12px; font-weight: 700;"
        )
        badge_l.addWidget(avatar)

        name_col = QVBoxLayout()
        name_col.setSpacing(1)
        uname = QLabel(user_name)
        uname.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-size: 12px; font-weight: 600;"
        )
        usub = QLabel("view profile  →")
        usub.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 9px;"
        )
        name_col.addWidget(uname)
        name_col.addWidget(usub)
        badge_l.addLayout(name_col)
        badge_l.addStretch()
        layout.addWidget(badge)

        if user_id is not None:
            badge.setCursor(Qt.CursorShape.PointingHandCursor)
            badge.setToolTip("View your profile")
            badge.mousePressEvent = lambda e: switch_cb(4) if e.button() == Qt.MouseButton.LeftButton else None
            badge.enterEvent = lambda e: badge.setStyleSheet(
                "background: rgba(127, 119, 221, 0.10); border-radius: 8px;"
            )
            badge.leaveEvent = lambda e: badge.setStyleSheet("background: transparent;")

        logout_btn = QPushButton("↪  Log out")
        logout_btn.setFixedHeight(32)
        logout_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        logout_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; "
            f"color: {Colors.TEXT_MUTED}; font-size: 11px; font-weight: 500; "
            f"text-align: left; padding-left: 16px; border-radius: 0px; }}"
            f"QPushButton:hover {{ background: rgba(216, 90, 48, 0.10); "
            f"color: {Colors.DANGER}; }}"
        )
        if logout_cb:
            logout_btn.clicked.connect(logout_cb)
        layout.addWidget(logout_btn)
        layout.addSpacing(8)

    def set_active(self, index: int) -> None:
        for item in self._items:
            item.set_active(item._index == index)


class _NavItem(QWidget):

    ICONS = {
        "monitor":  "⬡",
        "training": "◎",
        "history":  "◷",
        "waves":    "≋",
    }

    def __init__(self, label: str, icon_key: str, index: int, cb, parent=None):
        super().__init__(parent)
        self._index  = index
        self._cb     = cb
        self._active = False

        self.setFixedHeight(46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 16, 0)
        layout.setSpacing(12)

        self._bar = QFrame()
        self._bar.setFixedSize(3, 20)
        self._bar.setStyleSheet("background: transparent; border-radius: 2px;")
        layout.addWidget(self._bar)

        icon = QLabel(self.ICONS.get(icon_key, "·"))
        icon.setFixedWidth(16)
        icon.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 13px;")
        self._icon = icon
        layout.addWidget(icon)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 13px; font-weight: 400;"
        )
        self._lbl = lbl
        layout.addWidget(lbl)
        layout.addStretch()

        self._update()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._update()

    _ACCENT_ACTIVE = "rgba(127, 119, 221, 0.16)"
    _ACCENT_HOVER  = "rgba(127, 119, 221, 0.08)"
    _RADIUS        = "border-radius: 8px;"

    def _update(self) -> None:
        if self._active:
            self.setStyleSheet(
                f"background: {self._ACCENT_ACTIVE}; {self._RADIUS}"
            )
            self._bar.setStyleSheet(
                f"background: {Colors.ACCENT}; border-radius: 2px;"
            )
            self._lbl.setStyleSheet(
                f"color: {Colors.TEXT_PRIMARY}; font-size: 13px; font-weight: 600;"
            )
            self._icon.setStyleSheet(
                f"color: {Colors.ACCENT}; font-size: 13px;"
            )
        else:
            self.setStyleSheet(f"background: transparent; {self._RADIUS}")
            self._bar.setStyleSheet("background: transparent; border-radius: 2px;")
            self._lbl.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-size: 13px; font-weight: 400;"
            )
            self._icon.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-size: 13px;"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._cb(self._index)

    def enterEvent(self, event):
        if not self._active:
            self.setStyleSheet(f"background: {self._ACCENT_HOVER}; {self._RADIUS}")

    def leaveEvent(self, event):
        if not self._active:
            self.setStyleSheet(f"background: transparent; {self._RADIUS}")
