"""上传成功后的本地文件清理策略。"""

import logging
import os
import shutil

logger = logging.getLogger(__name__)


def _resolve_archive_folder(watch_folder: str, archive_folder: str) -> str:
    """归档目录。未配置时默认放在监控目录下的 auto_archived。"""
    if archive_folder:
        return archive_folder
    return os.path.join(watch_folder, "auto_archived")


def clean_up(
    file_path: str,
    mode: str,
    archive_folder: str = "",
    watch_folder: str = "",
) -> str:
    """按策略处理已上传的本地文件，返回动作描述文字。

    mode: archive=移动到归档文件夹 / delete=永久删除 / none=不处理
    """
    if mode == "none":
        return "不处理"

    if mode == "delete":
        try:
            os.remove(file_path)
            logger.info("已删除原文件：%s", file_path)
            return "已删除"
        except OSError as e:
            logger.error("删除文件失败 %s：%s", file_path, e)
            return "删除失败"

    if mode == "archive":
        target_dir = _resolve_archive_folder(watch_folder, archive_folder)
        os.makedirs(target_dir, exist_ok=True)
        dest = os.path.join(target_dir, os.path.basename(file_path))
        if os.path.exists(dest):
            base, ext = os.path.splitext(os.path.basename(file_path))
            i = 1
            while os.path.exists(os.path.join(target_dir, f"{base}_{i}{ext}")):
                i += 1
            dest = os.path.join(target_dir, f"{base}_{i}{ext}")
        try:
            shutil.move(file_path, dest)
            logger.info("已归档：%s -> %s", file_path, dest)
            return "已归档"
        except OSError as e:
            logger.error("归档失败 %s：%s", file_path, e)
            return "归档失败"

    logger.warning("未知清理模式：%s", mode)
    return "未知模式"
