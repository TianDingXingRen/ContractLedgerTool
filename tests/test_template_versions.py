import json
import os

import template_def
import pytest


def _write_definition(path, fields, **overrides):
    data = {
        'format_version': '1.0',
        'template_name': '测试模板',
        'source_docx': 'source.docx',
        'fields': fields,
    }
    data.update(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


def test_compare_version_reports_field_and_metadata_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(template_def, 'TEMPLATES_DIR', str(tmp_path))
    current_path = tmp_path / '测试模板.contract-template'
    version_dir = tmp_path / 'versions' / '测试模板'
    version_path = version_dir / '20260720_120000.contract-template'
    _write_definition(
        current_path,
        [
            {'key': 'party_a', 'label': '甲方', 'field_type': 'text'},
            {'key': 'amount', 'label': '金额（元）', 'field_type': 'number'},
        ],
        source_docx='current.docx',
    )
    _write_definition(
        version_path,
        [
            {'key': 'party_a', 'label': '甲方名称', 'field_type': 'text'},
            {'key': 'party_b', 'label': '乙方', 'field_type': 'text'},
        ],
        source_docx='historical.docx',
    )

    comparison = template_def.compare_version('测试模板', version_path.name)

    assert comparison['added'] == ['amount']
    assert comparison['removed'] == ['party_b']
    assert comparison['changed'] == ['party_a']
    assert comparison['metadata_changed'] == ['source_docx']
    assert comparison['has_changes'] is True


def test_compare_version_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(template_def, 'TEMPLATES_DIR', str(tmp_path))
    _write_definition(tmp_path / '测试模板.contract-template', [])

    try:
        template_def.compare_version('测试模板', '..\\outside.contract-template')
    except FileNotFoundError:
        pass
    else:
        raise AssertionError('path traversal must not resolve to a version file')


def test_restore_version_replace_failure_preserves_current_template(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(template_def, 'TEMPLATES_DIR', str(tmp_path))
    current_path = tmp_path / '测试模板.contract-template'
    version_path = (
        tmp_path / 'versions' / '测试模板' / '20260720_120000.contract-template'
    )
    _write_definition(
        current_path,
        [{'key': 'current', 'label': '当前', 'field_type': 'text'}],
    )
    _write_definition(
        version_path,
        [{'key': 'old', 'label': '历史', 'field_type': 'text'}],
    )
    before = current_path.read_bytes()
    original_replace = template_def.os.replace

    def fail_restore_replace(source, target):
        if '.restore-' in str(source):
            raise OSError('replace failed')
        return original_replace(source, target)

    monkeypatch.setattr(template_def.os, 'replace', fail_restore_replace)

    with pytest.raises(OSError, match='replace failed'):
        template_def.restore_version('测试模板', version_path.name)

    assert current_path.read_bytes() == before
    assert not list(tmp_path.glob('*.restore-*'))


def test_versions_page_renders_comparison_summary(app, client, tmp_path, monkeypatch):
    monkeypatch.setattr(template_def, 'TEMPLATES_DIR', str(tmp_path))
    current_path = tmp_path / '测试模板.contract-template'
    version_path = tmp_path / 'versions' / '测试模板' / '20260720_120000.contract-template'
    _write_definition(current_path, [{'key': 'amount', 'label': '金额', 'field_type': 'number'}])
    _write_definition(version_path, [{'key': 'party_a', 'label': '甲方', 'field_type': 'text'}])

    response = client.get('/template/测试模板/versions')

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '与当前版本相比' in html
    assert '新增 1' in html
    assert '移除 1' in html
    assert os.path.basename(version_path) in html
