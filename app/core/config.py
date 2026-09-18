"""配置读写：config.json 的加载、保存与默认值合并。"""

import json
import logging
import os
import shutil
import sys
from copy import deepcopy
from typing import Any

logger = logging.getLogger(__name__)

# 所有可配置项的默认值。新增字段后，旧配置文件加载时会自动补上默认值。
DEFAULT_CONFIG: dict[str, Any] = {
    "folders": [],  # 文件夹列表，每项 {"path": ..., 以及可覆盖的投稿设置}
    "video_extensions": [".mp4", ".flv", ".mkv", ".mov", ".avi", ".wmv", ".ts", ".m4v"],
    "schedule_times": ["08:00"],  # 每天运行的时刻 "HH:MM"
    "title_template": "{folder} {date} 第{index}期",
    "part_title_template": "P{part_index}",
    "date_offset_days": 0,  # 日期偏移（天），负数表示前几天，如 -1 表示昨天
    "desc_template": "",
    "tags": [],
    "cover_path": "",
    "tid": 21,  # 分区 ID（二级分区），21=生活·日常
    "copyright": 1,  # 1 原创 / 2 转载
    "source": "",  # 转载来源（copyright=2 时使用）
    "multi_file_strategy": "multipart",  # multipart / merge / separate
    "split_threshold_gb": 3.5,  # 单文件超过该大小则拆分
    "publish_mode": "timed",  # public 直接发布 / timed 延迟发布 / schedule 定时到指定时刻
    "publish_delay_hours": 2.0,  # 延迟发布模式下，上传后延迟公开的小时数
    "publish_schedule_time": "20:00",  # 定时发布模式下，发布的具体时刻 "HH:MM"
    "cleanup_mode": "archive",  # archive / delete / none
    "archive_folder": "",  # 归档目录，空=监控目录下的 auto_archived
    "auto_start": False,  # 开机自启
    "minimize_to_tray": True,  # 关闭窗口时最小化到托盘
    "start_minimized": False,  # 启动时最小化到托盘（不显示主窗口）
    "upload_workers": 3,  # 上传并发数
    "max_retry": 3,  # 失败重试次数
}

# 可被单个文件夹覆盖的设置项（投稿全套 + 扫描时间）
FOLDER_OVERRIDE_KEYS: list[str] = [
    "schedule_times",
    "title_template",
    "part_title_template",
    "date_offset_days",
    "desc_template",
    "tags",
    "cover_path",
    "tid",
    "copyright",
    "source",
    "multi_file_strategy",
    "split_threshold_gb",
    "publish_mode",
    "publish_delay_hours",
    "publish_schedule_time",
    "cleanup_mode",
    "archive_folder",
]


def get_folder_effective_config(config: dict, folder: dict) -> dict:
    """单个文件夹的有效配置 = 全局默认值 + 该文件夹的覆盖值。"""
    effective = dict(config)
    for key in FOLDER_OVERRIDE_KEYS:
        value = folder.get(key) if isinstance(folder, dict) else None
        if value is not None and value != "":
            effective[key] = value
    return effective


def get_base_dir() -> str:
    """程序根目录。开发环境为项目根，打包后为 exe 所在目录。"""
    if getattr(sys, "frozen", False):  # PyInstaller 打包后
        return os.path.dirname(sys.executable)
    # config.py 位于 app/core/ 下，向上三级到项目根
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_data_dir() -> str:
    """用户数据目录（config.json、history.db、credential.json 等）。

    放在 C 盘系统用户数据目录（%APPDATA%/BiliAutoUpload），不占用程序目录。
    """
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "BiliAutoUpload")
    os.makedirs(path, exist_ok=True)
    _migrate_old_data(path)
    return path


def _migrate_old_data(new_dir: str) -> None:
    """把旧版「程序目录/data」里的数据一次性迁移到新位置（不删除旧目录）。"""
    old_dir = os.path.join(get_base_dir(), "data")
    if not os.path.isdir(old_dir):
        return
    if os.path.normcase(os.path.abspath(old_dir)) == os.path.normcase(os.path.abspath(new_dir)):
        return
    for name in ("config.json", "history.db", "credential.json"):
        old = os.path.join(old_dir, name)
        new = os.path.join(new_dir, name)
        if os.path.isfile(old) and not os.path.exists(new):
            try:
                shutil.copy2(old, new)
                logger.info("已迁移数据文件：%s -> %s", old, new)
            except OSError as e:
                logger.warning("迁移数据文件失败 %s：%s", old, e)


class Config:
    """配置对象。data 为已与默认值合并的字典。"""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or os.path.join(get_data_dir(), "config.json")
        self.data: dict[str, Any] = deepcopy(DEFAULT_CONFIG)
        self.load()

    def load(self) -> None:
        """从磁盘读取，递归合并到默认值之上。文件缺失或损坏时保留默认值。"""
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self._merge(self.data, loaded)
            else:
                logger.warning("config.json 内容不是对象，忽略")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("读取配置失败，使用默认值：%s", e)
        self._migrate()

    def _migrate(self) -> None:
        """旧版本配置迁移。"""
        data = self.data
        # v0.1.x：watch_folders 是字符串列表 → 转成 folders 列表
        wf = data.get("watch_folders")
        if isinstance(wf, list):
            if not data.get("folders"):
                data["folders"] = [{"path": p} for p in wf if isinstance(p, str) and p]
            data.pop("watch_folders", None)

    @staticmethod
    def _merge(base: dict, override: dict) -> None:
        """把 override 合并进 base。仅覆盖 base 中已有的键，新增的默认字段得以保留。"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                Config._merge(base[key], value)
            else:
                base[key] = value

    def save(self) -> None:
        """把当前配置写入磁盘。"""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error("保存配置失败：%s", e)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
