"""一次完整的「检查并上传」流程：扫描 → 命名 → 拆分 → 上传 → 记录 → 清理。"""

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Callable

from . import auth, cleaner, naming, scanner, splitter, uploader

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str], None]


@dataclass
class _Submission:
    title: str
    parts: list[tuple[str, str]]  # [(路径, 分P标题)]
    source_files: list  # 组成该稿件的原始文件（scanner.VideoFile）


def _find_watch_root(file_path: str, watch_folders: list[str]) -> str:
    """找出文件所属的监控根目录（最长前缀匹配）。"""
    p = os.path.normcase(os.path.abspath(file_path))
    best = ""
    for wf in watch_folders:
        wp = os.path.normcase(os.path.abspath(wf))
        if (p == wp or p.startswith(wp + os.sep)) and len(wp) > len(best):
            best = wf
    return best


def _make_parts(files, config, threshold: int, temp_dir: str, emit: ProgressFn) -> list[tuple[str, str]]:
    """把一批文件转为分P列表；超大文件先拆分。"""
    parts: list[tuple[str, str]] = []
    part_index = 0
    for f in files:
        if f.size > threshold:
            emit(f"文件过大，拆分中：{os.path.basename(f.path)}")
            try:
                segs = splitter.split_by_size(
                    f.path, threshold, os.path.join(temp_dir, "split")
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("拆分失败，改为整文件上传：%s", e)
                segs = [f.path]
        else:
            segs = [f.path]
        for seg in segs:
            part_index += 1
            vars_ = naming.build_variables(
                f.path, index=1, part_index=part_index, count=len(files)
            )
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


def _exclude_folders(config, watch_folders: list[str]) -> list[str]:
    exclude: list[str] = []
    af = config.get("archive_folder", "")
    if af:
        exclude.append(af)
    if config.get("cleanup_mode") == "archive":
        for wf in watch_folders:
            exclude.append(os.path.join(wf, "auto_archived"))
    return exclude


def run_once(config, state, on_progress: ProgressFn | None = None) -> dict:
    """执行一次检查并上传。阻塞式，应在后台线程调用。

    返回 {"ok": bool, "message": str, "uploads": [...]}
    """
    def emit(msg: str) -> None:
        logger.info(msg)
        if on_progress:
            on_progress(msg)

    folders = [f for f in config.get("watch_folders", []) if f]
    if not folders:
        return {"ok": False, "event": "no_folder", "message": "未配置监控文件夹，请先在「设置」中添加。"}

    cred = auth.load_credential()
    if cred is None:
        return {"ok": False, "event": "no_login", "message": "未登录，请先在「登录」页扫码或填写 Cookie。"}

    emit("校验登录状态…")
    cred = asyncio.run(auth.ensure_valid_credential(cred))
    if cred is None:
        return {"ok": False, "event": "login_expired", "message": "登录已过期，请重新登录。"}

    exts = config.get("video_extensions", [])
    exclude = _exclude_folders(config, folders)
    new_files = scanner.scan_new_files(folders, exts, state, exclude_folders=exclude)

    if not new_files:
        return {"ok": True, "event": "no_new_files", "message": "没有发现新的视频文件。"}

    emit(f"发现 {len(new_files)} 个新文件，开始处理…")

    threshold = int(float(config.get("split_threshold_gb", 3.5)) * 1024 ** 3)
    temp_dir = tempfile.mkdtemp(prefix="bili_run_")
    try:
        submissions = _build_submissions(new_files, config, threshold, temp_dir, emit)
    except Exception as e:  # noqa: BLE001
        logger.exception("构建上传任务失败")
        return {"ok": False, "event": "failed", "message": f"处理失败：{e}"}

    cleanup_mode = config.get("cleanup_mode", "archive")
    archive_folder = config.get("archive_folder", "")
    uploads_done = []
    failed_count = 0

    for sub in submissions:
        emit(f"上传中：{sub.title}（{len(sub.parts)} 个分P）…")
        vars_ = naming.build_variables(
            sub.source_files[0].path if sub.source_files else "",
            index=1, count=len(sub.source_files),
        )
        desc = naming.render_template(config.get("desc_template", ""), **vars_)
        try:
            result = uploader.upload_videos(
                parts=sub.parts,
                credential=cred,
                title=sub.title,
                desc=desc,
                tags=config.get("tags", []),
                cover_path=config.get("cover_path", ""),
                tid=int(config.get("tid", 160)),
                copyright=int(config.get("copyright", 1)),
                source=config.get("source", ""),
                publish_mode=config.get("publish_mode", "timed"),
                publish_delay_hours=float(config.get("publish_delay_hours", 2.0)),
                publish_schedule_time=config.get("publish_schedule_time", "20:00"),
                temp_dir=temp_dir,
            )
            bvid = result.get("bvid", "")
            emit(f"上传成功：{sub.title}（BV: {bvid}）")

            # 记录历史 + 清理原始文件
            for f in sub.source_files:
                state.add(f.path, f.size, f.mtime, sub.title, bvid, len(sub.parts))
                watch_root = _find_watch_root(f.path, folders)
                action = cleaner.clean_up(
                    f.path, cleanup_mode,
                    archive_folder=archive_folder, watch_folder=watch_root,
                )
                emit(f"{action}：{os.path.basename(f.path)}")
            uploads_done.append({"title": sub.title, "bvid": bvid, "parts": len(sub.parts)})
        except Exception as e:  # noqa: BLE001
            failed_count += 1
            logger.exception("上传失败：%s", sub.title)
            emit(f"上传失败：{sub.title}（{e}）")

    if not uploads_done:
        return {"ok": False, "event": "failed", "message": "本次未能成功上传任何视频，详见日志。"}

    n = sum(u["parts"] for u in uploads_done)
    if failed_count > 0:
        return {
            "ok": True,
            "event": "partial",
            "message": f"完成：上传 {len(uploads_done)} 个稿件，{failed_count} 个失败。",
            "uploads": uploads_done,
        }
    return {
        "ok": True,
        "event": "success",
        "message": f"完成：上传 {len(uploads_done)} 个稿件，共 {n} 个分P。",
        "uploads": uploads_done,
    }
