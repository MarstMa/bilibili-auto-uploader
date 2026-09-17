"""核心模块（config/naming/scanner/state/cleaner）自测脚本。

用法：在项目根目录运行  python tests/test_core.py
"""

import os
import sys
import tempfile

# 保证能 import app.core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import Config
from app.core.state import State
from app.core.naming import render_template, build_variables
from app.core.scanner import scan_new_files
from app.core.cleaner import clean_up


def test_config():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "config.json")
    cfg = Config(path=path)
    assert cfg.get("publish_mode") == "timed"
    cfg.set("publish_mode", "public")
    cfg.save()
    cfg2 = Config(path=path)
    assert cfg2.get("publish_mode") == "public"
    print("[OK] config 读写与持久化")


def test_naming():
    vars_ = build_variables(r"D:\vids\我的视频.mp4", index=2, part_index=3, count=5)
    assert vars_["original_name"] == "我的视频"
    assert vars_["folder"] == "vids"
    assert vars_["index"] == 2
    assert vars_["part_index"] == 3

    title = render_template("{folder} {date} 第{index}期", **vars_)
    assert "vids" in title and "第2期" in title

    part = render_template("P{part_index} {original_name}", **vars_)
    assert part == "P3 我的视频"

    # 未知变量保持原样
    assert render_template("{未知}", **vars_) == "{未知}"
    print("[OK] naming 模板渲染")


def test_scanner_state_cleaner():
    tmp = tempfile.mkdtemp()
    watch = os.path.join(tmp, "watch")
    os.makedirs(watch)

    # 造 3 个假视频文件
    for i in (1, 2, 3):
        with open(os.path.join(watch, f"v{i}.mp4"), "wb") as f:
            f.write(b"0" * 100)

    state = State(db_path=os.path.join(tmp, "hist.db"))

    # 首次扫描应发现 3 个
    found = scan_new_files([watch], [".mp4"], state)
    assert len(found) == 3, f"应为 3 个，实际 {len(found)}"

    # 记录第一个已上传，再扫描应剩 2 个
    f0 = found[0]
    state.add(f0.path, f0.size, f0.mtime, "测试", "BVtest", 1)
    found2 = scan_new_files([watch], [".mp4"], state)
    assert len(found2) == 2, f"应为 2 个，实际 {len(found2)}"

    # 归档第一个文件 -> 移到 auto_archived，再扫描（不排除归档目录）会发现它被误扫
    res = clean_up(f0.path, "archive", watch_folder=watch)
    assert res == "已归档"
    archive_dir = os.path.join(watch, "auto_archived")
    assert os.path.exists(os.path.join(archive_dir, os.path.basename(f0.path)))

    # 不带排除：会扫到归档目录里的文件（旧行为，验证存在性）
    found3 = scan_new_files([watch], [".mp4"], state)
    assert len(found3) == 3, f"不排除归档目录时应为 3 个（含误扫归档），实际 {len(found3)}"

    # 带排除：跳过归档目录，只发现剩下的 2 个
    found4 = scan_new_files([watch], [".mp4"], state, exclude_folders=[archive_dir])
    assert len(found4) == 2, f"排除归档目录后应为 2 个，实际 {len(found4)}"

    # 删除模式
    f1 = found4[0]
    res = clean_up(f1.path, "delete")
    assert res == "已删除"
    assert not os.path.exists(f1.path)
    print("[OK] scanner/state/cleaner 扫描+去重+清理")


if __name__ == "__main__":
    test_config()
    test_naming()
    test_scanner_state_cleaner()
    print("\n全部测试通过")
