"""ExecutionPlan 的确定性 DAG 与边界校验。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import ExecutionPlan


@dataclass(frozen=True)
class DagIssue:
    code: str
    message: str
    path: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "path": self.path}


def validate_execution_plan(plan: ExecutionPlan) -> list[DagIssue]:
    issues: list[DagIssue] = []
    nodes = {node.id: node for node in plan.nodes}
    criterion_map = {criterion.id: criterion for criterion in plan.acceptance_criteria}

    for node in plan.nodes:
        for dependency in node.dependencies:
            if dependency not in nodes:
                issues.append(DagIssue("UNKNOWN_DEPENDENCY", f"节点 {node.id} 引用了未知依赖 {dependency}", ["nodes", node.id, "dependencies"]))
            if dependency == node.id:
                issues.append(DagIssue("SELF_DEPENDENCY", f"节点 {node.id} 不能依赖自身", ["nodes", node.id]))
        for criterion_id in [*node.produces_acceptance_criteria, *node.checks_acceptance_criteria]:
            if criterion_id not in criterion_map:
                issues.append(DagIssue("UNKNOWN_ACCEPTANCE_CRITERION", f"节点 {node.id} 引用了未知验收标准 {criterion_id}", ["nodes", node.id]))

    colors: dict[str, int] = {node_id: 0 for node_id in nodes}

    def visit(node_id: str) -> None:
        if colors[node_id] == 1:
            issues.append(DagIssue("DAG_CYCLE", f"检测到包含 {node_id} 的环", ["nodes", node_id]))
            return
        if colors[node_id] == 2:
            return
        colors[node_id] = 1
        for dependency in nodes[node_id].dependencies:
            if dependency in nodes:
                visit(dependency)
        colors[node_id] = 2

    for node_id in nodes:
        visit(node_id)

    def depends_on(source: str, target: str, seen: set[str] | None = None) -> bool:
        seen = seen or set()
        if source in seen:
            return False
        seen.add(source)
        for dependency in nodes[source].dependencies:
            if dependency == target or (dependency in nodes and depends_on(dependency, target, seen)):
                return True
        return False

    grouped: dict[str, list[str]] = {}
    for node in plan.nodes:
        if node.parallel_group:
            grouped.setdefault(node.parallel_group, []).append(node.id)
    for group, members in grouped.items():
        for left in members:
            for right in members:
                if left != right and depends_on(left, right):
                    issues.append(DagIssue("INVALID_PARALLEL_DEPENDENCY", f"并行组 {group} 中的 {left} 依赖 {right}", ["nodes", left, "parallel_group"]))

    signatures: dict[tuple[str, str], str] = {}
    for node in plan.nodes:
        signature = (node.objective.strip().casefold(), node.assigned_capability)
        if signature in signatures:
            issues.append(DagIssue("DUPLICATE_WORK", f"节点 {node.id} 与 {signatures[signature]} 重复工作", ["nodes", node.id]))
        else:
            signatures[signature] = node.id

    for criterion in plan.acceptance_criteria:
        producers = [node for node in plan.nodes if criterion.id in node.produces_acceptance_criteria]
        checkers = [node for node in plan.nodes if criterion.id in node.checks_acceptance_criteria]
        if not producers:
            issues.append(DagIssue("MISSING_PRODUCER", f"验收标准 {criterion.id} 没有 producer", ["acceptance_criteria", criterion.id]))
        if not checkers:
            issues.append(DagIssue("MISSING_CHECKER", f"验收标准 {criterion.id} 没有 checker", ["acceptance_criteria", criterion.id]))
        if criterion.critical:
            verifier_ids = {node.id for node in checkers if node.assigned_capability == "verifier"}
            if not verifier_ids:
                issues.append(DagIssue("MISSING_INDEPENDENT_VERIFIER", f"关键验收标准 {criterion.id} 必须由 verifier 检查", ["acceptance_criteria", criterion.id]))
            if any(node.id in verifier_ids for node in producers):
                issues.append(DagIssue("PRODUCER_CHECKER_NOT_INDEPENDENT", f"关键验收标准 {criterion.id} 的 producer 与 verifier 不得是同一节点", ["acceptance_criteria", criterion.id]))

    denied = {item.casefold() for item in plan.permissions.denied}
    approval = {item.casefold() for item in plan.permissions.requires_approval}
    for node in plan.nodes:
        required = {item.casefold() for item in node.permissions_required}
        if required & denied:
            issues.append(DagIssue("PERMISSION_DENIED", f"节点 {node.id} 请求了明确拒绝的权限", ["nodes", node.id, "permissions_required"]))
        if required & approval and plan.status == "READY":
            issues.append(DagIssue("APPROVAL_REQUIRED", f"节点 {node.id} 的权限尚需审批，计划不能标记 READY", ["nodes", node.id, "permissions_required"]))

    total_calls = sum(node.estimated_cost.estimated_tool_calls for node in plan.nodes)
    total_tokens = sum(node.estimated_cost.estimated_tokens for node in plan.nodes)
    total_cost = sum(node.estimated_cost.estimated_cost_units for node in plan.nodes)
    if plan.budget.max_tool_calls is not None and total_calls > plan.budget.max_tool_calls:
        issues.append(DagIssue("TOOL_BUDGET_EXCEEDED", "计划工具调用估算超过预算", ["budget", "max_tool_calls"]))
    if plan.budget.max_tokens is not None and total_tokens > plan.budget.max_tokens:
        issues.append(DagIssue("TOKEN_BUDGET_EXCEEDED", "计划 token 估算超过预算", ["budget", "max_tokens"]))
    if plan.budget.max_cost is not None and total_cost > plan.budget.max_cost:
        issues.append(DagIssue("COST_BUDGET_EXCEEDED", "计划成本估算超过预算", ["budget", "max_cost"]))
    return issues
