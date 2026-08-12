"""Atomic procurement project status transitions."""

from __future__ import annotations

from database.connection_factory import begin_immediate

from .constants import PROJECT_STATUSES, STATUS_TRANSITIONS, WORKFLOW_STATUS_ORDER


_STATUS_RANK = {status: index for index, status in enumerate(WORKFLOW_STATUS_ORDER)}
_AUTO_FINAL_STATUSES = frozenset({'contract_created', 'archived'})


def _can_skip_forward(current_status, new_status):
    """Return whether ``new_status`` is reachable without a workflow regression."""
    current_rank = _STATUS_RANK[current_status]
    target_rank = _STATUS_RANK[new_status]
    if target_rank < current_rank:
        return False
    pending = [current_status]
    visited = {current_status}
    while pending:
        status = pending.pop()
        for candidate in STATUS_TRANSITIONS.get(status, ()):  # pragma: no branch
            if candidate in visited or _STATUS_RANK[candidate] < _STATUS_RANK[status]:
                continue
            if _STATUS_RANK[candidate] > target_rank:
                continue
            if candidate == new_status:
                return True
            visited.add(candidate)
            pending.append(candidate)
    return False


def transition_project(
    conn,
    project_id,
    new_status,
    now,
    *,
    allow_forward_skip=False,
):
    """Validate and conditionally update one project inside the caller transaction."""
    if new_status not in PROJECT_STATUSES:
        raise ValueError('采购项目状态无效')
    begin_immediate(conn)
    row = conn.execute(
        'SELECT status, archived_at FROM procurement_projects WHERE id = ?',
        (project_id,),
    ).fetchone()
    if not row:
        raise ValueError('采购项目不存在')
    current_status = row['status']
    if current_status == new_status:
        return current_status

    allowed = new_status in STATUS_TRANSITIONS.get(current_status, set())
    if allow_forward_skip:
        if current_status in _AUTO_FINAL_STATUSES:
            allowed = False
        elif not allowed:
            allowed = _can_skip_forward(current_status, new_status)
    if not allowed:
        raise ValueError(
            f'采购项目状态已是“{current_status}”，不能自动变更为“{new_status}”'
        )

    archived_at = now if new_status == 'archived' else (row['archived_at'] or '')
    cursor = conn.execute(
        """UPDATE procurement_projects
              SET status = ?, archived_at = ?, updated_at = ?
            WHERE id = ? AND status = ?""",
        (new_status, archived_at, now, project_id, current_status),
    )
    if cursor.rowcount != 1:
        raise ValueError('采购项目状态已变化，请刷新后重试')
    return current_status
