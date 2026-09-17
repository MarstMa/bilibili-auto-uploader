"""文件夹详情页（二级菜单）：逐文件夹投稿设置 + 立即上传 + 删除。"""

import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core import pipeline
from app.core.config import get_folder_effective_config

from .submission_form import SubmissionForm
from .workers import RunWorker


class FolderDetailPage(QWidget):
    """单个文件夹的详情页。"""

    back_requested = Signal()
    deleted = Signal()

    def __init__(self, config, state, notify=None) -> None:
        super().__init__()
        self.config = config
        self.state = state
        self._notify = notify or (lambda t, m: None)
        self.folder_path = ""
        self._run_worker = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        # 顶部标题栏
        top = QHBoxLayout()
        back_btn = QPushButton("← 返回")
        back_btn.clicked.connect(self.back_requested.emit)
        top.addWidget(back_btn)
        self.title_label = QLabel("文件夹")
        self.title_label.setObjectName("sectionTitle")
        top.addWidget(self.title_label)
        top.addStretch()
        layout.addLayout(top)

        # 信息卡
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 14, 18, 14)
        card_layout.setSpacing(8)
        self.path_label = QLabel("")
        self.path_label.setObjectName("hint")
        self.path_label.setWordWrap(True)
        card_layout.addWidget(self.path_label)
        self.status_label = QLabel("")
        card_layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        run_btn = QPushButton("立即上传此文件夹")
        run_btn.setObjectName("primaryButton")
        run_btn.clicked.connect(self.run_folder_now)
        actions.addWidget(run_btn)
        del_btn = QPushButton("删除此文件夹")
        del_btn.setObjectName("dangerButton")
        del_btn.clicked.connect(self.delete_folder)
        actions.addWidget(del_btn)
        actions.addStretch()
        card_layout.addLayout(actions)
        layout.addWidget(card)

        # 投稿设置表单
        self.form = SubmissionForm()
        self.form_card = QFrame()
        self.form_card.setObjectName("card")
        form_layout = QVBoxLayout(self.form_card)
        form_layout.setContentsMargins(18, 14, 18, 14)
        hint = QLabel("该文件夹的投稿设置（留空项会继承全局默认值，保存后形成快照）")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form_layout.addWidget(hint)
        form_layout.addWidget(self.form)
        layout.addWidget(self.form_card, 1)

        # 保存
        save_btn = QPushButton("保存此文件夹设置")
        save_btn.setObjectName("primaryButton")
        save_btn.setMinimumHeight(38)
        save_btn.clicked.connect(self.save)
        layout.addWidget(save_btn)

        # 进度
        self.log_label = QLabel("")
        self.log_label.setObjectName("hint")
        self.log_label.setWordWrap(True)
        layout.addWidget(self.log_label)

    def set_folder(self, folder_path: str) -> None:
        """切换到指定文件夹并刷新。"""
        self.folder_path = folder_path
        self.title_label.setText(os.path.basename(folder_path) or folder_path)
        self.path_label.setText(folder_path)
        self.log_label.setText("")
        self.load()

    def _find_folder(self) -> dict:
        for f in self.config.data.get("folders", []):
            if isinstance(f, dict) and f.get("path") == self.folder_path:
                return f
        f = {"path": self.folder_path}
        self.config.data.setdefault("folders", []).append(f)
        return f

    def load(self) -> None:
        """刷新状态与表单。"""
        folder = self._find_folder()
        effective = get_folder_effective_config(self.config.data, folder)
        self.form.load(effective)

        last = self.state.last_status_for_folder(self.folder_path)
        if last:
            title, bvid, _status, created_at = last
            self.status_label.setText(f"最近上传：{title or ''}（{created_at or ''}）")
        else:
            self.status_label.setText("暂无上传记录")

    def save(self) -> None:
        folder = self._find_folder()
        self.form.save_to(folder)
        self.config.save()
        QMessageBox.information(self, "已保存", "该文件夹的设置已保存。")

    def delete_folder(self) -> None:
        name = os.path.basename(self.folder_path) or self.folder_path
        ret = QMessageBox.question(
            self, "删除文件夹", f"确定从列表里移除「{name}」吗？（不会删除磁盘上的文件）"
        )
        if ret != QMessageBox.Yes:
            return
        folders = self.config.data.get("folders", [])
        self.config.data["folders"] = [
            f for f in folders if not (isinstance(f, dict) and f.get("path") == self.folder_path)
        ]
        self.config.save()
        self.deleted.emit()

    def run_folder_now(self) -> None:
        if self._run_worker is not None and self._run_worker.isRunning():
            self.log_label.setText("正在运行中，请稍候…")
            return
        self.log_label.setText("开始运行…")
        path = self.folder_path
        self._run_worker = RunWorker(
            lambda emit: pipeline.run_folder(self.config.data, path, self.state, on_progress=emit),
            self,
        )
        self._run_worker.progress.connect(self.log_label.setText)
        self._run_worker.finished_result.connect(self._on_run_done)
        self._run_worker.start()

    def _on_run_done(self, result: dict) -> None:
        msg = result.get("message", "")
        event = result.get("event", "")
        self.log_label.setText(msg)
        self.load()
        if event == "success":
            self._notify("上传成功", msg)
        elif event == "partial":
            self._notify("上传完成（部分失败）", msg)
        elif event == "failed":
            self._notify("上传失败", msg)
        elif event in ("login_expired", "no_login"):
            self._notify("登录失效", msg)
