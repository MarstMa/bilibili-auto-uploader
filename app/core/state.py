"""上传历史记录（SQLite），用于差异去重。"""

import logging
import os
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)


class State:
    """记录已上传文件的历史，去重依据 path + size + mtime。"""

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            from .config import get_data_dir

            db_path = os.path.join(get_data_dir(), "history.db")
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL,
                    size INTEGER,
                    mtime REAL,
                    title TEXT,
                    bvid TEXT,
                    part_count INTEGER,
                    status TEXT,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_uploads_path ON uploads(path)"
            )

    def is_uploaded(self, path: str, size: int, mtime: float) -> bool:
        """文件是否已成功上传过。"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM uploads WHERE path=? AND size=? AND mtime=?",
                (path, size, mtime),
            ).fetchone()
        return row is not None

    def add(
        self,
        path: str,
        size: int,
        mtime: float,
        title: str,
        bvid: str,
        part_count: int = 1,
        status: str = "success",
    ) -> None:
        """记录一次成功（或失败）的上传。"""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO uploads
                    (path, size, mtime, title, bvid, part_count, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    path,
                    size,
                    mtime,
                    title,
                    bvid,
                    part_count,
                    status,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def recent(self, limit: int = 100) -> list[tuple]:
        """最近的上传记录（用于历史页展示）。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT path, title, bvid, part_count, status, created_at "
                "FROM uploads ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return rows
