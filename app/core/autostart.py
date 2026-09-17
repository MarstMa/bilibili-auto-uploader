"""开机自启动（写入注册表 HKEY_CURRENT_USER\\...\\Run，无需管理员权限）。"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

APP_NAME = "BiliAutoUpload"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command() -> str:
    """要注册的启动命令。打包后为 exe 路径，源码运行则为 python + main.py。"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    from .config import get_base_dir

    main_py = os.path.join(get_base_dir(), "main.py")
    return f'"{sys.executable}" "{main_py}"'


def enable() -> bool:
    """注册开机自启动。成功返回 True。"""
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command())
        winreg.CloseKey(key)
        logger.info("已注册开机自启动：%s", _command())
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("注册开机自启动失败：%s", e)
        return False


def disable() -> bool:
    """取消开机自启动。"""
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        logger.info("已取消开机自启动")
        return True
    except FileNotFoundError:
        return True  # 本来就没注册
    except Exception as e:  # noqa: BLE001
        logger.warning("取消开机自启动失败：%s", e)
        return False


def is_enabled() -> bool:
    """当前是否已注册开机自启动。"""
    try:
        import winreg

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except Exception:  # noqa: BLE001
        return False
