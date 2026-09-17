"""一次完整的「检查并上传」流程：扫描 → 命名 → 拆分 → 上传 → 记录 → 清理。

按文件夹独立处理：每个文件夹用「全局默认值 + 自身覆盖」的有效配置。
"""

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Callable

from . import auth, cleaner, naming, scanner, splitter, uploader
from .config import get_folder_effective_config

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str], None]


@dataclass
class _Submission:
    title: str
    parts: list[tuple[str, str]]  # [(路径, 分P标题)]
    source_files: list  # 组成该稿件的原始文件（scanner.VideoFile）


def _make_parts(files, config, threshold: int, temp_dir: str, emit: ProgressFn) -> list[tuple[str, str]]:
    """把一批文件转为分P列表；超大文件先拆分。"""
    parts: list[tuple[str, str]] = []
    part_index = 0
    for f in files:
        if f.size > threshold:
            emit(f"文件过大，拆分中：{os.path.basename(f.path)}")
            try:
                segs = splitter.split_by_size(f.path, threshold, os.path.join(temp_dir, "split"))
            except Exception as e:  # noqa: BLE001
                logger.warning("拆分失败，改为整文件上传：%s", e)
                segs = [f.path]
        else:
            segs = [f.path]
        for seg in segs:
            part_index += 1
            vars_ = naming.build_variables(f.path, index=1, part_index=part_index, count=len(files))
            part_title = naming.render_template(config["part_title_template"], **vars_)
            parts.append((seg, part_title))
    return parts


def _main_variables(files, config, index: int, count: int) -> dict:
    first = files[0].path if files else ""
    return naming.build_variables(first, index=index, count=count)


def _build_submissions(new_files, config, threshold: int, temp_dir: str, emit: ProgressFn) -> list[_Submission]:
    strategy = config.get("multi_file_strategy", "multipart")
    submissions: list[_Submission] = []

    if strategy == "separate":
        count = len(new_files)
        for i, f in enumerate(new_files, 1):
            parts = _make_parts([f], config, threshold, temp_dir, emit)
            vars_ = _main_variables([f], config, i, count)
            title = naming.render_template(config["title_template"], **vars_)
            submissions.append(_Submission(title, parts, [f]))
        return submissions

    if strategy == "merge":
        emit(f"物理合并 {len(new_files)} 个文件…")
        merged_path = os.path.join(temp_dir, "merged.mp4")
        try:
            splitter.merge_files([f.path for f in new_files], merged_path)
            st = os.stat(merged_path)
            merged = scanner.VideoFile(
                merged_path, st.st_size, st.st_mtime,
                os.path.dirname(merged_path),
                os.path.splitext(os.path.basename(merged_path))[0], ".mp4",
            )
            parts = _make_parts([merged], config, threshold, temp_dir, emit)
            vars_ = _main_variables(new_files, config, 1, 1)
            title = naming.render_template(config["title_template"], **vars_)
            submissions.append(_Submission(title, parts, new_files))
            return submissions
        except Exception as e:  # noqa: BLE001
            logger.warning("合并失败，回退为多分P：%s", e)
            emit("合并失败，已回退为多分P")

    # multipart（默认）
    parts = _make_parts(new_files, config, threshold, temp_dir, emit)
    vars_ = _main_variables(new_files, config, 1, 1)
    title = naming.render_template(config["title_template"], **vars_)
    submissions.append(_Submission(title, parts, new_files))
    return submissions


def _exclude_folders(config, folder_path: str) -> list[str]:
    exclude: list[str] = []
    af = config.get("archive_folder", "")
    if af:
        exclude.append(af)
    if config.get("cleanup_mode") == "archive":
        exclude.append(os.path.join(folder_path, "auto_archived"))
    return exclude


def _ensure_credential(emit: ProgressFn):
    """加载并校验/续期凭据。返回 (credential, 事件)。"""
    cred = auth.load_credential()
    if cred is None:
        return None, "no_login"
    emit("校验登录状态…")
    cred = asyncio.run(auth.ensure_valid_credential(cred))
    if cred is None:
        return None, "login_expired"
    return cred, "ok"


def _run_single_folder(effective_cfg: dict, folder_path: str, state, emit: ProgressFn, cred) -> dict:
    """处理单个文件夹：扫描→命名→拆分→上传→记录→清理。"""
    exts = effective_cfg.get("video_extensions", [])
    exclude = _exclude_folders(effective_cfg, folder_path)
    new_files = scanner.scan_new_files([folder_path], exts, state, exclude_folders=exclude)

    name = os.path.basename(folder_path) or folder_path
    if not new_files:
        return {"event": "no_new_files", "count": 0}

    emit(f"[{name}] 发现 {len(new_files)} 个新文件，开始处理…")

    threshold = int(float(effective_cfg.get("split_threshold_gb", 3.5)) * 1024 ** 3)
    temp_dir = tempfile.mkdtemp(prefix="bili_run_")
    try:
        submissions = _build_submissions(new_files, effective_cfg, threshold, temp_dir, emit)
    except Exception as e:  # noqa: BLE001
        logger.exception("构建上传任务失败")
        return {"event": "failed", "count": 0, "message": f"[{name}] 处理失败：{e}"}

    cleanup_mode = effective_cfg.get("cleanup_mode", "archive")
    archive_folder = effective_cfg.get("archive_folder", "")
    uploads_done = []
    failed_count = 0

    for sub in submissions:
        emit(f"上传中：{sub.title}（{len(sub.parts)} 个分P）…")
        vars_ = naming.build_variables(
            sub.source_files[0].path if sub.source_files else "",
            index=1, count=len(sub.source_files),
        )
        desc = naming.render_template(effective_cfg.get("desc_template", ""), **vars_)
        try:
            result = uploader.upload_videos(
                parts=sub.parts,
                credential=cred,
                title=sub.title,
                desc=desc,
                tags=effective_cfg.get("tags", []),
                cover_path=effective_cfg.get("cover_path", ""),
                tid=int(effective_cfg.get("tid", 160)),
                copyright=int(effective_cfg.get("copyright", 1)),
                source=effective_cfg.get("source", ""),
                publish_mode=effective_cfg.get("publish_mode", "timed"),
                publish_delay_hours=float(effective_cfg.get("publish_delay_hours", 2.0)),
                publish_schedule_time=effective_cfg.get("publish_schedule_time", "20:00"),
                temp_dir=temp_dir,
            )
            bvid = result.get("bvid", "")
            emit(f"上传成功：{sub.title}（BV: {bvid}）")

            for f in sub.source_files:
                state.add(f.path, f.size, f.mtime, sub.title, bvid, len(sub.parts))
                action = cleaner.clean_up(
                    f.path, cleanup_mode,
                    archive_folder=archive_folder, watch_folder=folder_path,
                )
                emit(f"{action}：{os.path.basename(f.path)}")
            uploads_done.append({"title": sub.title, "bvid": bvid, "parts": len(sub.parts)})
        except Exception as e:  # noqa: BLE001
            failed_count += 1
            logger.exception("上传失败：%s", sub.title)
            emit(f"上传失败：{sub.title}（{e}）")

    if not uploads_done:
        return {"event": "failed", "count": 0, "message": f"[{name}] 未能成功上传任何视频。"}

    n = sum(u["parts"] for u in uploads_done)
    if failed_count > 0:
        return {
            "event": "partial", "count": len(uploads_done), "uploads": uploads_done,
            "message": f"[{name}] 上传 {len(uploads_done)} 个稿件，{failed_count} 个失败。",
        }
    return {
        "event": "success", "count": len(uploads_done), "uploads": uploads_done,
        "message": f"[{name}] 上传 {len(uploads_done)} 个稿件，共 {n} 个分P。",
    }


def _find_folder(config: dict, folder_path: str) -> dict:
    for f in config.get("folders", []):
        if isinstance(f, dict) and f.get("path") == folder_path:
            return f
    return {"path": folder_path}


def run_folder(config: dict, folder_path: str, state, on_progress: ProgressFn | None = None) -> dict:
    """上传单个文件夹（详情页「立即上传此文件夹」）。"""
    def emit(msg: str) -> None:
        logger.info(msg)
        if on_progress:
            on_progress(msg)

    cred, event = _ensure_credential(emit)
    if cred is None:
        if event == "no_login":
            return {"ok": False, "event": "no_login", "message": "未登录，请先在「登录」页扫码或填写 Cookie。"}
        return {"ok": False, "event": "login_expired", "message": "登录已过期，请重新登录。"}

    folder = _find_folder(config, folder_path)
    effective = get_folder_effective_config(config, folder)
    result = _run_single_folder(effective, folder_path, state, emit, cred)
    result["ok"] = result["event"] in ("success", "partial", "no_new_files")
    if "message" not in result:
        result["message"] = "没有发现新的视频文件。" if result["event"] == "no_new_files" else ""
    return result


def run_once(config: dict, state, on_progress: ProgressFn | None = None) -> dict:
    """遍历所有文件夹逐个上传（全局定时 / 「立即上传全部」）。"""
    def emit(msg: str) -> None:
        logger.info(msg)
        if on_progress:
            on_progress(msg)

    folders = [f for f in config.get("folders", []) if isinstance(f, dict) and f.get("path")]
    if not folders:
        return {"ok": False, "event": "no_folder", "message": "未添加任何文件夹，请在仪表盘添加。"}

    cred, event = _ensure_credential(emit)
    if cred is None:
        if event == "no_login":
            return {"ok": False, "event": "no_login", "message": "未登录，请先在「登录」页扫码或填写 Cookie。"}
        return {"ok": False, "event": "login_expired", "message": "登录已过期，请重新登录。"}

    total = 0
    events = []
    for folder in folders:
        path = folder.get("path", "")
        if not os.path.isdir(path):
            emit(f"文件夹不存在，跳过：{path}")
            continue
        effective = get_folder_effective_config(config, folder)
        r = _run_single_folder(effective, path, state, emit, cred)
        events.append(r.get("event"))
        total += r.get("count", 0)

    if not events:
        return {"ok": False, "event": "no_folder", "message": "没有可用的文件夹。"}
    if "success" in events or "partial" in events:
        if any(e in ("failed", "partial") for e in events):
            return {"ok": True, "event": "partial", "message": f"完成：共上传 {total} 个稿件（部分失败）。"}
        return {"ok": True, "event": "success", "message": f"完成：共上传 {total} 个稿件。"}
    if any(e == "no_new_files" for e in events):
        return {"ok": True, "event": "no_new_files", "message": "所有文件夹都没有新视频。"}
    return {"ok": False, "event": "failed", "message": "本次未能成功上传任何视频，详见日志。"}
