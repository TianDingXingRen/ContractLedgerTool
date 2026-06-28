from scripts import worktree_scope


def test_worktree_scope_groups_common_project_areas():
    grouped = worktree_scope.summarize([
        ' M app.py',
        ' M ledger_store/__init__.py',
        '?? procurement_store/quote_jobs.py',
        ' M routes/procurement_bp.py',
        ' M services/quote_service.py',
        ' M templates/base.html',
        ' M static/style.css',
        '?? tests/test_example.py',
        ' M build_installer.py',
        '?? data/contracts.db',
        '?? 技术债务.md',
    ])

    assert [path for _status, path in grouped['backend-core']] == ['app.py']
    assert {path for _status, path in grouped['stores']} == {
        'ledger_store/__init__.py',
        'procurement_store/quote_jobs.py',
    }
    assert {path for _status, path in grouped['routes-services']} == {
        'routes/procurement_bp.py',
        'services/quote_service.py',
    }
    assert {path for _status, path in grouped['frontend']} == {
        'templates/base.html',
        'static/style.css',
    }
    assert grouped['runtime-data'] == [('??', 'data/contracts.db')]
    assert grouped['docs-tooling'] == [('??', '技术债务.md')]
