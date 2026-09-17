"""扫描监控文件夹，找出尚未上传的新视频文件（差异去重）。"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class VideoFile:
    """一个待上传的视频文件。"""

    path: str
    size: int
    mtime: float
    folder: str
    name: str  # 不含扩展名
    ext: str


def _normalize_extensions(extensions: list[str]) -> set[str]:
    """统一扩展名格式，如 '.mp4' 与 'mp4' 都归为 '.mp4'。"""
    result = set()
    for e in extensions:
        e = e.strip().lower()
        if not e:
            continue
        result.add(e if e.startswith(".") else "." + e)
    return result


def _is_under(path: str, folders: set[str]) -> bool:
    """path 是否等于或位于 folders 中某个目录之下。"""
    p = os.path.normcase(os.path.abspath(path))
    for f in folders:
        fp = os.path.normcase(os.path.abspath(f))
        if p == fp or p.startswith(fp + os.sep):
            return True
    return False


def scan_new_files(
    folders: list[str],
    extensions: list[str],
    state,
    exclude_folders: list[str] | None = None,
) -> list[VideoFile]:
    """扫描所有监控文件夹，返回未上传过的视频文件（按修改时间排序）。"""
    exts = _normalize_extensions(extensions)
    exclude = set(exclude_folders or [])
    result: list[VideoFile] = []

    for folder in folders:
        if not folder or not os.path.isdir(folder):
            logger.warning("监控文件夹不存在，跳过：%s", folder)
            continue
        for root, dirs, files in os.walk(folder):
            # 剪枝：不进入被排除的目录（如归档目录），避免重复扫描已归档文件
            dirs[:] = [
                d for d in dirs if not _is_under(os.path.join(root, d), exclude)
            ]
            if _is_under(root, exclude):
                continue
            for fname in files:
                name, ext = os.path.splitext(fname)
                if ext.lower() not in exts:
                    continue
                full = os.path.join(root, fname)
                try:
                    st = os.stat(full)
                except OSError as e:
                    logger.warning("无法读取文件，跳过 %s：%s", full, e)
                    continue
                if state.is_uploaded(full, st.st_size, st.st_mtime):
                    continue
                result.append(
                    VideoFile(full, st.st_size, st.st_mtime, root, name, ext.lower())
                )

    result.sort(key=lambda f: (f.mtime, f.path))
    return result
