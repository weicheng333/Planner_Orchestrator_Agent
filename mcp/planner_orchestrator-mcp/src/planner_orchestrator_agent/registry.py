"""最小静态 capability/tool registry。"""

CAPABILITY_REGISTRY = {
    "intake_spec": {"accepts": ["raw_request", "revision_request"], "returns": ["TaskSpec"]},
    "planner_orchestrator": {"accepts": ["TaskSpec", "failure_report"], "returns": ["ExecutionPlan", "handoff"]},
    "research": {"accepts": ["evidence_task"], "returns": ["evidence_refs"]},
    "executor": {"accepts": ["execution_node"], "returns": ["artifact_refs", "receipt_refs"]},
    "verifier": {"accepts": ["verification_node"], "returns": ["verification_report", "evidence_refs"]},
    "workflow": {"accepts": ["deterministic_node"], "returns": ["artifact_refs", "evidence_refs"]},
}

TOOL_REGISTRY = {
    "planner_orchestrator_mcp": {
        "scope": "planning_state_only",
        "tools": [
            "read_capability_registry", "read_tool_registry", "estimate_cost", "validate_dag",
            "read_task_state", "write_execution_plan", "update_progress_ledger", "request_human_approval",
        ],
        "denied_capabilities": ["shell", "git_write", "email", "payment", "business_database_write"],
    }
}
