"""版本化 ExecutionPlan、progress ledger 与 approval 仓库。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable
from uuid import uuid4

from planner_orchestrator_agent.contracts import ExecutionPlan, ProgressEvent

from .database import Database
from .errors import StorageError


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Receipt:
    receipt_ref: str
    operation: str
    task_id: str
    resource_ref: str
    replayed: bool
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "receipt_ref": self.receipt_ref,
            "operation": self.operation,
            "task_id": self.task_id,
            "resource_ref": self.resource_ref,
            "created_at": self.created_at,
        }


class PlannerRepository:
    def __init__(self, database: Database, *, now: Callable[[], str] = _now, new_id: Callable[[str], str] | None = None) -> None:
        self.database = database
        self.now = now
        self.new_id = new_id or (lambda prefix: f"{prefix}-{uuid4()}")
        self.database.initialize()

    @staticmethod
    def _current(connection: sqlite3.Connection, table: str, column: str, task_id: str) -> int:
        row = connection.execute(f"SELECT MAX({column}) AS value FROM {table} WHERE task_id = ?", (task_id,)).fetchone()
        return int(row["value"] or 0)

    @staticmethod
    def _existing(connection: sqlite3.Connection, operation: str, task_id: str, key: str) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT receipt_id, request_hash, response_json FROM tool_receipts WHERE operation=? AND task_id=? AND idempotency_key=?",
            (operation, task_id, key),
        ).fetchone()

    @staticmethod
    def _check_key(key: str) -> None:
        if not key.strip() or len(key) > 200:
            raise StorageError("INVALID_IDEMPOTENCY_KEY", "idempotency key 长度必须为 1–200")

    def _begin_idempotent(self, connection: sqlite3.Connection, operation: str, task_id: str, key: str, request_hash: str) -> Receipt | None:
        existing = self._existing(connection, operation, task_id, key)
        if existing is None:
            return None
        if existing["request_hash"] != request_hash:
            raise StorageError("IDEMPOTENCY_CONFLICT", "相同 idempotency key 已用于不同 payload", details={"receipt_ref": f"receipt://{existing['receipt_id']}"})
        response = json.loads(existing["response_json"])
        return Receipt(**response, replayed=True)

    def _save_receipt(self, connection: sqlite3.Connection, operation: str, task_id: str, key: str, request_hash: str, resource_ref: str, timestamp: str) -> Receipt:
        receipt_id = self.new_id("receipt")
        response = {
            "receipt_ref": f"receipt://{receipt_id}", "operation": operation,
            "task_id": task_id, "resource_ref": resource_ref, "created_at": timestamp,
        }
        connection.execute(
            "INSERT INTO tool_receipts(receipt_id,operation,task_id,idempotency_key,request_hash,response_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (receipt_id, operation, task_id, key, request_hash, _canonical_json(response), timestamp),
        )
        return Receipt(**response, replayed=False)

    def write_plan(self, plan: ExecutionPlan, *, idempotency_key: str, expected_plan_version: int) -> Receipt:
        self._check_key(idempotency_key)
        plan = ExecutionPlan.model_validate(plan.model_dump(mode="json"))
        request = {"plan": plan.model_dump(mode="json"), "expected_plan_version": expected_plan_version}
        request_hash = _hash(request)
        operation = "write_execution_plan"
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._begin_idempotent(connection, operation, plan.task_id, idempotency_key, request_hash)
            if replay:
                connection.rollback()
                return replay
            current = self._current(connection, "execution_plans", "version", plan.task_id)
            if current != expected_plan_version:
                raise StorageError("PLAN_VERSION_CONFLICT", "当前计划版本与 expected version 不一致", details={"expected": expected_plan_version, "actual": current})
            if plan.version != current + 1:
                raise StorageError("INVALID_NEXT_PLAN_VERSION", "ExecutionPlan 必须追加连续版本", details={"required": current + 1})
            if current > 0:
                prior_row = connection.execute(
                    "SELECT payload_json FROM execution_plans WHERE task_id=? AND version=?",
                    (plan.task_id, current),
                ).fetchone()
                prior_plan = ExecutionPlan.model_validate_json(prior_row["payload_json"])
                successful_rows = connection.execute(
                    "SELECT payload_json FROM progress_events WHERE task_id=? ORDER BY sequence",
                    (plan.task_id,),
                ).fetchall()
                successful_ids = {
                    item.node_id
                    for row in successful_rows
                    if (item := ProgressEvent.model_validate_json(row["payload_json"])).event_type == "SUCCEEDED"
                    and item.node_id is not None
                }
                prior_nodes = {node.id: node for node in prior_plan.nodes}
                next_nodes = {node.id: node for node in plan.nodes}
                for node_id in successful_ids:
                    if node_id not in next_nodes:
                        raise StorageError(
                            "SUCCESSFUL_NODE_REMOVED",
                            f"partial replan 必须保留已成功节点 {node_id}",
                        )
                    if next_nodes[node_id].model_dump(mode="json") != prior_nodes[node_id].model_dump(mode="json"):
                        raise StorageError(
                            "SUCCESSFUL_NODE_MUTATED",
                            f"partial replan 不得修改已成功节点 {node_id}",
                        )
            required_previous = None if current == 0 else f"plan://{plan.task_id}/v{current}"
            if plan.previous_plan_ref != required_previous:
                plan = ExecutionPlan.model_validate(plan.model_copy(update={"previous_plan_ref": required_previous}).model_dump(mode="json"))
            timestamp = self.now()
            connection.execute(
                "INSERT INTO tasks(task_id,created_at,updated_at) VALUES(?,?,?) ON CONFLICT(task_id) DO UPDATE SET updated_at=excluded.updated_at",
                (plan.task_id, timestamp, timestamp),
            )
            payload_json = _canonical_json(plan.model_dump(mode="json"))
            connection.execute(
                "INSERT INTO execution_plans(task_id,version,payload_json,payload_hash,created_at) VALUES(?,?,?,?,?)",
                (plan.task_id, plan.version, payload_json, hashlib.sha256(payload_json.encode()).hexdigest(), timestamp),
            )
            receipt = self._save_receipt(connection, operation, plan.task_id, idempotency_key, request_hash, f"plan://{plan.task_id}/v{plan.version}", timestamp)
            connection.commit()
            return receipt
        except StorageError:
            connection.rollback()
            raise
        except sqlite3.OperationalError as error:
            connection.rollback()
            raise StorageError("DATABASE_BUSY", str(error), retryable=True) from error
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise StorageError("DATABASE_ERROR", str(error)) from error
        except Exception as error:
            connection.rollback()
            raise StorageError("INTERNAL_STORAGE_ERROR", "计划事务未完成") from error
        finally:
            connection.close()

    def append_event(self, event: ProgressEvent, *, idempotency_key: str) -> Receipt:
        self._check_key(idempotency_key)
        event = ProgressEvent.model_validate(event.model_dump(mode="json"))
        request = event.model_dump(mode="json")
        request_hash = _hash(request)
        operation = "update_progress_ledger"
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._begin_idempotent(connection, operation, event.task_id, idempotency_key, request_hash)
            if replay:
                connection.rollback()
                return replay
            plan_row = connection.execute(
                "SELECT payload_json FROM execution_plans WHERE task_id=? ORDER BY version DESC LIMIT 1",
                (event.task_id,),
            ).fetchone()
            if plan_row is None:
                raise StorageError("TASK_NOT_FOUND", "尚未保存 ExecutionPlan")
            plan = ExecutionPlan.model_validate_json(plan_row["payload_json"])
            node_map = {node.id: node for node in plan.nodes}
            if event.node_id is not None and event.node_id not in node_map:
                raise StorageError("UNKNOWN_NODE", f"进度事件引用了未知节点 {event.node_id}")
            rows = connection.execute(
                "SELECT payload_json FROM progress_events WHERE task_id=? ORDER BY sequence",
                (event.task_id,),
            ).fetchall()
            history = [ProgressEvent.model_validate_json(row["payload_json"]) for row in rows]
            used_tool_calls = sum(item.actual_usage.tool_calls for item in history) + event.actual_usage.tool_calls
            used_tokens = sum(item.actual_usage.tokens for item in history) + event.actual_usage.tokens
            used_cost = sum(item.actual_usage.cost_units for item in history) + event.actual_usage.cost_units
            if plan.budget.max_tool_calls is not None and used_tool_calls > plan.budget.max_tool_calls:
                raise StorageError("TOOL_BUDGET_REACHED", "实际 tool call 用量超过硬上限")
            if plan.budget.max_tokens is not None and used_tokens > plan.budget.max_tokens:
                raise StorageError("TOKEN_BUDGET_REACHED", "实际 token 用量超过硬上限")
            if plan.budget.max_cost is not None and used_cost > plan.budget.max_cost:
                raise StorageError("COST_BUDGET_REACHED", "实际 cost unit 用量超过硬上限")
            if plan.budget.deadline_ms is not None:
                task_row = connection.execute("SELECT created_at FROM tasks WHERE task_id=?", (event.task_id,)).fetchone()
                started_at = datetime.fromisoformat(task_row["created_at"])
                elapsed_ms = (datetime.fromisoformat(self.now()) - started_at).total_seconds() * 1000
                if elapsed_ms > plan.budget.deadline_ms:
                    raise StorageError("DEADLINE_REACHED", "任务已经超过硬 deadline")
            if event.event_type == "SUCCEEDED" and event.node_id is not None and any(
                item.node_id == event.node_id and item.event_type == "SUCCEEDED" for item in history
            ):
                raise StorageError("DUPLICATE_COMPLETION", "该节点已经成功，禁止用新幂等键重复完成")
            if event.event_type == "STARTED" and event.node_id is not None:
                failures = sum(item.node_id == event.node_id and item.event_type == "FAILED" for item in history)
                if failures > plan.retry_limits.max_same_agent_retries:
                    raise StorageError("RETRY_LIMIT_REACHED", "节点重试次数已用尽")
                if node_map[event.node_id].assigned_capability == "verifier":
                    cycles = sum(
                        item.node_id == event.node_id and item.event_type in {"SUCCEEDED", "FAILED"}
                        for item in history
                    )
                    if cycles >= plan.retry_limits.max_verifier_cycles:
                        raise StorageError("VERIFIER_CYCLE_LIMIT_REACHED", "Verifier cycle 已用尽")
                agent_hops = sum(item.event_type == "STARTED" and item.node_id is not None for item in history)
                if agent_hops >= plan.retry_limits.max_agent_hops:
                    raise StorageError("AGENT_HOP_LIMIT_REACHED", "Agent hop 预算已用尽")
            if event.event_type == "REPLAN_REQUESTED":
                replans = sum(item.event_type == "REPLAN_REQUESTED" for item in history)
                if replans >= plan.retry_limits.max_replans:
                    raise StorageError("REPLAN_LIMIT_REACHED", "Replan 次数已用尽")
            sequence = self._current(connection, "progress_events", "sequence", event.task_id) + 1
            event_id = self.new_id("event")
            timestamp = self.now()
            connection.execute(
                "INSERT INTO progress_events(event_id,task_id,sequence,payload_json,created_at) VALUES(?,?,?,?,?)",
                (event_id, event.task_id, sequence, _canonical_json(request), timestamp),
            )
            connection.execute("UPDATE tasks SET updated_at=? WHERE task_id=?", (timestamp, event.task_id))
            receipt = self._save_receipt(connection, operation, event.task_id, idempotency_key, request_hash, f"ledger://{event.task_id}/events/{sequence}", timestamp)
            connection.commit()
            return receipt
        except StorageError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise StorageError("DATABASE_ERROR", str(error)) from error
        finally:
            connection.close()

    def request_approval(self, task_id: str, payload: dict[str, Any], *, idempotency_key: str) -> Receipt:
        self._check_key(idempotency_key)
        request_hash = _hash(payload)
        operation = "request_human_approval"
        connection = self.database.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._begin_idempotent(connection, operation, task_id, idempotency_key, request_hash)
            if replay:
                connection.rollback()
                return replay
            if self._current(connection, "execution_plans", "version", task_id) == 0:
                raise StorageError("TASK_NOT_FOUND", "尚未保存 ExecutionPlan")
            approval_id = self.new_id("approval")
            timestamp = self.now()
            connection.execute(
                "INSERT INTO approval_requests(approval_id,task_id,status,payload_json,created_at) VALUES(?,?,?,?,?)",
                (approval_id, task_id, "PENDING", _canonical_json(payload), timestamp),
            )
            receipt = self._save_receipt(connection, operation, task_id, idempotency_key, request_hash, f"approval://{approval_id}", timestamp)
            connection.commit()
            return receipt
        except StorageError:
            connection.rollback()
            raise
        except sqlite3.DatabaseError as error:
            connection.rollback()
            raise StorageError("DATABASE_ERROR", str(error)) from error
        finally:
            connection.close()

    def read_state(self, task_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            plan = connection.execute("SELECT payload_json FROM execution_plans WHERE task_id=? ORDER BY version DESC LIMIT 1", (task_id,)).fetchone()
            if plan is None:
                raise StorageError("TASK_NOT_FOUND", f"未找到任务 {task_id}")
            events = connection.execute("SELECT sequence,payload_json FROM progress_events WHERE task_id=? ORDER BY sequence", (task_id,)).fetchall()
            approvals = connection.execute("SELECT approval_id,status,payload_json FROM approval_requests WHERE task_id=? ORDER BY created_at", (task_id,)).fetchall()
        return {
            "execution_plan": json.loads(plan["payload_json"]),
            "progress_ledger": [{"sequence": row["sequence"], "event": json.loads(row["payload_json"])} for row in events],
            "approval_requests": [{"approval_ref": f"approval://{row['approval_id']}", "status": row["status"], "payload": json.loads(row["payload_json"])} for row in approvals],
        }
