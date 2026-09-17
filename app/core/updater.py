"""检查更新：查询 GitHub Releases 最新版本。"""

import logging

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
