"""封装 bilibili-api 上传，提供同步入口 upload_videos。"""

import asyncio
import logging
import os
import tempfile
import time
from datetime import datetime, timedelta
from typing import Optional

from bilibili_api.utils.network import Credential
from bilibili_api.video_uploader import VideoMeta, VideoUploader, VideoUploaderPage

from . import splitter

logger = logging.getLogger(__name__)

# 定时发布至少提前这么多小时，避免时间过近被 B 站拒绝
_MIN_DELAY_HOURS = 0.1


def _compute_delay_time(
    publish_mode: str,
    publish_delay_hours: float,
    publish_schedule_time: str = "",
) -> Optional[int]:
    """返回定时发布的时间戳（秒）；直接发布返回 None。

    publish_mode: public=直接发布 / timed=延迟 N 小时 / schedule=定时到指定时刻
    """
    if publish_mode == "timed":
        hours = max(float(publish_delay_hours), _MIN_DELAY_HOURS)
        return int(time.time() + hours * 3600)
    if publish_mode == "schedule":
        return _next_schedule_timestamp(publish_schedule_time)
    return None


def _next_schedule_timestamp(hhmm: str) -> int:
    """计算下一个 HH:MM 时刻的时间戳（今天已过则取明天）。"""
    hour, minute = 20, 0
    try:
        hour, minute = (int(x) for x in str(hhmm).strip().split(":"))
    except (ValueError, AttributeError):
        pass
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return int(target.timestamp())


def _make_cover(cover_path: str, first_video: str, temp_dir: str) -> str:
    """确定封面文件：优先用户指定，其次从首帧抽帧，最后用 Pillow 生成占位图。"""
    if cover_path and os.path.isfile(cover_path):
        return cover_path

    os.makedirs(temp_dir, exist_ok=True)

    if first_video and os.path.isfile(first_video):
        frame_path = os.path.join(temp_dir, "cover_frame.jpg")
        if splitter.extract_frame(first_video, frame_path, 1.0):
            return frame_path

    placeholder = os.path.join(temp_dir, "cover_placeholder.png")
    try:
        from PIL import Image

        img = Image.new("RGB", (1280, 720), (91, 155, 213))  # 淡蓝色占位图
        img.save(placeholder)
        return placeholder
    except Exception as e:
        logger.warning("生成占位封面失败：%s", e)
        return ""


async def _do_upload(pages: list, meta: VideoMeta, credential: Credential) -> dict:
    uploader = VideoUploader(pages, meta, credential)
    return await uploader.start()


def upload_videos(
    parts: list[tuple[str, str]],
    credential: Credential,
    *,
    title: str,
    desc: str = "",
    tags: list[str] | None = None,
    cover_path: str = "",
    tid: int = 160,
    copyright: int = 1,
    source: str = "",
    publish_mode: str = "timed",
    publish_delay_hours: float = 2.0,
    publish_schedule_time: str = "20:00",
    temp_dir: str = "",
) -> dict:
    """把多个视频上传为同一个稿件（多分P）。

    阻塞式同步接口，内部用 asyncio.run 执行，应在后台线程调用，避免卡 UI。

    Args:
        parts: [(视频路径, 分P标题), ...]
        title: 稿件标题
        publish_mode: "public" 直接发布 / "timed" 延迟发布 / "schedule" 定时到指定时刻
    返回: 含 bvid / aid 的字典。
    """
    if not parts:
        raise ValueError("没有要上传的视频")

    # 标签不能为空，最多 10 个
    tags = [str(t).strip() for t in (tags or []) if str(t).strip()]
    if not tags:
        tags = ["日常"]
    tags = tags[:10]

    temp_dir = temp_dir or tempfile.mkdtemp(prefix="bili_upload_")
    cover_file = _make_cover(cover_path, parts[0][0], temp_dir)
    delay = _compute_delay_time(publish_mode, publish_delay_hours, publish_schedule_time)

    meta = VideoMeta(
        tid=int(tid),
        title=title[:80],
        desc=(desc or "")[:2000],
        cover=cover_file,
        tags=tags,
        original=(int(copyright) == 1),
        source=source if int(copyright) != 1 else None,
        delay_time=delay,
    )

    pages = [VideoUploaderPage(path=p, title=t) for p, t in parts]

    logger.info(
        "开始上传：标题=%s，分P数=%d，模式=%s",
        title, len(pages), "定时发布" if publish_mode == "timed" else "直接发布",
    )
    result = asyncio.run(_do_upload(pages, meta, credential))
    logger.info("上传完成：bvid=%s，aid=%s", result.get("bvid"), result.get("aid"))
    return result
