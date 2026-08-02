"""Regression tests for repeatable quality-gate orchestration."""

from pathlib import Path

from scripts import quality_gate


def test_quality_gate_uses_isolated_temporary_directories(
    tmp_path,
    monkeypatch,
):
    commands = []
    reports = []
    monkeypatch.setattr(quality_gate, 'ROOT', tmp_path)
    monkeypatch.setattr(
        quality_gate,
        'run',
        lambda command: commands.append(command),
    )
    monkeypatch.setattr(
        quality_gate,
        'check_module_coverage',
        lambda report: reports.append(report),
    )

    quality_gate.run_full_tests_with_coverage()

    assert len(commands) == 2
    nonperformance = next(
        argument
        for argument in commands[0]
        if str(argument).startswith('--basetemp=')
    )
    performance = next(
        argument
        for argument in commands[1]
        if str(argument).startswith('--basetemp=')
    )
    assert nonperformance != performance
    assert '.pytest_basetemp_quality_gate' not in nonperformance
    assert '.pytest_basetemp_performance' not in performance
    assert str(tmp_path / 'build' / 'quality-gate-') in nonperformance
    assert reports == [tmp_path / 'build' / 'coverage.json']
    assert not any(
        path.name.startswith('quality-gate-')
        for path in Path(tmp_path / 'build').iterdir()
    )
