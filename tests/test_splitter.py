"""splitter 模块集成自测（需本机有 ffmpeg/ffprobe）。"""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import splitter


def _gen_video(path: str, seconds: int = 6) -> None:
    """用 ffmpeg 生成一段测试视频（每秒一个关键帧，便于流复制拆分）。"""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440",
        "-t", str(seconds),
        "-c:v", "libx264", "-preset", "ultrafast", "-g", "30",
        "-c:a", "aac",
        path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def test_split_and_merge():
    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "src.mp4")
    _gen_video(src, 6)
    size = os.path.getsize(src)
    print("源视频大小:", size, "字节")

    # 强制拆成约 3 段
    max_bytes = size // 3
    segs = splitter.split_by_size(src, max_bytes, os.path.join(tmp, "parts"))
    print("拆分段数:", len(segs))
    assert len(segs) >= 2, f"应拆成多段，实际 {len(segs)} 段"
    for s in segs:
        assert os.path.exists(s)
        print("  ", os.path.basename(s), os.path.getsize(s), "字节")

    # 合并回一个
    merged = os.path.join(tmp, "merged.mp4")
    splitter.merge_files(segs, merged)
    assert os.path.exists(merged) and os.path.getsize(merged) > 0
    print("合并后大小:", os.path.getsize(merged), "字节")

    # 小文件无需拆分时直接返回原文件
    single = splitter.split_by_size(src, size + 1, os.path.join(tmp, "parts2"))
    assert single == [src]
    print("[OK] splitter 拆分 + 合并 + 免拆判断")


if __name__ == "__main__":
    test_split_and_merge()
    print("\n全部测试通过")
