"""SQLite 初始化与连接。"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS tasks (
  task_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS execution_plans (
  task_id TEXT NOT NULL,
  version INTEGER NOT NULL CHECK(version > 0),
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(task_id, version),
  FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);
CREATE TABLE IF NOT EXISTS progress_events (
  event_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  sequence INTEGER NOT NULL CHECK(sequence > 0),
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(task_id, sequence),
  FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);
CREATE TABLE IF NOT EXISTS approval_requests (
  approval_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  status TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);
CREATE TABLE IF NOT EXISTS tool_receipts (
  receipt_id TEXT PRIMARY KEY,
  operation TEXT NOT NULL,
  task_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  response_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(operation, task_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_plan_latest ON execution_plans(task_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_event_latest ON progress_events(task_id, sequence DESC);
"""


class Database:
    def __init__(self, path: Path | str | None = None) -> None:
        if path is None:
            data_dir = Path(os.environ.get("PLANNER_ORCHESTRATOR_DATA_DIR", Path.home() / ".local" / "share" / "planner-orchestrator-agent"))
            path = data_dir / "state.sqlite3"
        self.path = Path(path).expanduser()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
