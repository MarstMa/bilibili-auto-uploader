"""设置页：所有可自定义项的表单。"""

from copy import deepcopy

from PySide6.QtCore import QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.config import DEFAULT_CONFIG

# 常见分区（名称, tid）。如需更细的子分区，可手动改 config.json 的 tid。
PARTITIONS = [
    ("生活", 160), ("科技", 188), ("游戏", 4), ("知识", 36), ("影视", 181),
    ("动画", 1), ("音乐", 3), ("娱乐", 5), ("时尚", 155), ("美食", 211),
    ("动物圈", 217), ("舞蹈", 129), ("鬼畜", 119), ("资讯", 202), ("运动", 234),
    ("汽车", 223), ("纪录片", 177),
]


class SettingsPage(QWidget):
    """设置页。修改后点「保存」写入 config.json。"""

    settings_saved = Signal()

    def __init__(self, config) -> None:
        super().__init__()
        self.config = config
        self._build()
        self.load()

    # ---------- 构建 ----------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(16)

        title = QLabel("设置")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        form = QVBoxLayout(body)
        form.setContentsMargins(0, 0, 8, 0)
        form.setSpacing(16)

        form.addWidget(self._build_watch_group())
        form.addWidget(self._build_schedule_group())
        form.addWidget(self._build_naming_group())
        form.addWidget(self._build_submit_group())
        form.addWidget(self._build_upload_group())
        form.addWidget(self._build_cleanup_group())
        form.addWidget(self._build_misc_group())

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # 底部按钮
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

    def _row(self, form: QFormLayout, label: str, widget: QWidget) -> None:
        form.addRow(label, widget)

    # 监控
    def _build_watch_group(self) -> QGroupBox:
        g = QGroupBox("监控")
        form = QFormLayout(g)
        self.folder_list = QListWidget()
        self.folder_list.setMinimumHeight(80)
        folder_btns = QVBoxLayout()
        add_btn = QPushButton("添加文件夹")
        add_btn.clicked.connect(self._add_folder)
        del_btn = QPushButton("移除选中")
        del_btn.clicked.connect(self._remove_folder)
        folder_btns.addWidget(add_btn)
        folder_btns.addWidget(del_btn)
        folder_btns.addStretch()
        folder_row = QWidget()
        h = QHBoxLayout(folder_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.folder_list, 1)
        h.addLayout(folder_btns)
        self._row(form, "监控文件夹", folder_row)

        self.ext_edit = QLineEdit()
        self._row(form, "视频扩展名", self.ext_edit)
        hint = QLabel("扩展名用逗号或空格分隔，如 .mp4, .flv, .mkv")
        hint.setObjectName("hint")
        form.addRow("", hint)
        return g

    # 定时
    def _build_schedule_group(self) -> QGroupBox:
        g = QGroupBox("定时")
        form = QFormLayout(g)
        self.schedule_edit = QLineEdit()
        self._row(form, "每天运行时刻", self.schedule_edit)
        hint = QLabel("逗号分隔，如 08:00, 20:30")
        hint.setObjectName("hint")
        form.addRow("", hint)
        return g

    # 命名
    def _build_naming_group(self) -> QGroupBox:
        g = QGroupBox("标题与命名")
        form = QFormLayout(g)
        self.title_edit = QLineEdit()
        self._row(form, "主标题模板", self.title_edit)
        self.part_title_edit = QLineEdit()
        self._row(form, "分P标题模板", self.part_title_edit)
        self.desc_edit = QLineEdit()
        self._row(form, "简介模板", self.desc_edit)
        self.tags_edit = QLineEdit()
        self._row(form, "标签", self.tags_edit)
        self.cover_edit = QLineEdit()
        cover_row = QWidget()
        h = QHBoxLayout(cover_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.cover_edit, 1)
        browse = QPushButton("浏览")
        browse.clicked.connect(self._browse_cover)
        h.addWidget(browse)
        self._row(form, "封面图片", cover_row)
        hint = QLabel(
            "可用变量：{date} {time} {index} {part_index} {original_name} {folder} {count}"
        )
        hint.setObjectName("hint")
        form.addRow("", hint)
        return g

    # 投稿
    def _build_submit_group(self) -> QGroupBox:
        g = QGroupBox("投稿信息")
        form = QFormLayout(g)
        self.tid_combo = QComboBox()
        for name, tid in PARTITIONS:
            self.tid_combo.addItem(name, tid)
        self._row(form, "分区", self.tid_combo)

        self.copyright_combo = QComboBox()
        self.copyright_combo.addItem("原创", 1)
        self.copyright_combo.addItem("转载", 2)
        self._row(form, "版权", self.copyright_combo)

        self.source_edit = QLineEdit()
        self._row(form, "转载来源", self.source_edit)
        return g

    # 上传与发布
    def _build_upload_group(self) -> QGroupBox:
        g = QGroupBox("上传与发布")
        form = QFormLayout(g)

        self.strategy_combo = QComboBox()
        self.strategy_combo.addItem("一个稿件多分P", "multipart")
        self.strategy_combo.addItem("物理合并成一个视频", "merge")
        self.strategy_combo.addItem("每个文件独立上传", "separate")
        self._row(form, "多文件策略", self.strategy_combo)

        self.split_spin = QDoubleSpinBox()
        self.split_spin.setRange(0.5, 100.0)
        self.split_spin.setDecimals(1)
        self.split_spin.setSuffix(" GB")
        self._row(form, "拆分阈值", self.split_spin)

        self.publish_combo = QComboBox()
        self.publish_combo.addItem("直接发布", "public")
        self.publish_combo.addItem("延迟发布（上传后 N 小时）", "timed")
        self.publish_combo.addItem("定时发布（到指定时刻）", "schedule")
        self.publish_combo.currentIndexChanged.connect(self._on_publish_mode_changed)
        self._row(form, "发布方式", self.publish_combo)

        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.1, 72.0)
        self.delay_spin.setDecimals(1)
        self.delay_spin.setSuffix(" 小时")
        self._row(form, "延迟公开时长", self.delay_spin)

        self.schedule_time_edit = QTimeEdit()
        self.schedule_time_edit.setDisplayFormat("HH:mm")
        self.schedule_time_edit.setTime(QTime(20, 0))
        self._row(form, "定时发布时刻", self.schedule_time_edit)

        self._on_publish_mode_changed()

        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 10)
        self._row(form, "上传并发数", self.workers_spin)

        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self._row(form, "失败重试次数", self.retry_spin)
        return g

    # 清理
    def _build_cleanup_group(self) -> QGroupBox:
        g = QGroupBox("上传后的本地文件处理")
        form = QFormLayout(g)
        self.cleanup_combo = QComboBox()
        self.cleanup_combo.addItem("移动到归档文件夹", "archive")
        self.cleanup_combo.addItem("永久删除", "delete")
        self.cleanup_combo.addItem("不处理", "none")
        self._row(form, "清理方式", self.cleanup_combo)

        self.archive_edit = QLineEdit()
        archive_row = QWidget()
        h = QHBoxLayout(archive_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.archive_edit, 1)
        browse = QPushButton("浏览")
        browse.clicked.connect(self._browse_archive)
        h.addWidget(browse)
        self._row(form, "归档目录", archive_row)
        hint = QLabel("留空则归档到各监控文件夹下的 auto_archived")
        hint.setObjectName("hint")
        form.addRow("", hint)
        return g

    # 其他
    def _build_misc_group(self) -> QGroupBox:
        g = QGroupBox("其他")
        form = QFormLayout(g)
        self.tray_check = QCheckBox("关闭窗口时最小化到系统托盘")
        form.addRow(self.tray_check)
        self.autostart_check = QCheckBox("开机自启（注册到系统启动项）")
        form.addRow(self.autostart_check)
        return g

    # ---------- 交互 ----------

    def _add_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择监控文件夹")
        if path:
            self.folder_list.addItem(path)

    def _remove_folder(self) -> None:
        for item in self.folder_list.selectedItems():
            self.folder_list.takeItem(self.folder_list.row(item))

    def _browse_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", "", "图片 (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            self.cover_edit.setText(path)

    def _browse_archive(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择归档目录")
        if path:
            self.archive_edit.setText(path)

    def _reset(self) -> None:
        self.config.data = deepcopy(DEFAULT_CONFIG)
        self.load()

    # ---------- 读写 ----------

    def _set_combo(self, combo: QComboBox, value) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _on_publish_mode_changed(self) -> None:
        mode = self.publish_combo.currentData()
        self.delay_spin.setEnabled(mode == "timed")
        self.schedule_time_edit.setEnabled(mode == "schedule")

    @staticmethod
    def _parse_time(hhmm) -> QTime:
        try:
            h, m = (int(x) for x in str(hhmm).split(":"))
            return QTime(h, m)
        except (ValueError, AttributeError):
            return QTime(20, 0)

    def load(self) -> None:
        """把 config 的值填充到表单。"""
        c = self.config.data
        self.folder_list.clear()
        self.folder_list.addItems(c.get("watch_folders", []))
        self.ext_edit.setText(" ".join(c.get("video_extensions", [])))
        self.schedule_edit.setText(", ".join(c.get("schedule_times", [])))
        self.title_edit.setText(c.get("title_template", ""))
        self.part_title_edit.setText(c.get("part_title_template", ""))
        self.desc_edit.setText(c.get("desc_template", ""))
        self.tags_edit.setText(", ".join(c.get("tags", [])))
        self.cover_edit.setText(c.get("cover_path", ""))
        self._set_combo(self.tid_combo, c.get("tid", 160))
        self._set_combo(self.copyright_combo, c.get("copyright", 1))
        self.source_edit.setText(c.get("source", ""))
        self._set_combo(self.strategy_combo, c.get("multi_file_strategy", "multipart"))
        self.split_spin.setValue(float(c.get("split_threshold_gb", 3.5)))
        self._set_combo(self.publish_combo, c.get("publish_mode", "timed"))
        self.delay_spin.setValue(float(c.get("publish_delay_hours", 2.0)))
        self.schedule_time_edit.setTime(self._parse_time(c.get("publish_schedule_time", "20:00")))
        self.workers_spin.setValue(int(c.get("upload_workers", 3)))
        self.retry_spin.setValue(int(c.get("max_retry", 3)))
        self._set_combo(self.cleanup_combo, c.get("cleanup_mode", "archive"))
        self.archive_edit.setText(c.get("archive_folder", ""))
        self.tray_check.setChecked(bool(c.get("minimize_to_tray", True)))
        self.autostart_check.setChecked(bool(c.get("auto_start", False)))

    def save(self) -> None:
        """把表单值写回 config 并落盘。"""
        c = self.config.data
        c["watch_folders"] = [
            self.folder_list.item(i).text() for i in range(self.folder_list.count())
        ]
        c["video_extensions"] = [
            x.strip() for x in self.ext_edit.text().replace(",", " ").split() if x.strip()
        ]
        c["schedule_times"] = [
            x.strip() for x in self.schedule_edit.text().replace("，", ",").split(",") if x.strip()
        ]
        c["title_template"] = self.title_edit.text().strip()
        c["part_title_template"] = self.part_title_edit.text().strip()
        c["desc_template"] = self.desc_edit.text().strip()
        c["tags"] = [
            x.strip() for x in self.tags_edit.text().replace("，", ",").split(",") if x.strip()
        ]
        c["cover_path"] = self.cover_edit.text().strip()
        c["tid"] = int(self.tid_combo.currentData())
        c["copyright"] = int(self.copyright_combo.currentData())
        c["source"] = self.source_edit.text().strip()
        c["multi_file_strategy"] = self.strategy_combo.currentData()
        c["split_threshold_gb"] = round(self.split_spin.value(), 1)
        c["publish_mode"] = self.publish_combo.currentData()
        c["publish_delay_hours"] = round(self.delay_spin.value(), 1)
        c["publish_schedule_time"] = self.schedule_time_edit.time().toString("HH:mm")
        c["upload_workers"] = self.workers_spin.value()
        c["max_retry"] = self.retry_spin.value()
        c["cleanup_mode"] = self.cleanup_combo.currentData()
        c["archive_folder"] = self.archive_edit.text().strip()
        c["minimize_to_tray"] = self.tray_check.isChecked()
        c["auto_start"] = self.autostart_check.isChecked()

        self.config.save()
        self.settings_saved.emit()
        QMessageBox.information(self, "已保存", "设置已保存。")

    def refresh(self) -> None:
        """导航到本页时不覆盖用户未保存的编辑。"""
        pass
