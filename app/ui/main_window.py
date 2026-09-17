"""主窗口：侧边导航 + 页面切换 + 系统托盘。"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.core.config import Config
from app.core.scheduler import DailyScheduler
from app.core.state import State
from app.core import updater

from .dashboard import DashboardPage
from .history import HistoryPage
from .login import LoginPage
from .settings import SettingsPage
from .workers import AsyncTask

NAV_ITEMS = [
    ("dashboard", "仪表盘"),
    ("settings", "设置"),
    ("login", "登录"),
    ("history", "历史记录"),
]


def _make_app_icon() -> QIcon:
    """生成一个简单的淡蓝色「B」图标（用于窗口与托盘）。"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor("#5b9bd5"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#ffffff"))
    painter.setFont(QFont("Microsoft YaHei", 30, QFont.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "B")
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    """应用主窗口。"""

    # 定时触发信号（在 APScheduler 线程发出，排队回主线程执行）
    scheduled_run = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("B站视频自动上传")
        self.resize(1020, 700)
        self.setWindowIcon(_make_app_icon())

        self.config = Config()
        self.state = State()
        self.scheduler = DailyScheduler()

        self._build_ui()
        self._setup_tray()
        self._apply_schedule()
        QTimer.singleShot(3000, self._check_updates_startup)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 侧边栏 ----
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(180)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 22, 12, 22)
        side_layout.setSpacing(8)

        title = QLabel("B站自动上传")
        title.setObjectName("appTitle")
        side_layout.addWidget(title)
        side_layout.addSpacing(18)

        self._nav_buttons: dict[str, QPushButton] = {}
        for key, label in NAV_ITEMS:
            btn = QPushButton(label)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self.switch_page(k))
            side_layout.addWidget(btn)
            self._nav_buttons[key] = btn
        side_layout.addStretch()

        # ---- 页面栈 ----
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.dashboard = DashboardPage(self.config, self.state, self.scheduler, notify=self._notify)
        self.settings_page = SettingsPage(self.config)
        self.login_page = LoginPage(self.config)
        self.history_page = HistoryPage(self.state, self.config)

        self.pages = {
            "dashboard": self.dashboard,
            "settings": self.settings_page,
            "login": self.login_page,
            "history": self.history_page,
        }
        for key, _label in NAV_ITEMS:
            self.stack.addWidget(self.pages[key])

        # 联动
        self.login_page.login_changed.connect(self.dashboard.refresh)
        self.settings_page.settings_saved.connect(self._on_settings_saved)
        self.scheduled_run.connect(self.dashboard.run_now)

        root.addWidget(sidebar)
        root.addWidget(self.stack, 1)

        self.switch_page("dashboard")

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(_make_app_icon(), self)
        self.tray.setToolTip("B站视频自动上传")
        menu = QMenu()
        show_action = menu.addAction("显示主窗口")
        show_action.triggered.connect(self._show_from_tray)
        run_action = menu.addAction("立即运行一次")
        run_action.triggered.connect(self.dashboard.run_now)
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self._quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:  # 单击托盘图标
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.show()
        self.activateWindow()

    def _notify(self, title: str, message: str) -> None:
        """通过系统托盘向 Windows 发布通知。"""
        self.tray.showMessage(title, message, QSystemTrayIcon.Information, 6000)

    def _quit(self) -> None:
        self.scheduler.shutdown()
        self.tray.hide()
        QApplication.instance().quit()

    def switch_page(self, key: str) -> None:
        for k, btn in self._nav_buttons.items():
            btn.setChecked(k == key)
        self.stack.setCurrentWidget(self.pages[key])
        self.pages[key].refresh()

    def _apply_schedule(self) -> None:
        times = self.config.get("schedule_times", ["08:00"])
        self.scheduler.set_schedule(times, self.scheduled_run.emit)
        self.scheduler.start()

    def _on_settings_saved(self) -> None:
        self._apply_schedule()
        self.dashboard.refresh()

    def _check_updates_startup(self) -> None:
        task = AsyncTask(updater.check_latest, self)
        task.done.connect(self._on_startup_update_check)
        task.start()

    def _on_startup_update_check(self, info: dict) -> None:
        if info.get("has_update"):
            self.tray.showMessage(
                "发现新版本",
                f"新版本 v{info.get('latest')} 已发布，请到「仪表盘」点「检查更新」下载。",
                QSystemTrayIcon.Information, 6000,
            )

    def closeEvent(self, event) -> None:
        """关闭窗口：默认最小化到托盘继续后台运行。"""
        if self.config.get("minimize_to_tray", True):
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "B站自动上传", "程序已最小化到系统托盘，仍会按计划运行。",
                QSystemTrayIcon.Information, 3000,
            )
        else:
            self.scheduler.shutdown()
            event.accept()
