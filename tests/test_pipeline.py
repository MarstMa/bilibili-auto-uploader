"""pipeline / config 纯逻辑自测（不联网、不真实上传）。"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import pipeline
from app.core.config import Config, get_folder_effective_config
from app.core.scanner import VideoFile


def _fake_videofile(path: str, size: int = 100) -> VideoFile:
    with open(path, "wb") as f:
        f.write(b"0" * size)
    st = os.stat(path)
    return VideoFile(
        path, st.st_size, st.st_mtime, os.path.dirname(path),
        os.path.splitext(os.path.basename(path))[0], ".mp4",
    )


def test_guards():
    # 无文件夹
    r = pipeline.run_once({"folders": []}, None)
    assert r["ok"] is False and r["event"] == "no_folder"

    # 未登录
    orig = pipeline.auth.load_credential
    pipeline.auth.load_credential = lambda: None
    try:
        tmp = tempfile.mkdtemp()
        r2 = pipeline.run_once({"folders": [{"path": tmp}]}, None)
        assert r2["ok"] is False and r2["event"] == "no_login"
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

    cfg = dict(base_cfg, multi_file_strategy="multipart")
    subs = pipeline._build_submissions(files, cfg, threshold, tmp, emit)
    assert len(subs) == 1 and len(subs[0].parts) == 2
    assert subs[0].parts[0][1] == "P1 甲"
    assert subs[0].parts[1][1] == "P2 乙"

    cfg2 = dict(base_cfg, multi_file_strategy="separate")
    subs2 = pipeline._build_submissions(files, cfg2, threshold, tmp, emit)
    assert len(subs2) == 2
    assert subs2[0].parts[0][1] == "P1 甲"
    assert subs2[1].parts[0][1] == "P1 乙"
    print("[OK] 投稿任务构建：multipart / separate")


def test_exclude_and_effective():
    watch = r"C:\vids"
    cfg = {"cleanup_mode": "archive", "archive_folder": r"D:\archive"}
    ex = pipeline._exclude_folders(cfg, watch)
    assert r"D:\archive" in ex
    assert os.path.join(watch, "auto_archived") in ex

    base = {"title_template": "全局", "tags": [], "tid": 160, "schedule_times": ["08:00"]}
    folder = {"path": watch, "title_template": "覆盖标题", "tags": ["a"]}
    eff = get_folder_effective_config(base, folder)
    assert eff["title_template"] == "覆盖标题"
    assert eff["tags"] == ["a"]
    assert eff["tid"] == 160  # 未覆盖 → 继承全局
    assert eff["schedule_times"] == ["08:00"]  # 全局项保留
    print("[OK] 归档排除 + 有效配置合并")


def test_config_migration():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"watch_folders": ["D:/a", "D:/b"]}, f)
    cfg = Config(path=path)
    assert cfg.data["folders"] == [{"path": "D:/a"}, {"path": "D:/b"}]
    assert "watch_folders" not in cfg.data
    print("[OK] 旧配置迁移 watch_folders -> folders")


if __name__ == "__main__":
    test_guards()
    test_build_submissions()
    test_exclude_and_effective()
    test_config_migration()
    print("\n全部测试通过")
