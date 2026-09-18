"""标题 / 分P标题模板渲染。

支持变量：{date} {time} {index} {part_index} {original_name} {folder} {count}
"""

import os
from datetime import datetime, timedelta


class _SafeDict(dict):
    """未知占位符保持原样，避免 str.format 抛异常。"""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_template(template: str, **variables) -> str:
    """渲染模板。缺失的变量保持原样显示。"""
    if not template:
        return ""
    return template.format_map(_SafeDict(variables))


def build_variables(
    file_path: str,
    index: int = 1,
    part_index: int | None = None,
    count: int = 1,
    now: datetime | None = None,
    date_offset_days: int = 0,
) -> dict:
    """根据一个文件构造模板变量字典。"""
    now = now or datetime.now()
    date = now + timedelta(days=int(date_offset_days or 0))
    folder = os.path.basename(os.path.dirname(file_path)) or "默认"
    name, _ext = os.path.splitext(os.path.basename(file_path))
    return {
        "date": date.strftime("%Y-%m-%d"),
        "time": now.strftime("%H%M"),
        "index": index,
        "part_index": part_index if part_index is not None else index,
        "original_name": name,
        "folder": folder,
        "count": count,
    }
