"""仪表盘：登录状态、下次运行时间、立即运行。"""

import webbrowser

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core import auth, pipeline, updater
from app.core.version import VERSION

from .workers import AsyncTask, RunWorker


class DashboardPage(QWidget):
    """仪表盘页。"""

    def __init__(self, config, state, scheduler, notify=None) -> None:
        super().__init__()
        self.config = config
        self.state = state
        self.scheduler = scheduler
        self._notify = notify or (lambda title, msg: None)
        self._check_task = None
        self._run_worker = None
        self._update_available = False
        self._latest_url = ""
        self._notified_start = False
        self._login_expired_notified = False
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("仪表盘")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        card = QFrame()
        card.setObjectName("card")
        grid = QGridLayout(card)
        grid.setContentsMargins(22, 20, 22, 20)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(16)

        grid.addWidget(QLabel("登录状态"), 0, 0)
        self.login_status = QLabel("检测中…")
        self.login_status.setObjectName("statusBadge")
        grid.addWidget(self.login_status, 0, 1)

        grid.addWidget(QLabel("下次运行"), 1, 0)
        self.next_run_label = QLabel("—")
        grid.addWidget(self.next_run_label, 1, 1)

        grid.addWidget(QLabel("监控文件夹"), 2, 0)
        self.folder_label = QLabel("未配置")
        self.folder_label.setWordWrap(True)
        grid.addWidget(self.folder_label, 2, 1)

        layout.addWidget(card)

        self.run_btn = QPushButton("立即运行一次")
        self.run_btn.setObjectName("primaryButton")
        self.run_btn.setMinimumHeight(42)
        self.run_btn.clicked.connect(self.run_now)
        layout.addWidget(self.run_btn)

        self.log_label = QLabel("")
        self.log_label.setObjectName("hint")
        self.log_label.setWordWrap(True)
        layout.addWidget(self.log_label)

        layout.addStretch()

        # 底部：版本信息 + 检查更新
        bottom = QHBoxLayout()
        self.version_label = QLabel(f"当前版本 v{VERSION}")
        self.version_label.setObjectName("hint")
        bottom.addWidget(self.version_label)
        bottom.addStretch()
        self.update_btn = QPushButton("检查更新")
        self.update_btn.clicked.connect(self._on_update_btn_clicked)
        bottom.addWidget(self.update_btn)
        layout.addLayout(bottom)

    def refresh(self) -> None:
        """刷新状态。登录态校验走后台线程，不卡界面。"""
        folders = self.config.get("watch_folders", [])
        self.folder_label.setText("；".join(folders) if folders else "未配置")

        nt = self.scheduler.next_run_time()
        self.next_run_label.setText(nt.strftime("%Y-%m-%d %H:%M:%S") if nt else "未设置")

        cred = auth.load_credential()
        if cred is None:
            self._set_login_status("未登录", "#b0484f")
            return

        self._set_login_status("检测中…", "#5b6c80")
        if self._check_task is not None and self._check_task.isRunning():
            return
        self._check_task = AsyncTask(self._make_check_coro(cred), self)
        self._check_task.done.connect(self._on_check_done)
        self._check_task.error.connect(lambda _e: self._set_login_status("校验失败", "#c98a2f"))
        self._check_task.start()

    @staticmethod
    def _make_check_coro(cred):
        async def _check():
            valid = await auth.check_login(cred)
            if not valid:
                return ("expired", "")
            name = await auth.get_nickname(cred)
            return ("ok", name)

        return _check

    def _on_check_done(self, result) -> None:
        kind, name = result
        if kind == "ok":
            self._login_expired_notified = False
            self._set_login_status(f"已登录：{name or '已登录'}", "#3d8f5c")
        else:
            self._set_login_status("登录已过期，请重新登录", "#c98a2f")
            if not self._login_expired_notified:
                self._login_expired_notified = True
                self._notify("登录失效", "登录已过期，请重新登录。")

    def _set_login_status(self, text: str, color: str) -> None:
        self.login_status.setText(text)
        self.login_status.setStyleSheet(f"background:{color}; color:#ffffff;")

    def _on_update_btn_clicked(self) -> None:
        if self._update_available:
            webbrowser.open(self._latest_url)
        else:
            self.check_update()

    def check_update(self) -> None:
        self.update_btn.setEnabled(False)
        self.update_btn.setText("检查中…")
        self._update_task = AsyncTask(updater.check_latest, self)
        self._update_task.done.connect(self._on_update_checked)
        self._update_task.error.connect(lambda _e: self._on_update_failed())
        self._update_task.start()

    def _on_update_checked(self, info: dict) -> None:
        self.update_btn.setEnabled(True)
        if info.get("has_update"):
            self._update_available = True
            self._latest_url = info.get("url", "")
            self.version_label.setText(f"当前 v{VERSION} → 新版本 v{info.get('latest')}")
            self.update_btn.setText(f"下载 v{info.get('latest')}")
        else:
            self._update_available = False
            self.version_label.setText(f"已是最新版本 v{VERSION}")
            self.update_btn.setText("检查更新")

    def _on_update_failed(self) -> None:
        self.update_btn.setEnabled(True)
        self.update_btn.setText("检查更新")
        self.version_label.setText(f"当前版本 v{VERSION}（检查失败）")

    def run_now(self) -> None:
        """立即运行一次完整流程（扫描→命名→拆分→上传→清理）。"""
        if self._run_worker is not None and self._run_worker.isRunning():
            self.log_label.setText("正在运行中，请稍候…")
            return

        self.run_btn.setEnabled(False)
        self.log_label.setText("开始运行…")
        self._notified_start = False

        self._run_worker = RunWorker(
            lambda emit: pipeline.run_once(self.config.data, self.state, on_progress=emit),
            self,
        )
        self._run_worker.progress.connect(self._on_progress)
        self._run_worker.finished_result.connect(self._on_run_done)
        self._run_worker.start()

    def _on_progress(self, msg: str) -> None:
        self.log_label.setText(msg)
        if not self._notified_start and msg.startswith("上传中"):
            self._notified_start = True
            self._notify("开始上传", "正在上传视频…")

    def _on_run_done(self, result: dict) -> None:
        self.run_btn.setEnabled(True)
        msg = result.get("message", "")
        event = result.get("event", "")
        self.log_label.setText(msg)
        self.refresh()

        if event == "success":
            self._notify("上传成功", msg)
        elif event == "partial":
            self._notify("上传完成（部分失败）", msg)
        elif event == "failed":
            self._notify("上传失败", msg)
        elif event in ("login_expired", "no_login"):
            self._notify("登录失效", msg)
