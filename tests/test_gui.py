"""GUI 冒烟测试：离屏渲染，验证主窗口与各页面能正常构建。"""

import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
# 隔离真实数据，避免读到真实的登录凭据发起网络请求
os.environ["APPDATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def test_gui():
    app = QApplication.instance() or QApplication(sys.argv)

    w = MainWindow()
    assert w.windowTitle() == "B站视频自动上传"
    assert len(w.pages) == 4, f"应有 4 个页面，实际 {len(w.pages)}"

    # 切换每个页面并刷新
    for key in ("settings", "login", "history", "dashboard"):
        w.switch_page(key)
        assert w.stack.currentWidget() is w.pages[key]

    # 主题文件存在
    qss = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "app", "ui", "theme.qss")
    assert os.path.exists(qss)

    print("[OK] GUI 主窗口 + 4 页面 + 主题加载正常")
    w.close()


def test_folder_detail():
    app = QApplication.instance() or QApplication(sys.argv)

    from PySide6.QtWidgets import QMessageBox

    # 离屏模式下避免模态弹窗阻塞
    QMessageBox.information = staticmethod(lambda *a, **k: None)

    from app.core.config import Config
    from app.core.state import State
    from app.ui.folder_detail import FolderDetailPage

    cfg = Config(path=os.path.join(tempfile.mkdtemp(), "config.json"))
    state = State(db_path=os.path.join(tempfile.mkdtemp(), "h.db"))
    cfg.data["folders"] = [{"path": "C:/test", "enabled": True}]

    page = FolderDetailPage(cfg, state)
    page.set_folder("C:/test")
    assert page.schedule_edit is not None
    assert page.enabled_check.isChecked() is True

    page.enabled_check.setChecked(False)
    page.schedule_edit.setText("20:00")
    page.save()
    folder = cfg.data["folders"][0]
    assert folder["enabled"] is False
    assert folder["schedule_times"] == ["20:00"]
    print("[OK] 文件夹详情：扫描时间 + 启用开关")


if __name__ == "__main__":
    test_gui()
    test_folder_detail()
    print("\n全部测试通过")
