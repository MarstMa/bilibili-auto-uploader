"""pipeline 纯逻辑自测（不联网、不真实上传）。"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import pipeline
from app.core.scanner import VideoFile


def _fake_videofile(path: str, size: int = 100) -> VideoFile:
    with open(path, "wb") as f:
        f.write(b"0" * size)
    st = os.stat(path)
    return VideoFile(
        path, st.st_size, st.st_mtime, os.path.dirname(path),
        os.path.splitext(os.path.basename(path))[0], ".mp4",
    )


def test_guards(monkeypatch=None):
    # 未配置文件夹
    r = pipeline.run_once({"watch_folders": []}, None)
    assert r["ok"] is False and "监控文件夹" in r["message"]

    # 未登录
    orig = pipeline.auth.load_credential
    pipeline.auth.load_credential = lambda: None
    try:
        tmp = tempfile.mkdtemp()
        r2 = pipeline.run_once({"watch_folders": [tmp]}, None)
        assert r2["ok"] is False and "登录" in r2["message"]
    finally:
        pipeline.auth.load_credential = orig
    print("[OK] 守卫分支：无文件夹 / 未登录")


def test_build_submissions():
    tmp = tempfile.mkdtemp()
    f1 = _fake_videofile(os.path.join(tmp, "甲.mp4"))
    f2 = _fake_videofile(os.path.join(tmp, "乙.mp4"))
    files = [f1, f2]

    base_cfg = {
        "title_template": "{folder} {date} 第{index}期",
        "part_title_template": "P{part_index} {original_name}",
        "split_threshold_gb": 3.5,
    }
    threshold = int(3.5 * 1024 ** 3)

    def emit(_m):
        pass

    # multipart：一个稿件，两个分P
    cfg = dict(base_cfg, multi_file_strategy="multipart")
    subs = pipeline._build_submissions(files, cfg, threshold, tmp, emit)
    assert len(subs) == 1
    assert len(subs[0].parts) == 2
    assert "P1 甲" == subs[0].parts[0][1]
    assert "P2 乙" == subs[0].parts[1][1]

    # separate：两个独立稿件
    cfg2 = dict(base_cfg, multi_file_strategy="separate")
    subs2 = pipeline._build_submissions(files, cfg2, threshold, tmp, emit)
    assert len(subs2) == 2
    assert subs2[0].parts[0][1] == "P1 甲"
    assert subs2[1].parts[0][1] == "P1 乙"
    print("[OK] 投稿任务构建：multipart / separate")


def test_exclude_and_root():
    watch = os.path.normcase(r"C:\vids")
    assert pipeline._find_watch_root(r"C:\vids\a\b.mp4", [watch]) == watch

    cfg = {"cleanup_mode": "archive", "archive_folder": r"D:\archive"}
    ex = pipeline._exclude_folders(cfg, [watch])
    assert r"D:\archive" in ex
    assert os.path.join(watch, "auto_archived") in ex
    print("[OK] 归档目录排除 + 监控根定位")


if __name__ == "__main__":
    test_guards()
    test_build_submissions()
    test_exclude_and_root()
    print("\n全部测试通过")
