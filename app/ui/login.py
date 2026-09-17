"""登录页：扫码登录 + Cookie 登录。"""

import asyncio
import os
import tempfile

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core import auth

from .workers import AsyncTask


class QrLoginWorker(QThread):
    """后台生成二维码并轮询扫码状态。"""

    qr_ready = Signal(str)  # 二维码图片路径
    status = Signal(str)  # 中间状态文字
    done = Signal(str)  # 登录成功，参数为昵称
    timeout = Signal()
    error = Signal(str)

    def __init__(self, qr_path: str, parent=None) -> None:
        super().__init__(parent)
        self.qr_path = qr_path
        self._running = True

    def stop(self) -> None:
        self._running = False

    async def _work(self) -> None:
        session = auth.QrLoginSession()
        await session.generate(self.qr_path)
        self.qr_ready.emit(self.qr_path)

        while self._running:
            event = await session.poll()
            if event == auth.QrCodeLoginEvents.DONE:
                cred = session.credential()
                auth.save_credential(cred)
                try:
                    name = await auth.get_nickname(cred)
                except Exception:
                    name = ""
                self.done.emit(name)
                return
            if event == auth.QrCodeLoginEvents.TIMEOUT:
                self.timeout.emit()
                return
            if event == auth.QrCodeLoginEvents.CONF:
                self.status.emit("已扫码，请在手机上确认登录")
            else:
                self.status.emit("等待扫码…")
            await asyncio.sleep(2)

    def run(self) -> None:
        try:
            asyncio.run(self._work())
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


class LoginPage(QWidget):
    """登录页。"""

    login_changed = Signal()

    def __init__(self, config) -> None:
        super().__init__()
        self.config = config
        self._qr_worker = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("登录")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.status_label = QLabel("")
        self.status_label.setObjectName("hint")
        layout.addWidget(self.status_label)

        # ---- 扫码登录 ----
        qr_group = QGroupBox("扫码登录")
        qr_layout = QVBoxLayout(qr_group)
        qr_layout.setSpacing(12)

        self.qr_label = QLabel("点击下方按钮生成二维码")
        self.qr_label.setFixedSize(220, 220)
        self.qr_label.setAlignment(self._center())
        qr_layout.addWidget(self.qr_label, alignment=self._center())

        self.qr_status = QLabel("")
        self.qr_status.setObjectName("hint")
        qr_layout.addWidget(self.qr_status, alignment=self._center())

        self.qr_btn = QPushButton("生成二维码")
        self.qr_btn.setObjectName("primaryButton")
        self.qr_btn.clicked.connect(self._start_qr_login)
        qr_layout.addWidget(self.qr_btn, alignment=self._center())
        layout.addWidget(qr_group)

        # ---- Cookie 登录 ----
        cookie_group = QGroupBox("Cookie 登录（备选）")
        cookie_layout = QVBoxLayout(cookie_group)
        cookie_layout.setSpacing(12)
        hint = QLabel("从浏览器复制 B 站的 Cookie，粘贴 SESSDATA 等字段（也可只粘贴 SESSDATA 值）")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        cookie_layout.addWidget(hint)
        self.cookie_edit = QPlainTextEdit()
        self.cookie_edit.setPlaceholderText("SESSDATA=xxx; bili_jct=yyy; ...")
        self.cookie_edit.setFixedHeight(80)
        cookie_layout.addWidget(self.cookie_edit)
        self.cookie_btn = QPushButton("用 Cookie 登录")
        self.cookie_btn.clicked.connect(self._cookie_login)
        cookie_layout.addWidget(self.cookie_btn)
        layout.addWidget(cookie_group)

        layout.addStretch()

    @staticmethod
    def _center():
        from PySide6.QtCore import Qt

        return Qt.AlignCenter

    def refresh(self) -> None:
        cred = auth.load_credential()
        if cred is None:
            self.status_label.setText("当前状态：未登录")
        else:
            self.status_label.setText("当前状态：已保存登录凭据（有效性以仪表盘检测为准）")

    # ---------- 扫码 ----------

    def _start_qr_login(self) -> None:
        if self._qr_worker is not None and self._qr_worker.isRunning():
            return
        self.qr_btn.setEnabled(False)
        self.qr_status.setText("正在生成二维码…")
        qr_path = os.path.join(tempfile.gettempdir(), "bili_qr_login.png")

        self._qr_worker = QrLoginWorker(qr_path, self)
        self._qr_worker.qr_ready.connect(self._on_qr_ready)
        self._qr_worker.status.connect(self.qr_status.setText)
        self._qr_worker.done.connect(self._on_qr_done)
        self._qr_worker.timeout.connect(self._on_qr_timeout)
        self._qr_worker.error.connect(self._on_qr_error)
        self._qr_worker.finished.connect(self._on_qr_finished)
        self._qr_worker.start()

    def _on_qr_ready(self, path: str) -> None:
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            self.qr_label.setPixmap(
                pixmap.scaled(210, 210, self._aspect_mode(), self._smooth_mode())
            )
        self.qr_status.setText("请用手机 B 站 App 扫码")

    @staticmethod
    def _aspect_mode():
        from PySide6.QtCore import Qt

        return Qt.KeepAspectRatio

    @staticmethod
    def _smooth_mode():
        from PySide6.QtCore import Qt

        return Qt.SmoothTransformation

    def _on_qr_done(self, name: str) -> None:
        self.qr_status.setText(f"登录成功：{name or '已登录'}")
        self.login_changed.emit()

    def _on_qr_timeout(self) -> None:
        self.qr_status.setText("二维码已过期，请重新生成")

    def _on_qr_error(self, msg: str) -> None:
        self.qr_status.setText(f"登录出错：{msg}")

    def _on_qr_finished(self) -> None:
        self.qr_btn.setEnabled(True)
        self._qr_worker = None

    # ---------- Cookie ----------

    def _cookie_login(self) -> None:
        text = self.cookie_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "请先粘贴 Cookie")
            return
        try:
            cred = auth.credential_from_cookie_text(text)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "提示", f"Cookie 解析失败：{e}")
            return
        if not cred.has_sessdata():
            QMessageBox.warning(self, "提示", "未解析到 SESSDATA，请检查 Cookie")
            return

        self.cookie_btn.setEnabled(False)
        self.cookie_btn.setText("验证中…")

        def make_coro():
            async def _verify():
                valid = await auth.check_login(cred)
                name = await auth.get_nickname(cred) if valid else ""
                return valid, name

            return _verify

        self._cookie_task = AsyncTask(make_coro, self)
        self._cookie_task.done.connect(self._on_cookie_done)
        self._cookie_task.error.connect(self._on_cookie_error)
        self._cookie_task.start()

    def _on_cookie_done(self, result) -> None:
        self.cookie_btn.setEnabled(True)
        self.cookie_btn.setText("用 Cookie 登录")
        valid, name = result
        if valid:
            cred = auth.credential_from_cookie_text(self.cookie_edit.toPlainText())
            auth.save_credential(cred)
            self.status_label.setText(f"当前状态：已登录 {name or ''}")
            self.login_changed.emit()
            QMessageBox.information(self, "登录成功", f"已登录：{name or '成功'}")
        else:
            QMessageBox.warning(self, "登录失败", "Cookie 无效或已过期，请重新获取")

    def _on_cookie_error(self, msg: str) -> None:
        self.cookie_btn.setEnabled(True)
        self.cookie_btn.setText("用 Cookie 登录")
        QMessageBox.warning(self, "登录失败", f"验证失败：{msg}")
