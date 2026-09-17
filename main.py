"""程序入口。"""

import logging
import os
import sys

from PySide6.QtWidgets import QApplication

from app.core.config import get_data_dir
from app.ui.main_window import MainWindow

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_QSS_PATH = os.path.join(_BASE_DIR, "app", "ui", "theme.qss")


def _setup_logging() -> None:
    log_file = os.path.join(get_data_dir(), "app.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def main() -> None:
    _setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("B站视频自动上传")
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出，托盘常驻后台

    if os.path.exists(_QSS_PATH):
        with open(_QSS_PATH, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
