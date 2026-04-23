# Entry point — launches the user profile picker then the main window.

import sys
import signal

from PyQt6.QtCore import QObject, QEvent, Qt, QTimer
from PyQt6.QtWidgets import QApplication, QPushButton

from frontend.styles import GLOBAL_STYLESHEET
from frontend.main_window import MainWindow
from frontend.user_dialog import UserDialog
from backend.engine import DataEngine
from backend.database import Database
from backend.sources.mock_source import MockSource


class _ButtonCursorFilter(QObject):
    def eventFilter(self, obj, event):
        if isinstance(obj, QPushButton) and event.type() == QEvent.Type.Enter:
            obj.setCursor(Qt.CursorShape.PointingHandCursor)
        return False


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SkyWave")
    app.setApplicationVersion("0.1.0")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(GLOBAL_STYLESHEET)
    _cursor_filter = _ButtonCursorFilter(app)
    app.installEventFilter(_cursor_filter)

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    _sigint_timer = QTimer()
    _sigint_timer.start(200)
    _sigint_timer.timeout.connect(lambda: None)

    db = Database()

    def launch():
        user_dialog = UserDialog(db)
        if not user_dialog.exec():
            app.quit()
            return

        user_id   = user_dialog.selected_user_id
        user_name = user_dialog.selected_user_name

        source = MockSource()
        engine = DataEngine(source, db, user_id=user_id)
        window = MainWindow(engine, db, user_name=user_name, user_id=user_id)

        def on_logout():
            window._is_logout = True
            window.close()
            QTimer.singleShot(150, launch)

        window.logout_requested.connect(on_logout)
        window.show()
        engine.start()

    launch()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
