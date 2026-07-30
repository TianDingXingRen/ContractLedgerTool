"""Workflow coverage for the split template HTTP adapters and services."""

import io
import json

from docx import Document

import template_def
from services import (
    template_authoring_service,
    template_catalog_service,
)
from utils.session_store import save_session_data


def _set_session(client, *, sid=None):
    with client.session_transaction() as flask_session:
        flask_session['_csrf_token'] = 'template-token'
        if sid is not None:
            flask_session['sid'] = sid


def _post(client, path, data):
    data = dict(data)
    data['csrf_token'] = 'template-token'
    return client.post(path, data=data)


def _docx_bytes():
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph('{{甲方}}')
    document.save(stream)
    stream.seek(0)
    return stream


def _configure_template_dir(app, monkeypatch):
    paths = app.extensions['runtime_paths']
    monkeypatch.setattr(
        template_def,
        'TEMPLATES_DIR',
        str(paths.templates_dir),
    )
    return paths


def _save_text_template(name, *, source_docx=''):
    definition = template_def.TemplateDef.create(
        name,
        source_docx,
        [
            {
                'id': 0,
                'key': 'party',
                'label': '甲方',
                'field_type': 'text',
                'required': True,
                'default_value': '',
                'location': {
                    'type': 'paragraph',
                    'body_index': 0,
                    'placeholder': '',
                },
            }
        ],
    )
    return definition.save()


def test_manual_save_editor_and_defaults_workflow(
    app,
    client,
    monkeypatch,
):
    _configure_template_dir(app, monkeypatch)
    _set_session(client)
    response = _post(
        client,
        '/template/manual-save',
        {
            'template_name': '路由拆分回归',
            'stored_name': '',
            'field_label_0': '金额',
            'field_key_0': 'amount',
            'field_type_0': 'number',
            'field_number_decimal_0': '2',
            'field_number_min_0': '0',
            'field_number_max_0': '1000',
            'field_label_1': '状态',
            'field_key_1': 'status',
            'field_type_1': 'select',
            'field_options_1': '草稿\n生效',
        },
    )
    assert response.status_code == 302
    with client.session_transaction() as flask_session:
        session_id = flask_session['sid']

    editor = client.get(response.headers['Location'])
    assert editor.status_code == 200
    assert '路由拆分回归' in editor.get_data(as_text=True)

    _set_session(client, sid=session_id)
    saved = _post(
        client,
        '/template-defaults',
        {'field_0': '12.30', 'field_1': '生效'},
    )
    assert saved.status_code == 200
    assert saved.get_json() == {
        'success': True,
        'message': '预制内容已保存到模板',
        'warnings': [],
    }


def test_template_defaults_reports_session_file_and_data_errors(
    app,
    client,
    monkeypatch,
):
    paths = _configure_template_dir(app, monkeypatch)
    _set_session(client)
    no_template = _post(client, '/template-defaults', {})
    assert no_template.status_code == 400
    assert no_template.get_json()['message'] == '未选择模板'

    _set_session(client, sid='expired')
    expired = _post(client, '/template-defaults', {})
    assert expired.status_code == 400
    assert '会话已失效' in expired.get_json()['message']

    save_session_data(
        'missing',
        {'template_filename': 'missing.contract-template'},
        paths,
    )
    _set_session(client, sid='missing')
    missing = _post(client, '/template-defaults', {})
    assert missing.status_code == 404
    assert missing.get_json()['message'] == '模板文件不存在'

    broken_path = (
        paths.templates_dir / 'broken.contract-template'
    )
    broken_path.write_text('{', encoding='utf-8')
    save_session_data(
        'broken',
        {'template_filename': broken_path.name},
        paths,
    )
    _set_session(client, sid='broken')
    broken = _post(client, '/template-defaults', {})
    assert broken.status_code == 500
    assert broken.get_json()['message'] == '模板操作失败'


def test_template_defaults_rejects_invalid_table_payload(
    app,
    client,
    monkeypatch,
):
    paths = _configure_template_dir(app, monkeypatch)
    definition = template_def.TemplateDef.create(
        '表格默认值',
        '',
        [
            {
                'id': 0,
                'key': 'items',
                'label': '明细',
                'field_type': 'table',
                'required': False,
                'location': {
                    'type': 'table',
                    'table_index': 0,
                    'template_row_index': 1,
                },
                'columns': [
                    {
                        'key': 'name',
                        'label': '名称',
                        'field_type': 'text',
                        'formula': '',
                    }
                ],
            }
        ],
    )
    template_path = definition.save()
    save_session_data(
        'table-defaults',
        {
            'template_path': template_path,
            'template_filename': '表格默认值.contract-template',
        },
        paths,
    )
    _set_session(client, sid='table-defaults')

    response = _post(
        client,
        '/template-defaults',
        {
            'table_cols_0': '{',
            'field_0': json.dumps({'not': 'a list'}),
        },
    )

    assert response.status_code == 400
    message = response.get_json()['message']
    assert '列定义格式错误' in message
    assert '表格数据必须是数组' in message


def test_template_upload_success_and_marker_failure(
    app,
    client,
    monkeypatch,
):
    _configure_template_dir(app, monkeypatch)
    monkeypatch.setattr(
        template_authoring_service,
        'detect_markers_isolated',
        lambda _path: [{'label': '甲方'}],
    )
    _set_session(client)
    uploaded = client.post(
        '/template/upload-style',
        data={
            'csrf_token': 'template-token',
            'file': (_docx_bytes(), 'source.docx'),
        },
        content_type='multipart/form-data',
    )
    assert uploaded.status_code == 302
    created = client.get(uploaded.headers['Location'])
    assert created.status_code == 200
    assert 'source.docx' in created.get_data(as_text=True)

    def fail_detection(_path):
        raise RuntimeError('parser detail')

    monkeypatch.setattr(
        template_authoring_service,
        'detect_markers_isolated',
        fail_detection,
    )
    _set_session(client)
    failed = client.post(
        '/template/upload-style',
        data={
            'csrf_token': 'template-token',
            'file': (_docx_bytes(), 'bad.docx'),
        },
        content_type='multipart/form-data',
    )
    assert failed.status_code == 500
    assert 'parser detail' not in failed.get_data(as_text=True)


def test_template_upload_rejects_unsupported_filename(client):
    _set_session(client)
    response = client.post(
        '/template/upload-style',
        data={
            'csrf_token': 'template-token',
            'file': (io.BytesIO(b'plain'), 'source.txt'),
        },
        content_type='multipart/form-data',
    )

    assert response.status_code == 400
    assert '仅支持' in response.get_data(as_text=True)


def test_template_catalog_routes_translate_expected_failures(
    app,
    client,
    monkeypatch,
):
    paths = _configure_template_dir(app, monkeypatch)
    path = _save_text_template('目录测试')
    definition = template_def.TemplateDef.load(path)
    definition.data['category'] = '销售'
    definition.save(path)

    listed = client.get('/templates?category=销售')
    assert listed.status_code == 200
    assert '目录测试' in listed.get_data(as_text=True)

    assert client.get('/template/invalid').status_code == 400
    assert (
        client.get('/template/missing.contract-template').status_code
        == 404
    )
    broken_path = paths.templates_dir / 'broken.contract-template'
    broken_path.write_text('{', encoding='utf-8')
    assert (
        client.get('/template/broken.contract-template').status_code
        == 500
    )

    _set_session(client)
    copied = _post(
        client,
        '/template/目录测试.contract-template/copy',
        {},
    )
    assert copied.status_code == 302
    copied_files = list(
        paths.templates_dir.glob('*副本*.contract-template')
    )
    assert copied_files
    _set_session(client)
    deleted = _post(
        client,
        f'/template/{copied_files[0].name}/delete',
        {},
    )
    assert deleted.status_code == 302

    _set_session(client)
    failed_copy = _post(
        client,
        '/template/missing.contract-template/copy',
        {},
    )
    assert failed_copy.status_code == 500


def test_template_preview_routes_translate_validation_and_generation_errors(
    app,
    client,
    monkeypatch,
):
    _configure_template_dir(app, monkeypatch)
    _save_text_template('预览测试')
    _save_text_template(
        '无效源路径',
        source_docx='../outside.docx',
    )
    _set_session(client)

    assert _post(
        client,
        '/template/None/preview',
        {},
    ).status_code == 400
    assert _post(
        client,
        '/template/missing.contract-template/preview',
        {},
    ).status_code == 404
    assert _post(
        client,
        '/template/预览测试.contract-template/preview',
        {},
    ).status_code == 400
    assert _post(
        client,
        '/template/无效源路径.contract-template/preview',
        {'field_0': '测试甲方'},
    ).status_code == 400

    monkeypatch.setattr(
        template_catalog_service,
        'generate_docx_isolated',
        lambda *_args: (['生成器拒绝'], ''),
    )
    failed = _post(
        client,
        '/template/预览测试.contract-template/preview',
        {'field_0': '测试甲方'},
    )
    assert failed.status_code == 500
    assert '生成器拒绝' in failed.get_data(as_text=True)


def test_template_version_restore_route_handles_success_and_missing(
    app,
    client,
    monkeypatch,
):
    paths = _configure_template_dir(app, monkeypatch)
    current_path = _save_text_template('版本路由')
    version_dir = (
        paths.templates_dir / 'versions' / '版本路由'
    )
    version_dir.mkdir(parents=True, exist_ok=True)
    version_name = '20260729_120000.contract-template'
    version_path = version_dir / version_name
    version_path.write_bytes(
        paths.templates_dir.joinpath(
            '版本路由.contract-template'
        ).read_bytes()
    )

    _set_session(client)
    restored = _post(
        client,
        f'/template/版本路由/versions/{version_name}/restore',
        {},
    )
    assert restored.status_code == 302
    assert current_path

    _set_session(client)
    missing = _post(
        client,
        '/template/版本路由/versions/missing.contract-template/restore',
        {},
    )
    assert missing.status_code == 404
