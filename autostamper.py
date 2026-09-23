import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from autostamper.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AutoStamper")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
