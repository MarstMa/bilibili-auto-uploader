"""登录：扫码 / Cookie，凭据持久化与登录态校验。"""

import asyncio
import base64
import json
import logging
import os

import qrcode
from bilibili_api.login_v2 import QrCodeLoginEvents
from bilibili_api.utils.network import Credential
from curl_cffi.requests import AsyncSession

logger = logging.getLogger(__name__)

_CRED_KEYS = ["sessdata", "bili_jct", "buvid3", "buvid4", "dedeuserid", "ac_time_value"]

# B 站扫码登录接口（B 站已改版：cookie 放在 Set-Cookie 响应头，而非 data.url）
_QR_GENERATE = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
_QR_POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"


# ---------- 凭据持久化（基础混淆，防明文泄露） ----------

def _credential_path() -> str:
    from .config import get_data_dir

    return os.path.join(get_data_dir(), "credential.json")


def _obfuscate(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii")


def _deobfuscate(s: str) -> str:
    return base64.urlsafe_b64decode(s.encode("ascii")).decode("utf-8")


def save_credential(cred: Credential, path: str | None = None) -> None:
    """把凭据保存到本地（字段做 base64 混淆）。"""
    path = path or _credential_path()
    data = {}
    for k in _CRED_KEYS:
        v = getattr(cred, k, None)
        data[k] = _obfuscate(v) if v else ""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    logger.info("已保存登录凭据")


def load_credential(path: str | None = None) -> Credential | None:
    """读取本地凭据；不存在或损坏返回 None。"""
    path = path or _credential_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        kwargs = {}
        for k in _CRED_KEYS:
            v = data.get(k, "")
            if v:
                kwargs[k] = _deobfuscate(v)
        if not kwargs.get("sessdata"):
            return None
        return Credential(**kwargs)
    except Exception as e:
        logger.warning("读取凭据失败：%s", e)
        return None


def clear_credential(path: str | None = None) -> None:
    """清除本地凭据（退出登录）。"""
    path = path or _credential_path()
    if os.path.exists(path):
        os.remove(path)
    logger.info("已清除登录凭据")


# ---------- 登录态 ----------

async def check_login(cred: Credential) -> bool:
    """校验凭据是否有效。"""
    if cred is None or not cred.has_sessdata():
        return False
    try:
        return bool(await cred.check_valid())
    except Exception as e:
        logger.warning("校验登录态失败：%s", e)
        return False


async def ensure_valid_credential(cred: Credential) -> Credential | None:
    """校验凭据；若已过期但可刷新，则自动续期并保存。

    返回有效的凭据，续期失败或无法续期时返回 None。
    """
    if cred is None or not cred.has_sessdata():
        return None
    if await check_login(cred):
        return cred
    # 已过期：尝试用 refresh_token 自动续期
    if cred.has_ac_time_value() and cred.has_bili_jct():
        try:
            await cred.refresh()
            if await check_login(cred):
                save_credential(cred)
                logger.info("登录凭据已自动续期")
                return cred
        except Exception as e:
            logger.warning("自动续期凭据失败：%s", e)
    return None


async def get_nickname(cred: Credential) -> str:
    """获取当前账号昵称（用于界面展示）。"""
    try:
        from bilibili_api.user import get_self_info

        info = await get_self_info(cred)
        return str(info.get("name", ""))
    except Exception as e:
        logger.warning("获取昵称失败：%s", e)
        return ""


# ---------- Cookie 登录 ----------

def credential_from_cookie_text(text: str) -> Credential:
    """从浏览器 Cookie 文本解析 Credential。

    支持两种格式：
    1. "SESSDATA=xxx; bili_jct=yyy; ..."（分号分隔的键值对）
    2. 仅粘贴 SESSDATA 值本身
    """
    text = text.strip()
    cookies: dict[str, str] = {}
    if "=" in text:
        for part in text.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                cookies[k.strip()] = v.strip()
    else:
        cookies["SESSDATA"] = text

    norm = {k.lower(): v for k, v in cookies.items()}
    return Credential(
        sessdata=norm.get("sessdata"),
        bili_jct=norm.get("bili_jct"),
        buvid3=norm.get("buvid3"),
        buvid4=norm.get("buvid4"),
        dedeuserid=norm.get("dedeuserid"),
        ac_time_value=norm.get("ac_time_value"),
    )


# ---------- 扫码登录 ----------

class QrLoginSession:
    """一次扫码登录会话（自实现，适配 B 站新接口）。"""

    def __init__(self) -> None:
        self._session = AsyncSession(impersonate="chrome")
        self._qrcode_key = ""
        self._credential: Credential | None = None

    async def generate(self, qr_path: str) -> None:
        """生成二维码并保存为图片文件。"""
        resp = await self._session.get(_QR_GENERATE)
        data = resp.json()["data"]
        self._qrcode_key = data["qrcode_key"]
        qrcode.make(data["url"]).save(qr_path)

    async def poll(self) -> QrCodeLoginEvents:
        """轮询一次登录状态。"""
        resp = await self._session.get(
            _QR_POLL, params={"qrcode_key": self._qrcode_key}
        )
        data = resp.json().get("data") or {}
        code = data.get("code", 0)
        if code == 86101:
            return QrCodeLoginEvents.SCAN
        if code == 86090:
            return QrCodeLoginEvents.CONF
        if code == 86038:
            return QrCodeLoginEvents.TIMEOUT
        # 登录成功：从 Set-Cookie 提取 cookie
        self._credential = self._build_credential(resp, data)
        return QrCodeLoginEvents.DONE

    def _build_credential(self, resp, data: dict) -> Credential:
        """从响应头 Set-Cookie 与 data.refresh_token 构造凭据。"""
        cookies: dict[str, str] = {}
        try:
            for k, v in resp.cookies.items():
                cookies[k] = v
        except Exception:  # noqa: BLE001
            pass
        set_cookie = resp.headers.get("Set-Cookie") or resp.headers.get("set-cookie") or ""
        for part in set_cookie.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                cookies.setdefault(k, v)
        return Credential(
            sessdata=cookies.get("SESSDATA") or cookies.get("sessdata"),
            bili_jct=cookies.get("bili_jct"),
            buvid3=cookies.get("buvid3"),
            buvid4=cookies.get("buvid4"),
            dedeuserid=cookies.get("DedeUserID") or cookies.get("dedeuserid"),
            ac_time_value=data.get("refresh_token", ""),
        )

    async def close(self) -> None:
        await self._session.close()

    def is_done(self) -> bool:
        return self._credential is not None

    def credential(self) -> Credential:
        return self._credential


async def run_qr_login(
    qr_path: str,
    on_event=None,
    poll_interval: float = 2.0,
) -> Credential | None:
    """完整扫码登录流程：生成二维码并轮询，直到登录成功或二维码过期。

    on_event: 可选回调，收到 QrCodeLoginEvents（用于界面更新状态）。
    返回成功后的 Credential，超时返回 None。
    """
    session = QrLoginSession()
    await session.generate(qr_path)
    while True:
        event = await session.poll()
        if on_event is not None:
            on_event(event)
        if event == QrCodeLoginEvents.DONE:
            return session.credential()
        if event == QrCodeLoginEvents.TIMEOUT:
            return None
        await asyncio.sleep(poll_interval)
