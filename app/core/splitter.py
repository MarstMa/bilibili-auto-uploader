"""ffmpeg 拆分 / 合并（依赖 ffmpeg / ffprobe 可执行文件）。"""

import logging
import os
import shutil
import subprocess
import sys

logger = logging.getLogger(__name__)


def _find_tool(name: str) -> str | None:
    """查找 ffmpeg/ffprobe 可执行文件。优先级：环境变量 > 打包目录 > 系统 PATH。"""
    env_key = name.upper() + "_PATH"
    env_path = os.environ.get(env_key)
    if env_path and os.path.isfile(env_path):
        return env_path

    from .config import get_base_dir

    base = get_base_dir()
    for candidate in (
        os.path.join(base, "resources", "ffmpeg", "bin", name + ".exe"),
        os.path.join(base, "resources", "ffmpeg", name + ".exe"),
        os.path.join(base, name + ".exe"),
    ):
        if os.path.isfile(candidate):
            return candidate

    # PyInstaller 打包后，捆绑的二进制在 sys._MEIPASS 临时目录
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        for candidate in (
            os.path.join(meipass, "ffmpeg", name + ".exe"),
            os.path.join(meipass, name + ".exe"),
        ):
            if os.path.isfile(candidate):
                return candidate

    return shutil.which(name)


def probe_duration(path: str) -> float:
    """用 ffprobe 获取视频时长（秒）。失败返回 0.0。"""
    ffprobe = _find_tool("ffprobe")
    if not ffprobe:
        return 0.0
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return float(r.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired, OSError) as e:
        logger.warning("探测时长失败 %s：%s", path, e)
        return 0.0


def _run_ffmpeg(cmd: list[str]) -> bool:
    """运行 ffmpeg，成功返回 True。"""
    logger.debug("执行：%s", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        logger.error("ffmpeg 失败：%s\n%s", " ".join(cmd), r.stderr[-500:])
        return False
    return True


def extract_frame(video_path: str, output_path: str, time_sec: float = 1.0) -> bool:
    """从视频指定时间点抽取一帧作为封面。成功返回 True。"""
    ffmpeg = _find_tool("ffmpeg")
    if not ffmpeg:
        return False
    cmd = [
        ffmpeg, "-y",
        "-ss", f"{time_sec:.2f}",
        "-i", video_path,
        "-frames:v", "1", "-q:v", "2",
        output_path,
    ]
    return _run_ffmpeg(cmd)


def split_by_size(file_path: str, max_bytes: int, output_dir: str) -> list[str]:
    """把视频按大小拆成多段（流复制，按平均码率估算段时长）。

    返回段文件路径列表。无需拆分时返回 [file_path]。
    找不到 ffmpeg 且需要拆分时抛 RuntimeError。
    """
    size = os.path.getsize(file_path)
    if size <= max_bytes:
        return [file_path]

    ffmpeg = _find_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，无法拆分大文件。请在设置中指定 ffmpeg 路径。")

    duration = probe_duration(file_path)
    if duration <= 0:
        raise RuntimeError(f"无法读取视频时长，无法拆分：{file_path}")

    # 按平均码率估算每段时长，留 5% 余量
    seg_time = max(duration * max_bytes / size * 0.95, 1.0)

    os.makedirs(output_dir, exist_ok=True)
    base, _ext = os.path.splitext(os.path.basename(file_path))
    pattern = os.path.join(output_dir, base + "_%03d.mp4")

    cmd = [
        ffmpeg, "-y", "-i", file_path,
        "-c", "copy", "-f", "segment",
        "-segment_time", f"{seg_time:.2f}",
        "-reset_timestamps", "1",
        pattern,
    ]
    if not _run_ffmpeg(cmd):
        raise RuntimeError(f"拆分失败：{file_path}")

    segs = sorted(
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.startswith(base + "_") and f.endswith(".mp4")
    )
    if not segs:
        raise RuntimeError(f"拆分后未生成任何分段：{file_path}")
    logger.info("已拆分 %s 为 %d 段", file_path, len(segs))
    return segs


def merge_files(file_paths: list[str], output_path: str) -> str:
    """把多个视频物理合并成一个（流复制，要求各文件编码参数一致）。"""
    ffmpeg = _find_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，无法合并视频。")

    list_path = output_path + ".txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in file_paths:
            f.write("file '" + p.replace("'", "'\\''") + "'\n")

    cmd = [
        ffmpeg, "-y", "-f", "concat", "-safe", "0",
        "-i", list_path, "-c", "copy", output_path,
    ]
    ok = _run_ffmpeg(cmd)
    try:
        os.remove(list_path)
    except OSError:
        pass
    if not ok:
        raise RuntimeError(f"合并失败：{output_path}")
    logger.info("已合并 %d 个文件 -> %s", len(file_paths), output_path)
    return output_path
