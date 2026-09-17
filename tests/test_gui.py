"""GUI 冒烟测试：离屏渲染，验证主窗口与各页面能正常构建。"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
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


if __name__ == "__main__":
    test_gui()
    print("\n全部测试通过")
