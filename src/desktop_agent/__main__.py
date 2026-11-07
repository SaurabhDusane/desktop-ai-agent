"""Application entry point."""

import sys
from PySide6.QtWidgets import QApplication

from desktop_agent.config import Settings
from desktop_agent.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Local Desktop AI Agent")
    window = MainWindow(Settings.from_environment())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
