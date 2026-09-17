"""定时任务调度（APScheduler），每天若干时刻触发回调。"""

import logging
from datetime import datetime
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class DailyScheduler:
    """按每天若干时刻触发回调的后台调度器。"""

    def __init__(self) -> None:
        # timezone 默认本地时区，CronTrigger(hour, minute) 按本地时间触发
        self._scheduler = BackgroundScheduler()
        self._jobs: list = []

    @staticmethod
    def _parse_time(s: str) -> tuple[int | None, int | None]:
        """解析 "HH:MM"，非法返回 (None, None)。"""
        try:
            h, m = s.strip().split(":")
            h, m = int(h), int(m)
            if 0 <= h <= 23 and 0 <= m <= 59:
                return h, m
        except (ValueError, AttributeError):
            pass
        return None, None

    def set_folder_schedules(self, folder_schedules, callback) -> None:
        """按文件夹设置定时任务。

        folder_schedules: [(folder_path, [times]), ...]；callback(folder_path) 在到点时调用。
        """
        for job in self._jobs:
            try:
                self._scheduler.remove_job(job.id)
            except Exception:
                pass
        self._jobs = []

        idx = 0
        for folder_path, times in folder_schedules:
            for t in times or []:
                h, m = self._parse_time(t)
                if h is None:
                    logger.warning("忽略非法时间：%s", t)
                    continue
                job = self._scheduler.add_job(
                    callback,
                    CronTrigger(hour=h, minute=m),
                    args=[folder_path],
                    id=f"folder_{idx}_{h:02d}{m:02d}",
                    replace_existing=True,
                    max_instances=1,  # 上一次没跑完不重复触发
                    coalesce=True,
                )
                self._jobs.append(job)
                idx += 1
        logger.info("已设置 %d 个文件夹定时任务", len(self._jobs))

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("定时调度器已启动")

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("定时调度器已停止")

    def next_run_time(self) -> datetime | None:
        """下一次触发时间（调度器未启动时用 trigger 手动计算）。"""
        now = datetime.now(self._scheduler.timezone)
        times = []
        for job in self._scheduler.get_jobs():
            nt = getattr(job, "next_run_time", None)
            if nt is None and job.trigger is not None:
                nt = job.trigger.get_next_fire_time(None, now)
            if nt is not None:
                times.append(nt)
        return min(times) if times else None

    def is_running(self) -> bool:
        return self._scheduler.running
