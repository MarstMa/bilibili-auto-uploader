"""仪表盘：文件夹卡片（一级）+ 文件夹详情（二级）+ 检查/下载更新。"""

import os
import sys
import webbrowser

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core import auth, pipeline, scanner, updater
from app.core.version import VERSION

from .folder_detail import FolderDetailPage
from .workers import AsyncTask, RunWorker


class _FolderCard(QFrame):
    """一张文件夹卡片，点击进入详情。"""

    clicked = Signal(str)

    def __init__(self, path: str, name: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        self.path = path
        self._pending = 0
        self._uploading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        name_label = QLabel(name)
        name_label.setStyleSheet("font-weight:bold; font-size:14px;")
        layout.addWidget(name_label)

        self.pending_label = QLabel("待上传：…")
        self.pending_label.setObjectName("hint")
        layout.addWidget(self.pending_label)

        self.status_label = QLabel("")
        self.status_label.setObjectName("hint")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        path_label = QLabel(path)
        path_label.setStyleSheet("color:#7a7a90; font-size:11px;")
        layout.addWidget(path_label)

    def set_pending(self, count: int) -> None:
        self._pending = count
        self._render_pending()

    def set_uploading(self, uploading: bool) -> None:
        self._uploading = uploading
        self._render_pending()

    def _render_pending(self) -> None:
        if self._uploading:
            self.pending_label.setText("上传中…")
            self.pending_label.setStyleSheet("color:#e0a030;")
        else:
            self.pending_label.setText(f"待上传：{self._pending} 个")
            self.pending_label.setStyleSheet("")

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.path)
        super().mousePressEvent(event)


class DashboardPage(QWidget):
    """仪表盘页。"""

    def __init__(self, config, state, scheduler, notify=None) -> None:
        super().__init__()
        self.config = config
        self.state = state
        self.scheduler = scheduler
        self._notify = notify or (lambda t, m: None)
        self._cards: dict[str, _FolderCard] = {}
        self._uploading: set[str] = set()
        self._check_task = None
        self._run_worker = None
        self._count_worker = None
        self._download_worker = None
        self._update_available = False
        self._latest = ""
        self._latest_url = ""
        self._asset_url = ""
        self._new_exe_path = ""
        self._build()

    # ---------- 构建 ----------

    def _build(self) -> None:
        self.stack = QStackedWidget()

        self.cards_page = QWidget()
        self._build_cards_page()
        self.stack.addWidget(self.cards_page)

        self.detail_page = FolderDetailPage(self.config, self.state, notify=self._notify)
        self.detail_page.back_requested.connect(self._back_to_cards)
        self.detail_page.deleted.connect(self._back_to_cards)
        self.detail_page.upload_started.connect(self._on_folder_upload_started)
        self.detail_page.upload_finished.connect(self._on_folder_upload_finished)
        self.stack.addWidget(self.detail_page)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack)

    def _build_cards_page(self) -> None:
        layout = QVBoxLayout(self.cards_page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("仪表盘")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        # 顶部操作栏
        top = QHBoxLayout()
        self.login_status = QLabel("检测中…")
        self.login_status.setObjectName("statusBadge")
        top.addWidget(self.login_status)
        top.addStretch()
        add_btn = QPushButton("＋ 添加文件夹")
        add_btn.setObjectName("primaryButton")
        add_btn.clicked.connect(self._add_folder)
        top.addWidget(add_btn)
        run_all_btn = QPushButton("立即上传全部")
        run_all_btn.clicked.connect(self.run_now)
        top.addWidget(run_all_btn)
        layout.addLayout(top)

        self.log_label = QLabel("")
        self.log_label.setObjectName("hint")
        self.log_label.setWordWrap(True)
        layout.addWidget(self.log_label)

        # 卡片滚动区
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 8, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.addStretch()
        self.scroll.setWidget(self.cards_host)
        layout.addWidget(self.scroll, 1)

        # 底部版本 + 更新
        bottom = QHBoxLayout()
        self.version_label = QLabel(f"当前版本 v{VERSION}")
        self.version_label.setObjectName("hint")
        bottom.addWidget(self.version_label)
        bottom.addStretch()
        self.update_btn = QPushButton("检查更新")
        self.update_btn.clicked.connect(self._on_update_btn_clicked)
        bottom.addWidget(self.update_btn)
        layout.addLayout(bottom)

    # ---------- 刷新 ----------

    def refresh(self) -> None:
        """刷新登录状态、重建卡片、后台统计待上传数。"""
        self._refresh_login_status()
        self._rebuild_cards()
        self._refresh_counts()

    def _refresh_login_status(self) -> None:
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
            valid_cred = await auth.ensure_valid_credential(cred)
            if valid_cred is None:
                return ("expired", "")
            name = await auth.get_nickname(valid_cred)
            return ("ok", name)

        return _check

    def _on_check_done(self, result) -> None:
        kind, name = result
        if kind == "ok":
            self._set_login_status(f"已登录：{name or '已登录'}", "#3d8f5c")
        else:
            self._set_login_status("登录已过期，请重新登录", "#c98a2f")
            self._notify("登录失效", "登录已过期，请重新登录。")

    def _set_login_status(self, text: str, color: str) -> None:
        self.login_status.setText(text)
        self.login_status.setStyleSheet(f"background:{color}; color:#ffffff;")

    def _rebuild_cards(self) -> None:
        # 清空旧卡片（保留末尾 stretch）
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._cards.clear()

        folders = [f for f in self.config.get("folders", []) if isinstance(f, dict) and f.get("path")]
        if not folders:
            empty = QLabel("还没有文件夹。点击右上角「＋ 添加文件夹」开始。")
            empty.setObjectName("hint")
            empty.setAlignment(Qt.AlignCenter)
            self.cards_layout.insertWidget(0, empty)
            return

        for folder in folders:
            path = folder.get("path", "")
            name = os.path.basename(path.rstrip("\\/")) or path
            card = _FolderCard(path, name)
            card.clicked.connect(self._open_folder)
            if folder.get("enabled", True) is False:
                card.set_status("已禁用自动扫描")
            else:
                last = self.state.last_status_for_folder(path)
                card.set_status(f"最近：{last[0]}（{last[3]}）" if last else "暂无上传记录")
            if path in self._uploading:
                card.set_uploading(True)
            self._cards[path] = card
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

    def _refresh_counts(self) -> None:
        if self._count_worker is not None and self._count_worker.isRunning():
            return
        self._count_worker = RunWorker(lambda _emit: self._compute_counts(), self)
        self._count_worker.finished_result.connect(self._on_counts_ready)
        self._count_worker.start()

    def _compute_counts(self) -> dict:
        counts = {}
        exts = self.config.get("video_extensions", [])
        af = self.config.get("archive_folder", "")
        for folder in self.config.get("folders", []):
            path = folder.get("path", "")
            if not os.path.isdir(path):
                counts[path] = 0
                continue
            exclude = [af] if af else []
            if self.config.get("cleanup_mode") == "archive":
                exclude.append(os.path.join(path, "auto_archived"))
            try:
                files = scanner.scan_new_files([path], exts, self.state, exclude_folders=exclude)
                counts[path] = len(files)
            except Exception:  # noqa: BLE001
                counts[path] = 0
        return {"counts": counts}

    def _on_counts_ready(self, result: dict) -> None:
        counts = result.get("counts", {})
        for path, card in self._cards.items():
            card.set_pending(counts.get(path, 0))

    # ---------- 导航 ----------

    def _add_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择监控文件夹")
        if not path:
            return
        if any(f.get("path") == path for f in self.config.get("folders", [])):
            QMessageBox.information(self, "提示", "该文件夹已在列表中。")
            return
        self.config.data.setdefault("folders", []).append({"path": path, "enabled": True})
        self.config.save()
        self.refresh()

    def _open_folder(self, path: str) -> None:
        self.detail_page.set_folder(path)
        self.stack.setCurrentWidget(self.detail_page)

    def _back_to_cards(self) -> None:
        self.stack.setCurrentWidget(self.cards_page)
        self.refresh()

    def _on_folder_upload_started(self, path: str) -> None:
        self._uploading.add(path)
        card = self._cards.get(path)
        if card:
            card.set_uploading(True)

    def _on_folder_upload_finished(self, path: str) -> None:
        self._uploading.discard(path)
        self.refresh()

    # ---------- 上传 ----------

    def run_now(self) -> None:
        """立即上传全部文件夹（也供定时任务调用）。"""
        if self._run_worker is not None and self._run_worker.isRunning():
            self.log_label.setText("正在运行中，请稍候…")
            return
        self.log_label.setText("开始运行…")
        self._run_worker = RunWorker(
            lambda emit: pipeline.run_once(self.config.data, self.state, on_progress=emit),
            self,
        )
        self._run_worker.progress.connect(self.log_label.setText)
        self._run_worker.finished_result.connect(self._on_run_done)
        self._run_worker.start()

    def _on_run_done(self, result: dict) -> None:
        self.log_label.setText(result.get("message", ""))
        self._notify_result(result.get("event", ""), result.get("message", ""))
        self.refresh()

    def run_folder(self, path: str) -> None:
        """定时任务触发：上传单个文件夹。"""
        if self._run_worker is not None and self._run_worker.isRunning():
            return
        self._on_folder_upload_started(path)
        self.log_label.setText(f"定时触发：{os.path.basename(path)}")
        self._run_worker = RunWorker(
            lambda emit: pipeline.run_folder(self.config.data, path, self.state, on_progress=emit),
            self,
        )
        self._run_worker.progress.connect(self.log_label.setText)
        self._run_worker.finished_result.connect(lambda r: self._on_folder_run_done(path, r))
        self._run_worker.start()

    def _on_folder_run_done(self, path: str, result: dict) -> None:
        self._on_folder_upload_finished(path)
        self.log_label.setText(result.get("message", ""))
        self._notify_result(result.get("event", ""), result.get("message", ""))

    def _notify_result(self, event: str, msg: str) -> None:
        if event == "success":
            self._notify("上传成功", msg)
        elif event == "partial":
            self._notify("上传完成（部分失败）", msg)
        elif event == "failed":
            self._notify("上传失败", msg)
        elif event in ("login_expired", "no_login"):
            self._notify("登录失效", msg)

    # ---------- 更新 ----------

    def _on_update_btn_clicked(self) -> None:
        if self._update_available:
            self._start_download_update()
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
            self._latest = info.get("latest", "")
            self._latest_url = info.get("url", "")
            self._asset_url = info.get("asset_url", "")
            self.version_label.setText(f"当前 v{VERSION} → 新版本 v{self._latest}")
            self.update_btn.setText(f"下载并安装 v{self._latest}")
        else:
            self._update_available = False
            self.version_label.setText(f"已是最新版本 v{VERSION}")
            self.update_btn.setText("检查更新")

    def _on_update_failed(self) -> None:
        self.update_btn.setEnabled(True)
        self.update_btn.setText("检查更新")
        self.version_label.setText(f"当前版本 v{VERSION}（检查失败）")

    def _start_download_update(self) -> None:
        if not getattr(sys, "frozen", False):
            # 源码运行无法自更新，跳转下载页
            webbrowser.open(self._latest_url)
            return
        ret = QMessageBox.question(self, "更新", f"发现新版本 v{self._latest}，是否下载并安装？")
        if ret != QMessageBox.Yes:
            return
        exe_dir = os.path.dirname(sys.executable)
        self._new_exe_path = os.path.join(exe_dir, "BiliAutoUpload_new.exe")
        self.update_btn.setEnabled(False)
        self.update_btn.setText("下载中…")
        self._download_worker = RunWorker(lambda emit: self._do_download(emit), self)
        self._download_worker.progress.connect(self.update_btn.setText)
        self._download_worker.finished_result.connect(self._on_download_done)
        self._download_worker.start()

    def _do_download(self, emit) -> dict:
        def progress(done: int, total: int) -> None:
            if total:
                emit(f"下载中… {int(done / total * 100)}%")
            else:
                emit(f"下载中… {done // (1024 * 1024)} MB")

        ok = updater.download_latest(self._asset_url, self._new_exe_path, on_progress=progress)
        return {"ok": ok}

    def _on_download_done(self, result: dict) -> None:
        self.update_btn.setEnabled(True)
        self.update_btn.setText("检查更新")
        if not result.get("ok"):
            QMessageBox.warning(self, "更新失败", "下载失败，请稍后重试。")
            return
        ret = QMessageBox.question(self, "更新", f"新版本 v{self._latest} 已下载，是否立即重启并更新？")
        if ret == QMessageBox.Yes:
            # apply_update 内部会 os._exit 立即退出，由 update.bat 完成替换与重启
            updater.apply_update(self._new_exe_path)
        else:
            self.version_label.setText(f"已下载 v{self._latest}，重启后生效")
