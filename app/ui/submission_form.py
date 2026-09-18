"""可复用的「投稿设置」表单：供全局默认设置页与文件夹详情页共用。"""

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.zones import ZONE_TREE, find_zone_for_tid

# 各字段的说明文字（悬浮提示 + 需要时的小字说明）
TOOLTIPS = {
    "title_template": "稿件标题。可用变量：{date}日期、{time}时间、{index}当天序号、{original_name}原文件名、{folder}文件夹名、{count}总数",
    "part_title_template": "每个分P（每一集）的标题。常用 {part_index} 分P序号，例如：P{part_index}",
    "date_offset_days": "日期偏移（天）。-1 表示标题里的 {date} 用昨天，0 表示今天，正数表示未来",
    "desc_template": "稿件简介，可含标题的变量，留空则不写简介",
    "tags": "稿件标签，逗号分隔，最多 10 个",
    "cover_path": "封面图片路径，留空则自动从视频首帧截取",
    "tid": "投稿分区（B 站分类）",
    "copyright": "原创=自制；转载=搬运他人视频（需填来源）",
    "source": "转载时必填的原始来源地址",
    "multi_file_strategy": "多个新视频怎么处理：多分P=一个稿件多集；合并=物理拼成一个；独立=各自成稿",
    "split_threshold_gb": "单个视频超过该大小时，自动拆成多个分P",
    "publish_mode": "直接发布=立即公开；延迟发布=上传后 N 小时公开；定时发布=到指定时刻公开",
    "publish_delay_hours": "延迟发布模式下，上传后多少小时才公开",
    "publish_schedule_time": "定时发布模式下，稿件在哪个时刻公开",
    "cleanup_mode": "上传成功后本地文件怎么处理：归档=移到归档目录；删除=直接删除；不处理=保留原样",
    "archive_folder": "归档目标目录，留空则归档到各监控文件夹下的 auto_archived",
}


class SubmissionForm(QWidget):
    """投稿相关设置表单。load(data) 读取，save_to(data) 写回。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        outer.addLayout(form)

        def row(label, widget, tip_key):
            widget.setToolTip(TOOLTIPS[tip_key])
            form.addRow(label, widget)
            return widget

        self.title_edit = row("主标题模板", QLineEdit(), "title_template")
        self.part_title_edit = row("分P标题模板", QLineEdit(), "part_title_template")
        self.date_offset_spin = QSpinBox()
        self.date_offset_spin.setRange(-30, 30)
        self.date_offset_spin.setSuffix(" 天")
        row("日期偏移", self.date_offset_spin, "date_offset_days")
        self.desc_edit = row("简介模板", QLineEdit(), "desc_template")
        self.tags_edit = row("标签", QLineEdit(), "tags")

        self.cover_edit = QLineEdit()
        cover_box = QWidget()
        h = QHBoxLayout(cover_box)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.cover_edit, 1)
        browse = self._browse_button("浏览", self._pick_cover)
        h.addWidget(browse)
        row("封面图片", cover_box, "cover_path")

        self.zone_combo = QComboBox()
        for name, _zone_tid, _subs in ZONE_TREE:
            self.zone_combo.addItem(name)
        self.zone_combo.currentIndexChanged.connect(self._on_zone_changed)
        row("分区", self.zone_combo, "tid")

        self.subzone_combo = QComboBox()
        row("二级分区", self.subzone_combo, "tid")
        self._on_zone_changed()

        self.copyright_combo = QComboBox()
        self.copyright_combo.addItem("原创", 1)
        self.copyright_combo.addItem("转载", 2)
        row("版权", self.copyright_combo, "copyright")

        self.source_edit = row("转载来源", QLineEdit(), "source")

        self.strategy_combo = QComboBox()
        self.strategy_combo.addItem("一个稿件多分P", "multipart")
        self.strategy_combo.addItem("物理合并成一个视频", "merge")
        self.strategy_combo.addItem("每个文件独立上传", "separate")
        row("多文件策略", self.strategy_combo, "multi_file_strategy")

        self.split_spin = QDoubleSpinBox()
        self.split_spin.setRange(0.5, 100.0)
        self.split_spin.setDecimals(1)
        self.split_spin.setSuffix(" GB")
        row("拆分阈值", self.split_spin, "split_threshold_gb")

        self.publish_combo = QComboBox()
        self.publish_combo.addItem("直接发布", "public")
        self.publish_combo.addItem("延迟发布（上传后 N 小时）", "timed")
        self.publish_combo.addItem("定时发布（到指定时刻）", "schedule")
        self.publish_combo.currentIndexChanged.connect(self._on_publish_mode_changed)
        row("发布方式", self.publish_combo, "publish_mode")

        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.1, 72.0)
        self.delay_spin.setDecimals(1)
        self.delay_spin.setSuffix(" 小时")
        row("延迟公开时长", self.delay_spin, "publish_delay_hours")

        self.schedule_time_edit = QTimeEdit()
        self.schedule_time_edit.setDisplayFormat("HH:mm")
        self.schedule_time_edit.setTime(QTime(20, 0))
        row("定时发布时刻", self.schedule_time_edit, "publish_schedule_time")

        self.cleanup_combo = QComboBox()
        self.cleanup_combo.addItem("移动到归档文件夹", "archive")
        self.cleanup_combo.addItem("永久删除", "delete")
        self.cleanup_combo.addItem("不处理", "none")
        row("清理方式", self.cleanup_combo, "cleanup_mode")

        self.archive_edit = QLineEdit()
        archive_box = QWidget()
        h2 = QHBoxLayout(archive_box)
        h2.setContentsMargins(0, 0, 0, 0)
        h2.addWidget(self.archive_edit, 1)
        h2.addWidget(self._browse_button("浏览", self._pick_archive))
        row("归档目录", archive_box, "archive_folder")

        self._on_publish_mode_changed()

    @staticmethod
    def _browse_button(text: str, handler) -> QWidget:
        from PySide6.QtWidgets import QPushButton

        btn = QPushButton(text)
        btn.clicked.connect(handler)
        return btn

    def _pick_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", "", "图片 (*.png *.jpg *.jpeg *.webp)"
        )
        if path:
            self.cover_edit.setText(path)

    def _pick_archive(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择归档目录")
        if path:
            self.archive_edit.setText(path)

    def _on_publish_mode_changed(self) -> None:
        mode = self.publish_combo.currentData()
        self.delay_spin.setEnabled(mode == "timed")
        self.schedule_time_edit.setEnabled(mode == "schedule")

    def _on_zone_changed(self) -> None:
        zi = self.zone_combo.currentIndex()
        self.subzone_combo.clear()
        if 0 <= zi < len(ZONE_TREE):
            for sub_name, sub_tid in ZONE_TREE[zi][2]:
                self.subzone_combo.addItem(sub_name, sub_tid)

    @staticmethod
    def _set_combo(combo: QComboBox, value) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    @staticmethod
    def _parse_time(hhmm) -> QTime:
        try:
            h, m = (int(x) for x in str(hhmm).split(":"))
            return QTime(h, m)
        except (ValueError, AttributeError):
            return QTime(20, 0)

    def load(self, data: dict) -> None:
        """用字典里的值填充表单。"""
        self.title_edit.setText(str(data.get("title_template", "")))
        self.part_title_edit.setText(str(data.get("part_title_template", "")))
        self.date_offset_spin.setValue(int(data.get("date_offset_days", 0)))
        self.desc_edit.setText(str(data.get("desc_template", "")))
        self.tags_edit.setText(", ".join(data.get("tags", []) or []))
        self.cover_edit.setText(str(data.get("cover_path", "")))
        zi, si = find_zone_for_tid(data.get("tid", 21))
        self.zone_combo.setCurrentIndex(zi)  # 触发 _on_zone_changed 填充二级分区
        self.subzone_combo.setCurrentIndex(si)
        self._set_combo(self.copyright_combo, data.get("copyright", 1))
        self.source_edit.setText(str(data.get("source", "")))
        self._set_combo(self.strategy_combo, data.get("multi_file_strategy", "multipart"))
        self.split_spin.setValue(float(data.get("split_threshold_gb", 3.5)))
        self._set_combo(self.publish_combo, data.get("publish_mode", "timed"))
        self.delay_spin.setValue(float(data.get("publish_delay_hours", 2.0)))
        self.schedule_time_edit.setTime(self._parse_time(data.get("publish_schedule_time", "20:00")))
        self._set_combo(self.cleanup_combo, data.get("cleanup_mode", "archive"))
        self.archive_edit.setText(str(data.get("archive_folder", "")))
        self._on_publish_mode_changed()

    def save_to(self, data: dict) -> None:
        """把表单值写入字典（写入全部投稿字段，形成完整快照）。"""
        data["title_template"] = self.title_edit.text().strip()
        data["part_title_template"] = self.part_title_edit.text().strip()
        data["date_offset_days"] = self.date_offset_spin.value()
        data["desc_template"] = self.desc_edit.text().strip()
        data["tags"] = [x.strip() for x in self.tags_edit.text().replace("，", ",").split(",") if x.strip()]
        data["cover_path"] = self.cover_edit.text().strip()
        data["tid"] = int(self.subzone_combo.currentData())
        data["copyright"] = int(self.copyright_combo.currentData())
        data["source"] = self.source_edit.text().strip()
        data["multi_file_strategy"] = self.strategy_combo.currentData()
        data["split_threshold_gb"] = round(self.split_spin.value(), 1)
        data["publish_mode"] = self.publish_combo.currentData()
        data["publish_delay_hours"] = round(self.delay_spin.value(), 1)
        data["publish_schedule_time"] = self.schedule_time_edit.time().toString("HH:mm")
        data["cleanup_mode"] = self.cleanup_combo.currentData()
        data["archive_folder"] = self.archive_edit.text().strip()
