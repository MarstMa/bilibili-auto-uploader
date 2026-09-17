"""后台异步任务封装：把阻塞/异步工作放到 QThread，避免卡住界面。"""

import asyncio

from PySide6.QtCore import QThread, Signal


class AsyncTask(QThread):
    """在后台线程运行一个「返回协程的可调用对象」，完成后发信号。

    用法：
        task = AsyncTask(lambda: some_async_func(...))
        task.done.connect(on_ok)
        task.error.connect(on_err)
        task.start()
    """

    done = Signal(object)  # 成功结果
    error = Signal(str)  # 异常信息

    def __init__(self, coro_factory, parent=None):
        super().__init__(parent)
        self._coro_factory = coro_factory

    def run(self) -> None:
        try:
            result = asyncio.run(self._coro_factory())
            self.done.emit(result)
        except Exception as e:  # noqa: BLE001 —— 后台线程需兜底所有异常
            self.error.emit(str(e))


class RunWorker(QThread):
    """在后台线程运行一个「带进度回调的同步函数」。

    run_func 接收一个 emit_progress(str) 回调，返回结果字典。
    """

    progress = Signal(str)
    finished_result = Signal(dict)

    def __init__(self, run_func, parent=None):
        super().__init__(parent)
        self._run_func = run_func

    def run(self) -> None:
        try:
            result = self._run_func(self.progress.emit)
            self.finished_result.emit(result)
        except Exception as e:  # noqa: BLE001
            self.finished_result.emit({"ok": False, "message": f"运行出错：{e}"})
