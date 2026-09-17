"""auth 模块纯逻辑自测（不联网）。"""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bilibili_api.utils.network import Credential

from app.core import auth


def test_cookie_parsing():
    # 完整 Cookie 文本
    c = auth.credential_from_cookie_text(
        "SESSDATA=abc123; bili_jct=xyz789; DedeUserID=12345; buvid3=BUV3"
    )
    assert c.sessdata == "abc123"
    assert c.bili_jct == "xyz789"
    assert c.dedeuserid == "12345"
    assert c.buvid3 == "BUV3"

    # 仅 SESSDATA 值
    c2 = auth.credential_from_cookie_text("onlysessdata")
    assert c2.sessdata == "onlysessdata"
    assert c2.bili_jct is None
    print("[OK] Cookie 文本解析")


def test_credential_roundtrip():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "cred.json")
    cred = Credential(sessdata="sess_data", bili_jct="jct", dedeuserid="123")
    auth.save_credential(cred, path=path)
    assert os.path.exists(path)

    loaded = auth.load_credential(path=path)
    # Credential 构造时会对 sessdata 做 URL 编码归一化，故与保存时的值比较
    assert loaded.sessdata == cred.sessdata
    assert loaded.bili_jct == "jct"
    assert loaded.dedeuserid == "123"

    # 文件内容不应明文包含 sessdata 值
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    assert cred.sessdata not in raw

    auth.clear_credential(path=path)
    assert not os.path.exists(path)

    # 读取不存在的文件返回 None
    assert auth.load_credential(path=path) is None
    print("[OK] 凭据保存/读取/清除（含混淆）")


def test_check_login_no_network():
    # 无凭据 / 无 sessdata 时不联网，直接 False
    assert asyncio.run(auth.check_login(None)) is False
    assert asyncio.run(auth.check_login(Credential())) is False
    print("[OK] 登录态校验（空凭据）")


if __name__ == "__main__":
    test_cookie_parsing()
    test_credential_roundtrip()
    test_check_login_no_network()
    print("\n全部测试通过")
