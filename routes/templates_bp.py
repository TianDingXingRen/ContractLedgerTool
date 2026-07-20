"""Template management routes: upload, create, edit, list, delete, versions."""

import os
import uuid
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from flask import render_template, request, redirect, url_for, session, jsonify, send_file

from routes.legacy_blueprint import LegacyEndpointBlueprint

import template_def
import field_eval
from services.contract_preview_service import editor_preview_model
from utils import helpers
from utils.logger import get_logger
from utils.security import MAX_TEMPLATE_FIELDS, MAX_TABLE_COLUMNS, MAX_TABLE_ROWS, bounded_int, bounded_decimal_places, limit_text
from utils.errors import safe_error, safe_parse_error, GENERIC_TEMPLATE_ERROR

ALLOWED_EXTENSIONS = {'docx', 'doc'}

_DOC_CONVERT_TIMEOUT = 30  # 秒


def _is_valid_docx(filepath):
    """验证文件是否为合法的 DOCX (ZIP 格式) — 检查文件头魔数"""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(4)
        return header == b'PK\x03\x04'
    except Exception:
        get_logger().debug('DOCX header validation failed: %s', filepath, exc_info=True)
        return False


def _try_convert_doc_to_docx(doc_path):
    """尝试将 .doc 转换为 .docx，返回转换后的路径或 None。

    COM 操作在线程中执行，最多等待 _DOC_CONVERT_TIMEOUT 秒，
    超时后终止本工具启动的 Word/WPS 进程。
    """
    target = doc_path.rsplit('.', 1)[0] + '.docx'
    _state = {'proc': None}

    def _convert():
        # 方法1: 使用 pythoncom + Word
        try:
            import pythoncom
            pythoncom.CoInitialize()
            from win32com import client
            word = client.Dispatch('Word.Application')
            word.Visible = False
            word.DisplayAlerts = 0
            doc = word.Documents.Open(os.path.abspath(doc_path))
            doc.SaveAs2(os.path.abspath(target), FileFormat=16)  # wdFormatXMLDocument
            doc.Close()
            word.Quit()
            pythoncom.CoUninitialize()
            if os.path.exists(target) and os.path.getsize(target) > 0:
                return True
        except Exception:
            get_logger().debug('Word COM DOC conversion failed', exc_info=True)

        # 方法2: 使用 WPS COM
        for progid in ['WPS.Application', 'KWPS.Application', 'Ket.Application']:
            try:
                import pythoncom
                pythoncom.CoInitialize()
                from win32com import client
                app = client.Dispatch(progid)
                app.Visible = False
                doc = app.Documents.Open(os.path.abspath(doc_path))
                doc.SaveAs2(os.path.abspath(target), FileFormat=16)
                doc.Close()
                app.Quit()
                pythoncom.CoUninitialize()
                if os.path.exists(target) and os.path.getsize(target) > 0:
                    return True
            except Exception:
                get_logger().debug('WPS COM DOC conversion failed: %s', progid, exc_info=True)

        return False

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_convert)
            try:
                result = future.result(timeout=_DOC_CONVERT_TIMEOUT)
            except FutureTimeoutError:
                get_logger().warning('.doc 转换超时（%d 秒）', _DOC_CONVERT_TIMEOUT)
                return None
            if result:
                return target
    except Exception:
        get_logger().warning('.doc 转换过程异常', exc_info=True)
    return None


def register(app):
    bp = LegacyEndpointBlueprint('templates', __name__)
    # ── 模板保存的辅助函数（从 template_manual_save 提取）──

    def _parse_field_location(idx, field_type):
        """解析字段在源文档中的位置信息。返回 (location_dict, error_string)。"""
        if field_type == 'table':
            table_idx = request.form.get(f'field_table_index_{idx}', '')
            try:
                return {
                    'type': 'table',
                    'table_index': bounded_int(table_idx, default=0, label='表格位置'),
                    'template_row_index': bounded_int(
                        request.form.get(f'field_template_row_index_{idx}', 1), default=1, label='表格模板行',
                    ),
                }, ''
            except ValueError as e:
                return None, str(e)

        table_cell_idx = request.form.get(f'field_table_index_{idx}', '')
        if table_cell_idx:
            try:
                return {
                    'type': 'table_cell',
                    'table_index': bounded_int(table_cell_idx, label='表格位置'),
                    'row_index': bounded_int(request.form.get(f'field_row_index_{idx}', 0), label='行位置'),
                    'col_index': bounded_int(request.form.get(f'field_col_index_{idx}', 0), label='列位置'),
                    'placeholder': limit_text(request.form.get(f'field_placeholder_{idx}', ''), 200),
                }, ''
            except ValueError as e:
                return None, str(e)

        body_index = request.form.get(f'field_body_index_{idx}', '')
        if body_index:
            try:
                return {
                    'type': 'paragraph',
                    'body_index': bounded_int(body_index, label='段落位置'),
                    'placeholder': limit_text(request.form.get(f'field_placeholder_{idx}', ''), 200),
                }, ''
            except ValueError as e:
                return None, str(e)

        return {'type': 'paragraph', 'body_index': 0, 'placeholder': ''}, ''

    def _parse_table_columns(idx, label):
        """解析表格字段的列定义。返回 (columns_list, error_string)。"""
        columns = []
        col_idx = 0
        while True:
            if col_idx >= MAX_TABLE_COLUMNS:
                return None, f'{label} 的列数不能超过 {MAX_TABLE_COLUMNS}'
            col_label = request.form.get(f'col_label_{idx}_{col_idx}')
            if col_label is None:
                break
            col_label = col_label.strip()
            if not col_label:
                col_idx += 1
                continue
            col_type = request.form.get(f'col_type_{idx}_{col_idx}', 'text')
            if col_type not in {'text', 'number', 'textarea', 'select', 'calculated'}:
                col_type = 'text'
            col_formula = request.form.get(f'col_formula_{idx}_{col_idx}', '').strip()
            if col_type == 'calculated' and not col_formula:
                col_type = 'text'
            if col_type == 'calculated':
                try:
                    field_eval.validate_formula(col_formula)
                except field_eval.FormulaError as e:
                    return None, f'{col_label} 公式无效：{e}'
            col_default = limit_text(request.form.get(f'col_default_{idx}_{col_idx}', ''), 2000)
            col_key = helpers.safe_col_key(col_label, col_idx, {c['key'] for c in columns})
            column = {
                'key': col_key, 'label': col_label, 'field_type': col_type,
                'formula': col_formula if col_type == 'calculated' else '',
                'default_value': col_default if col_type != 'calculated' else '',
            }
            if col_type == 'select':
                options_text = request.form.get(f'col_options_{idx}_{col_idx}', '')
                column['options'] = [
                    limit_text(option.strip(), 200)
                    for option in options_text.splitlines() if option.strip()
                ][:100]
            if col_type == 'number':
                try:
                    column['decimal_places'] = bounded_decimal_places(
                        request.form.get(f'col_decimal_{idx}_{col_idx}', 2)
                    )
                    if col_default:
                        column['default_value'] = helpers.normalize_number_field_value(
                            col_default, column
                        )
                except ValueError as e:
                    return None, f'{col_label}{e}'
            columns.append(column)
            col_idx += 1
        return columns or [{'key': 'col_0', 'label': '内容', 'field_type': 'text', 'formula': ''}], ''

    def _parse_single_field(idx, fields_so_far):
        """从 request.form 解析单个字段定义。返回 (field_dict, error_string)。"""
        label = request.form.get(f'field_label_{idx}', '').strip()
        if not label:
            return None, ''

        field_type = request.form.get(f'field_type_{idx}', 'text')
        if field_type not in {'text', 'number', 'textarea', 'select', 'table', 'calculated'}:
            field_type = 'text'
        field_formula = request.form.get(f'field_formula_{idx}', '').strip()
        if field_type == 'calculated' and not field_formula:
            field_type = 'text'
        if field_type == 'calculated':
            try:
                field_eval.validate_formula(field_formula)
            except field_eval.FormulaError as e:
                return None, f'{label} 公式无效：{e}'

        submitted_key = request.form.get(f'field_key_{idx}', '').strip()
        key = helpers.unique_key(helpers.field_key_from_label(submitted_key or label, f'field_{idx}'), fields_so_far)

        location, loc_err = _parse_field_location(idx, field_type)
        if loc_err:
            return None, loc_err

        field = {
            'id': idx, 'key': key, 'label': label,
            'field_type': field_type,
            'required': bool(request.form.get(f'field_required_{idx}')),
            'location': location,
        }

        if field_type not in ('table', 'calculated'):
            field['default_value'] = limit_text(request.form.get(f'field_default_{idx}', ''))

        if field_type == 'select':
            options_text = request.form.get(f'field_options_{idx}', '')
            field['options'] = [limit_text(o.strip(), 200) for o in options_text.split('\n') if o.strip()][:100]
        elif field_type == 'number':
            try:
                field['decimal_places'] = bounded_decimal_places(
                    request.form.get(f'field_number_decimal_{idx}', 2)
                )
                min_raw = request.form.get(f'field_number_min_{idx}', '').strip()
                max_raw = request.form.get(f'field_number_max_{idx}', '').strip()
                field['min_value'] = float(min_raw) if min_raw else None
                field['max_value'] = float(max_raw) if max_raw else None
                if (field['min_value'] is not None and field['max_value'] is not None
                        and field['min_value'] > field['max_value']):
                    return None, f'{label} 的最小值不能大于最大值'
                if field.get('default_value'):
                    field['default_value'] = helpers.normalize_number_field_value(
                        field['default_value'], field
                    )
            except ValueError as e:
                return None, f'{label} 数字配置无效：{e}'
        elif field_type == 'calculated':
            field['formula'] = field_formula
            try:
                field['decimal_places'] = bounded_decimal_places(request.form.get(f'field_decimal_{idx}', 2))
            except ValueError as e:
                return None, str(e)
            field['depends_on'] = list(field_eval.get_calc_deps(field))
        elif field_type == 'table':
            columns, col_err = _parse_table_columns(idx, label)
            if col_err:
                return None, col_err
            field['columns'] = columns

        return field, ''

    # ── 路由定义 ──

    @bp.route('/create-template')
    def create_template():
        style_sid = request.args.get('style_sid')
        if not style_sid:
            style_sid = session.pop('style_sid', None)
        stored_name = ''
        raw_name = ''
        detected_fields = []

        if style_sid:
            try:
                style_data = helpers.load_session_data(style_sid)
                stored_name = style_data.get('stored_name', '')
                raw_name = style_data.get('raw_name', '')
                detected_fields = style_data.get('detected_fields', [])
            except (FileNotFoundError, json.JSONDecodeError):
                get_logger().info('模板样式会话已失效: %s', style_sid, exc_info=True)

        return render_template('create_template.html',
            stored_name=stored_name,
            raw_name=raw_name,
            detected_fields=detected_fields,
        )

    @bp.route('/template/upload-style', methods=['POST'])
    def upload_style():
        if 'file' not in request.files:
            return '未选择文件', 400
        file = request.files['file']
        if file.filename == '':
            return '未选择文件', 400

        raw_name = file.filename
        if '.' not in raw_name:
            return '请上传 .docx 或 .doc 格式的文档', 400
        ext = raw_name.rsplit('.', 1)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return '仅支持 .docx 和 .doc 格式', 400

        session_id = str(uuid.uuid4())
        stored_name = f'{session_id}.{ext}'
        filepath = os.path.join(helpers.UPLOAD_FOLDER, stored_name)
        file.save(filepath)

        # .doc 文件自动转换为 .docx
        if ext == 'doc':
            converted = _try_convert_doc_to_docx(filepath)
            if converted and _is_valid_docx(converted):
                # 替换为转换后的 .docx 文件
                os.remove(filepath)
                new_stored = f'{session_id}.docx'
                new_path = os.path.join(helpers.UPLOAD_FOLDER, new_stored)
                shutil.move(converted, new_path)
                filepath = new_path
                stored_name = new_stored
                get_logger().info('DOC converted: %s -> %s', raw_name, new_stored)
            else:
                os.remove(filepath)
                return '无法将 .doc 转换为 .docx，请用 Word/WPS 打开文件后另存为 .docx 格式再上传', 400

        if not _is_valid_docx(filepath):
            os.remove(filepath)
            return '文件不是有效的 DOCX 格式（需为 ZIP 压缩的 Office 文档）', 400

        try:
            detected_fields = helpers.detect_markers(filepath)
        except Exception as e:
            return safe_parse_error(e, 'DOCX占位符解析失败', 500)

        helpers.save_session_data(session_id, {
            'raw_name': raw_name,
            'stored_name': stored_name,
            'detected_fields': detected_fields,
        })
        session['style_sid'] = session_id

        return redirect(url_for('create_template'))

    @bp.route('/template/manual-save', methods=['POST'])
    def template_manual_save():
        template_name = request.form.get('template_name', '').strip()
        if not template_name:
            return '模板名称不能为空', 400
        if len(template_name) > 120:
            return '模板名称不能超过120个字符', 400
        template_name = limit_text(template_name, 120)
        category = limit_text(request.form.get('template_category', '').strip(), 50)

        try:
            stored_name = helpers.validate_stored_docx(request.form.get('stored_name', '').strip())
        except ValueError as e:
            return str(e), 400

        fields = []
        for idx in range(MAX_TEMPLATE_FIELDS):
            if f'field_label_{idx}' not in request.form:
                break
            field, err = _parse_single_field(idx, fields)
            if err:
                return err, 400
            if field:
                fields.append(field)

        if not fields:
            return '请至少添加一个字段', 400

        for i, f in enumerate(fields):
            f['id'] = i

        tpl = template_def.TemplateDef.create(template_name, stored_name, fields)
        if category:
            tpl.data['category'] = category
        try:
            tpl.validate()
        except template_def.TemplateValidationError as e:
            return f'模板数据验证失败：{str(e)}', 400
        if stored_name:
            binding_errors = helpers.validate_template_source_bindings(
                fields, helpers.safe_uploaded_docx_path(stored_name)
            )
            if binding_errors:
                return '模板预检失败：\n' + '\n'.join(binding_errors), 400

        path = tpl.save()

        sid = str(uuid.uuid4())
        helpers.save_session_data(sid, {
            'template_name': template_name,
            'template_path': path,
            'template_filename': os.path.basename(path),
            'stored_name': stored_name,
            'step': 'editor',
        })
        session['sid'] = sid

        return redirect(url_for('template_editor', name=os.path.basename(path)))

    @bp.route('/templates')
    def list_templates():
        templates = template_def.list_templates()
        category_filter = request.args.get('category', '').strip()
        if category_filter:
            templates = [t for t in templates if t.get('category', '') == category_filter]
        return render_template('list.html', templates=templates)

    @bp.route('/template/<name>')
    def template_editor(name):
        try:
            path = helpers.safe_template_path(name)
        except ValueError as e:
            return str(e), 400
        if not os.path.exists(path):
            return f'模板文件不存在: {name}', 404

        try:
            tpl = template_def.TemplateDef.load(path)
        except Exception as e:
            return safe_error(e, '加载模板失败', 500)

        sid = str(uuid.uuid4())
        helpers.save_session_data(sid, {
            'template_name': tpl.name,
            'template_path': path,
            'template_filename': os.path.basename(path),
            'stored_name': tpl.data.get('source_docx', ''),
            'step': 'editor',
        })
        session['sid'] = sid

        # 确保所有字段都有 id（兼容手动创建/旧版模板）
        fields = tpl.data['fields']
        for i, f in enumerate(fields):
            if 'id' not in f:
                f['id'] = i

        preview_model = editor_preview_model(tpl.data.get('source_docx', ''), fields)
        return render_template(
            'editor.html',
            fields=fields,
            field_count=len(fields),
            template_name=tpl.name,
            template_filename=os.path.basename(path),
            preview_blocks=preview_model.get('blocks', []),
            preview_warnings=preview_model.get('warnings', []),
            batch_allowed=True,
        )

    @bp.route('/template/<name>/preview', methods=['POST'])
    def template_preview(name):
        if not name or name == 'None' or name == '未命名':
            return '模板名称无效，请先保存模板', 400
        try:
            path = helpers.safe_template_path(name)
        except ValueError as e:
            return str(e), 400
        if not os.path.exists(path):
            return f'模板文件不存在: {name}', 404
        try:
            tpl = template_def.TemplateDef.load(path)
        except Exception as e:
            return safe_error(e, '加载模板失败', 500)

        fields = tpl.data.get('fields', [])
        field_values, input_errors = helpers.prepare_generation_values(fields, request.form)
        if input_errors:
            return '\n'.join(input_errors), 400

        source_docx = tpl.data.get('source_docx', '')
        output_path = os.path.join(helpers.OUTPUT_FOLDER, f'preview_{uuid.uuid4().hex[:8]}.docx')

        template_path = ''
        if source_docx:
            try:
                template_path = helpers.safe_uploaded_docx_path(source_docx)
            except ValueError as e:
                return safe_error(e, '模板路径无效')
        gen_errors, output_path = helpers.generate_docx_document(
            tpl.data, fields, field_values, template_path, output_path
        )
        if gen_errors:
            return '预览生成失败：\n' + '\n'.join(gen_errors), 500

        return send_file(
            output_path,
            as_attachment=True,
            download_name=f'{tpl.name}_预览.docx',
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )

    @bp.route('/template/<filename>/delete', methods=['POST'])
    def template_delete(filename):
        template_def.delete_template(os.path.basename(filename))
        return redirect(url_for('list_templates'))

    @bp.route('/template/<filename>/copy', methods=['POST'])
    def template_copy(filename):
        new_filename = template_def.copy_template(filename)
        if not new_filename:
            return '复制模板失败', 500
        get_logger().info('Copied template %s -> %s', filename, new_filename)
        return redirect(url_for('list_templates'))

    @bp.route('/template/<name>/versions')
    def template_versions(name):
        if name.endswith('.contract-template'):
            template_name = name[:-len('.contract-template')]
        else:
            template_name = name
        versions = template_def.list_versions(template_name)
        return render_template('versions.html',
            template_name=template_name, versions=versions)

    @bp.route('/template/<name>/versions/<version_filename>/restore', methods=['POST'])
    def template_version_restore(name, version_filename):
        template_name = name[:-len('.contract-template')] if name.endswith('.contract-template') else name
        try:
            template_def.restore_version(template_name, version_filename)
        except FileNotFoundError as e:
            return safe_error(e, '版本文件不存在', 404)
        return redirect(url_for('list_templates'))

    @bp.route('/template-defaults', methods=['POST'])
    def save_template_defaults():
        sid = session.get('sid')
        if not sid:
            return jsonify({'success': False, 'message': '未选择模板'}), 400

        try:
            data = helpers.load_session_data(sid)
        except (FileNotFoundError, json.JSONDecodeError):
            return jsonify({'success': False, 'message': '会话已失效，请重新选择模板'}), 400

        template_path_data = helpers.template_path_from_session(data)
        if not template_path_data or not os.path.exists(template_path_data):
            return jsonify({'success': False, 'message': '模板文件不存在'}), 404

        try:
            tpl = template_def.TemplateDef.load(template_path_data)
        except Exception as e:
            get_logger().error('模板加载失败: %s', e, exc_info=True)
            return jsonify({'success': False, 'message': GENERIC_TEMPLATE_ERROR}), 500

        fields = tpl.data.get('fields', [])
        errors = []
        for i, field in enumerate(fields):
            field_type = field.get('field_type')
            if field_type == 'table':
                cols_raw = request.form.get(f'table_cols_{field.get("id")}')
                if cols_raw:
                    try:
                        submitted_cols = json.loads(cols_raw)
                        field['columns'] = helpers.normalize_table_columns(field, submitted_cols)
                    except (json.JSONDecodeError, TypeError):
                        errors.append(f'{field.get("label", field.get("key"))} 的列定义格式错误')
                    except (ValueError, field_eval.FormulaError) as e:
                        errors.append(f'{field.get("label", field.get("key"))} 的列定义无效：{e}')

                raw_val = request.form.get(f'field_{i}', '')
                try:
                    rows_data = json.loads(raw_val) if raw_val else []
                    if not isinstance(rows_data, list):
                        raise ValueError('表格数据必须是数组')
                    if len(rows_data) > MAX_TABLE_ROWS:
                        raise ValueError(f'表格行数不能超过 {MAX_TABLE_ROWS}')
                    field['default_rows'] = helpers.filter_table_rows(field, rows_data)
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    errors.append(f'{field.get("label", field.get("key"))} 的预制表格内容无效：{e}')
            elif field_type != 'calculated':
                default_value = limit_text(request.form.get(f'field_{i}', ''))
                if field_type == 'number' and default_value:
                    try:
                        default_value = helpers.normalize_number_field_value(default_value, field)
                    except ValueError as e:
                        errors.append(f'{field.get("label", field.get("key"))}{e}')
                elif field_type == 'select' and default_value:
                    options = [str(option) for option in field.get('options', [])]
                    if options and default_value not in options:
                        errors.append(f'{field.get("label", field.get("key"))} 的预制选项无效')
                field['default_value'] = default_value

        if errors:
            return jsonify({'success': False, 'message': '\n'.join(errors)}), 400

        # Binding 预警：不阻断保存，仅在字段位置与源文档不匹配时发出警告
        warnings_list = []
        source_docx = tpl.data.get('source_docx', '')
        if source_docx:
            try:
                docx_path = helpers.safe_uploaded_docx_path(source_docx)
                binding_warnings = helpers.validate_template_source_bindings(fields, docx_path)
                if binding_warnings:
                    warnings_list = binding_warnings
                    get_logger().warning('模板默认值保存时的 binding 预警：%s', '; '.join(binding_warnings))
            except ValueError:
                get_logger().warning(
                    '模板源文件路径无效，无法执行默认值绑定预检: %s',
                    source_docx,
                    exc_info=True,
                )

        try:
            tpl.save(template_path_data)
        except Exception as e:
            get_logger().error('保存模板默认值失败: %s', e, exc_info=True)
            return jsonify({'success': False, 'message': GENERIC_TEMPLATE_ERROR}), 500

        return jsonify({
            'success': True,
            'message': '预制内容已保存到模板',
            'warnings': warnings_list,
        })

    app.register_blueprint(bp)
