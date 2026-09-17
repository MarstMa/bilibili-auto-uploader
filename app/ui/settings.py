"""全局设置页：全局定时、全局默认投稿设置、其它全局项。"""

from copy import deepcopy

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.config import DEFAULT_CONFIG

from .submission_form import SubmissionForm


class SettingsPage(QWidget):
    """全局设置页。"""

    settings_saved = Signal()

    def __init__(self, config) -> None:
        super().__init__()
        self.config = config
        self._build()
        self.load()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(16)

        title = QLabel("全局设置")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        form = QVBoxLayout(body)
        form.setContentsMargins(0, 0, 8, 0)
        form.setSpacing(16)

        form.addWidget(self._build_schedule_group())
        form.addWidget(self._build_defaults_group())
        form.addWidget(self._build_misc_group())

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        btns = QHBoxLayout()
        btns.addStretch()
        reset_btn = QPushButton("恢复默认")
        reset_btn.clicked.connect(self._reset)
        btns.addWidget(reset_btn)
        save_btn = QPushButton("保存")
        save_btn.setObjectName("primaryButton")
        save_btn.setMinimumWidth(120)
        save_btn.clicked.connect(self.save)
        btns.addWidget(save_btn)
        outer.addLayout(btns)

    def _build_schedule_group(self) -> QGroupBox:
        g = QGroupBox("全局定时")
        form = QFormLayout(g)

        self.schedule_edit = QLineEdit()
        self.schedule_edit.setToolTip("每天自动扫描上传的时刻，逗号分隔，如 08:00, 20:00")
        form.addRow("每天运行时刻", self.schedule_edit)

        self.ext_edit = QLineEdit()
        self.ext_edit.setToolTip("要上传的视频文件扩展名，逗号或空格分隔")
        form.addRow("视频扩展名", self.ext_edit)
        return g

    def _build_defaults_group(self) -> QGroupBox:
        g = QGroupBox("全局默认投稿设置")
        v = QVBoxLayout(g)
        hint = QLabel("以下为所有文件夹的默认投稿设置，可在每个文件夹详情里单独覆盖。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        v.addWidget(hint)
        self.form = SubmissionForm()
        v.addWidget(self.form)
        return g

    def _build_misc_group(self) -> QGroupBox:
        g = QGroupBox("其它")
        form = QFormLayout(g)

        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 10)
        self.workers_spin.setToolTip("同时上传的分P数量，越大越快但越占资源")
        form.addRow("上传并发数", self.workers_spin)

        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setToolTip("上传失败后的自动重试次数")
        form.addRow("失败重试次数", self.retry_spin)

        self.tray_check = QCheckBox("关闭窗口时最小化到系统托盘")
        self.tray_check.setToolTip("关闭窗口时不退出程序，而是最小化到托盘继续后台运行")
        form.addRow(self.tray_check)

        self.autostart_check = QCheckBox("开机自启（注册到系统启动项）")
        self.autostart_check.setToolTip("开机时自动启动本程序")
        form.addRow(self.autostart_check)
        return g

    def _reset(self) -> None:
        self.config.data = deepcopy(DEFAULT_CONFIG)
        self.load()

    def load(self) -> None:
        c = self.config.data
        self.schedule_edit.setText(", ".join(c.get("schedule_times", [])))
        self.ext_edit.setText(" ".join(c.get("video_extensions", [])))
        self.form.load(c)
        self.workers_spin.setValue(int(c.get("upload_workers", 3)))
        self.retry_spin.setValue(int(c.get("max_retry", 3)))
        self.tray_check.setChecked(bool(c.get("minimize_to_tray", True)))
        self.autostart_check.setChecked(bool(c.get("auto_start", False)))

    def save(self) -> None:
        c = self.config.data
        c["schedule_times"] = [
            x.strip() for x in self.schedule_edit.text().replace("，", ",").split(",") if x.strip()
        ]
        c["video_extensions"] = [
            x.strip() for x in self.ext_edit.text().replace(",", " ").split() if x.strip()
        ]
        self.form.save_to(c)
        c["upload_workers"] = self.workers_spin.value()
        c["max_retry"] = self.retry_spin.value()
        c["minimize_to_tray"] = self.tray_check.isChecked()
        c["auto_start"] = self.autostart_check.isChecked()

        self.config.save()
        self.settings_saved.emit()
        QMessageBox.information(self, "已保存", "全局设置已保存。")

    def refresh(self) -> None:
        pass
