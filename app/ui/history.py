"""历史记录页：展示上传历史，支持按文件夹筛选。"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class HistoryPage(QWidget):
    """历史记录页。"""

    def __init__(self, state, config) -> None:
        super().__init__()
        self.state = state
        self.config = config
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("历史记录")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        top = QHBoxLayout()
        top.addWidget(QLabel("筛选文件夹："))
        self.filter_combo = QComboBox()
        self.filter_combo.currentIndexChanged.connect(self._load)
        top.addWidget(self.filter_combo, 1)
        top.addStretch()
        layout.addLayout(top)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["文件名", "标题", "BVID", "分P数", "状态", "时间"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table)

        self.hint = QLabel("暂无记录")
        self.hint.setObjectName("hint")
        layout.addWidget(self.hint)

    def refresh(self) -> None:
        # 重建筛选下拉，尽量保留当前选择
        current = self.filter_combo.currentData()
        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        self.filter_combo.addItem("全部", "")
        for f in self.config.get("folders", []):
            path = f.get("path", "")
            if path:
                self.filter_combo.addItem(os.path.basename(path.rstrip("\\/")) or path, path)
        self.filter_combo.blockSignals(False)
        if current:
            idx = self.filter_combo.findData(current)
            if idx >= 0:
                self.filter_combo.setCurrentIndex(idx)
        self._load()

    def _load(self) -> None:
        folder = self.filter_combo.currentData() or ""
        rows = self.state.recent(limit=2000)
        if folder:
            prefix = os.path.normcase(os.path.normpath(folder))
            rows = [
                r for r in rows
                if os.path.normcase(os.path.normpath(r[0] or "")).startswith(prefix)
            ]
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            path, title, bvid, part_count, status, created_at = row
            values = [
                os.path.basename(path or ""),
                title or "",
                bvid or "",
                str(part_count or ""),
                status or "",
                created_at or "",
            ]
            for j, v in enumerate(values):
                item = QTableWidgetItem(v)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(i, j, item)
        self.hint.setText(f"共 {len(rows)} 条记录" if rows else "暂无记录")
