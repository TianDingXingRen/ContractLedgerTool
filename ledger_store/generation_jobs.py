"""Persistent journal for crash-safe contract generation."""

from __future__ import annotations

from datetime import datetime


ACTIVE_STATES = ('prepared', 'staged', 'file_moved')
TERMINAL_STATES = ('completed', 'failed', 'recovered', 'attention')
VALID_PREVIOUS_STATES = {
    'staged': ('prepared',),
    'file_moved': ('staged',),
    'completed': ACTIVE_STATES,
    'failed': ACTIVE_STATES,
    'recovered': ACTIVE_STATES,
    'attention': ACTIVE_STATES,
}


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def create(get_conn, portable_path, job_id, output_path, staging_path):
    now = _now()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO contract_generation_jobs (
                   job_id, state, output_path, staging_path, created_at, updated_at
               ) VALUES (?, 'prepared', ?, ?, ?, ?)""",
            (
                job_id,
                portable_path(output_path),
                portable_path(staging_path),
                now,
                now,
            ),
        )
    return get(get_conn, job_id)


def update(
    get_conn,
    job_id,
    state,
    *,
    contract_id=None,
    error=None,
    recovery_action=None,
    conn=None,
):
    assignments = ['state = ?', 'updated_at = ?']
    values = [state, _now()]
    if contract_id is not None:
        assignments.append('contract_id = ?')
        values.append(int(contract_id))
    if error is not None:
        assignments.append('error = ?')
        values.append(str(error)[:2000])
    if recovery_action is not None:
        assignments.append('recovery_action = ?')
        values.append(str(recovery_action)[:2000])
    if state == 'completed':
        assignments.append('completed_at = ?')
        values.append(_now())
    values.append(job_id)

    def _execute(connection):
        previous_states = VALID_PREVIOUS_STATES.get(state)
        if not previous_states:
            raise ValueError(f'Unsupported generation job state: {state}')
        placeholders = ','.join('?' for _ in previous_states)
        cursor = connection.execute(
            f"""UPDATE contract_generation_jobs
                SET {', '.join(assignments)}
                WHERE job_id = ? AND state IN ({placeholders})""",
            values + list(previous_states),
        )
        if cursor.rowcount != 1:
            current = connection.execute(
                'SELECT state FROM contract_generation_jobs WHERE job_id = ?',
                (job_id,),
            ).fetchone()
            if current is None:
                raise KeyError(f'Generation job does not exist: {job_id}')
            raise ValueError(
                f'Invalid generation job transition: {current["state"]} -> {state}'
            )

    if conn is not None:
        _execute(conn)
    else:
        with get_conn() as managed_conn:
            _execute(managed_conn)


def get(get_conn, job_id):
    with get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM contract_generation_jobs WHERE job_id = ?',
            (job_id,),
        ).fetchone()
    return dict(row) if row else None


def list_unfinished(get_conn):
    placeholders = ','.join('?' for _ in ACTIVE_STATES)
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT * FROM contract_generation_jobs
                WHERE state IN ({placeholders})
                ORDER BY created_at, job_id""",
            ACTIVE_STATES,
        ).fetchall()
    return [dict(row) for row in rows]


def state_counts(get_conn):
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT state, COUNT(*) AS count FROM contract_generation_jobs GROUP BY state'
        ).fetchall()
    counts = {state: 0 for state in ACTIVE_STATES + TERMINAL_STATES}
    counts.update({row['state']: int(row['count']) for row in rows})
    return counts
