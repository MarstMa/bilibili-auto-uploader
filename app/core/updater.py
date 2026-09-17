"""检查更新：查询 GitHub Releases 最新版本。"""

import logging
import os
import sys

from curl_cffi import requests as cffi
from curl_cffi.requests import AsyncSession

from .version import GITHUB_REPO, VERSION

logger = logging.getLogger(__name__)

_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def compare_versions(a: str, b: str) -> int:
    """比较版本号。a>b 返回 1，a<b 返回 -1，相等返回 0。"""
    def parse(v: str) -> list[int]:
        try:
            return [int(x) for x in str(v).lstrip("v").split(".")]
        except (ValueError, AttributeError):
            return [0, 0, 0]

    pa, pb = parse(a), parse(b)
    for x, y in zip(pa, pb):
        if x != y:
            return 1 if x > y else -1
    return 0


async def check_latest() -> dict:
    """查询最新发布版本。

    返回 {"latest", "tag", "url", "asset_url", "has_update"}。
    查询失败或尚无 release 时 has_update 为 False。
    """
    try:
        async with AsyncSession(impersonate="chrome") as s:
            r = await s.get(_API_URL, headers={"Accept": "application/vnd.github+json"})
            data = r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("检查更新失败：%s", e)
        return {"latest": VERSION, "tag": "v" + VERSION, "url": "", "asset_url": "", "has_update": False}

    tag = str(data.get("tag_name", "") or "")
    latest = tag.lstrip("v")
    url = str(data.get("html_url", "") or "")
    asset_url = ""
    for a in data.get("assets", []) or []:
        if str(a.get("name", "")).lower().endswith(".exe"):
            asset_url = str(a.get("browser_download_url", "") or "")
            break
    has_update = compare_versions(latest, VERSION) > 0
    return {"latest": latest, "tag": tag, "url": url, "asset_url": asset_url, "has_update": has_update}


def download_latest(asset_url: str, dest_path: str, on_progress=None) -> bool:
    """流式下载 release 资产到 dest_path（阻塞式，应在后台线程调用）。

    on_progress(done_bytes, total_bytes) 可选进度回调。
    """
    try:
        r = cffi.get(asset_url, stream=True, impersonate="chrome")
        try:
            total = int(r.headers.get("Content-Length", 0) or 0)
            done = 0
            dest_dir = os.path.dirname(dest_path)
            if dest_dir:
                os.makedirs(dest_dir, exist_ok=True)
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
                        done += len(chunk)
                        if on_progress:
                            on_progress(done, total)
        finally:
            r.close()
        return os.path.isfile(dest_path) and os.path.getsize(dest_path) > 0
    except Exception as e:  # noqa: BLE001
        logger.warning("下载更新失败：%s", e)
        return False


def apply_update(new_exe_path: str) -> None:
    """写并运行 update.bat，退出程序后由脚本完成「替换旧 exe + 重启」。"""
    exe_path = sys.executable
    exe_dir = os.path.dirname(exe_path)
    bat_path = os.path.join(exe_dir, "update.bat")
    new_name = os.path.basename(new_exe_path)
    exe_name = os.path.basename(exe_path)

    bat = (
        "@echo off\n"
        ":retry\n"
        "timeout /t 2 /nobreak >nul\n"
        f'move /y "%~dp0{new_name}" "%~dp0{exe_name}" >nul 2>&1\n'
        f'if exist "%~dp0{new_name}" goto retry\n'
        f'start "" "%~dp0{exe_name}"\n'
        'del "%~f0"\n'
    )
    with open(bat_path, "w", encoding="ascii") as f:
        f.write(bat)
    os.startfile(bat_path)
