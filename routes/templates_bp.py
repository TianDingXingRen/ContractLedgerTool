"""Template management routes: upload, create, edit, list, delete, versions."""

import os
import uuid
import json

from flask import render_template, request, redirect, url_for, session, jsonify, send_file

import template_def
import field_eval
import docx_builder
from docx import Document
from utils import helpers
from utils.logger import get_logger
from utils.security import MAX_TEMPLATE_FIELDS, MAX_TABLE_COLUMNS, MAX_TABLE_ROWS, bounded_int, bounded_decimal_places, limit_text

ALLOWED_EXTENSIONS = {'docx'}


def _is_valid_docx(filepath):
    """验证文件是否为合法的 DOCX (ZIP 格式) — 检查文件头魔数"""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(4)
        return header == b'PK\x03\x04'
    except Exception:
        return False


def register(app):
    @app.route('/create-template')
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
                pass

        return render_template('create_template.html',
            stored_name=stored_name,
            raw_name=raw_name,
            detected_fields=detected_fields,
        )

    @app.route('/template/upload-style', methods=['POST'])
    def upload_style():
        if 'file' not in request.files:
            return '未选择文件', 400
        file = request.files['file']
        if file.filename == '':
            return '未选择文件', 400

        raw_name = file.filename
        if '.' not in raw_name:
            return '请上传 .docx 格式的文档', 400
        ext = raw_name.rsplit('.', 1)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return '请上传 .docx 格式的文档', 400

        session_id = str(uuid.uuid4())
        stored_name = f'{session_id}.{ext}'
        filepath = os.path.join(helpers.UPLOAD_FOLDER, stored_name)
        file.save(filepath)

        if not _is_valid_docx(filepath):
            os.remove(filepath)
            return '文件不是有效的 DOCX 格式（需为 ZIP 压缩的 Office 文档）', 400

        try:
            detected_fields = helpers.detect_markers(filepath)
        except Exception as e:
            return f'解析文档失败：{str(e)}', 500

        helpers.save_session_data(session_id, {
            'raw_name': raw_name,
            'stored_name': stored_name,
            'detected_fields': detected_fields,
        })
        session['style_sid'] = session_id

        return redirect(url_for('create_template'))

    @app.route('/template/manual-save', methods=['POST'])
    def template_manual_save():
        template_name = request.form.get('template_name', '').strip()
        if not template_name:
            return '模板名称不能为空', 400
        category = limit_text(request.form.get('template_category', '').strip(), 50)

        try:
            stored_name = helpers.validate_stored_docx(request.form.get('stored_name', '').strip())
        except ValueError as e:
            return str(e), 400

        fields = []
        idx = 0

        while True:
            if idx >= MAX_TEMPLATE_FIELDS:
                return f'字段数量不能超过 {MAX_TEMPLATE_FIELDS}', 400
            label_key = f'field_label_{idx}'
            if label_key not in request.form:
                break

            label = request.form.get(label_key, '').strip()
            if not label:
                idx += 1
                continue

            field_type = request.form.get(f'field_type_{idx}', 'text')
            field_formula = request.form.get(f'field_formula_{idx}', '').strip()
            if field_type == 'calculated' and not field_formula:
                field_type = 'text'
            if field_type == 'calculated':
                try:
                    field_eval.validate_formula(field_formula)
                except field_eval.FormulaError as e:
                    return f'{label} 公式无效：{e}', 400
            required = bool(request.form.get(f'field_required_{idx}'))

            submitted_key = request.form.get(f'field_key_{idx}', '').strip()
            key_source = submitted_key or label
            key = helpers.unique_key(helpers.field_key_from_label(key_source, f'field_{idx}'), fields)

            location = {'type': 'paragraph', 'body_index': 0, 'placeholder': ''}
            if field_type == 'table':
                table_idx = request.form.get(f'field_table_index_{idx}', '')
                try:
                    location = {
                        'type': 'table',
                        'table_index': bounded_int(table_idx, default=0, label='表格位置'),
                        'template_row_index': bounded_int(
                            request.form.get(f'field_template_row_index_{idx}', 1),
                            default=1,
                            label='表格模板行',
                        ),
                    }
                except ValueError as e:
                    return str(e), 400
            else:
                table_cell_idx = request.form.get(f'field_table_index_{idx}', '')
                if table_cell_idx:
                    try:
                        location = {
                            'type': 'table_cell',
                            'table_index': bounded_int(table_cell_idx, label='表格位置'),
                            'row_index': bounded_int(request.form.get(f'field_row_index_{idx}', 0), label='行位置'),
                            'col_index': bounded_int(request.form.get(f'field_col_index_{idx}', 0), label='列位置'),
                            'placeholder': limit_text(request.form.get(f'field_placeholder_{idx}', ''), 200),
                        }
                    except ValueError as e:
                        return str(e), 400
                else:
                    body_index = request.form.get(f'field_body_index_{idx}', '')
                    if body_index:
                        try:
                            location = {
                                'type': 'paragraph',
                                'body_index': bounded_int(body_index, label='段落位置'),
                                'placeholder': limit_text(request.form.get(f'field_placeholder_{idx}', ''), 200),
                            }
                        except ValueError as e:
                            return str(e), 400

            field = {
                'id': idx,
                'key': key,
                'label': label,
                'field_type': field_type,
                'required': required,
                'location': location,
            }

            if field_type not in ('table', 'calculated'):
                field['default_value'] = limit_text(request.form.get(f'field_default_{idx}', ''))

            if field_type == 'select':
                options_text = request.form.get(f'field_options_{idx}', '')
                field['options'] = [limit_text(o.strip(), 200) for o in options_text.split('\n') if o.strip()][:100]

            elif field_type == 'calculated':
                field['formula'] = field_formula
                try:
                    field['decimal_places'] = bounded_decimal_places(
                        request.form.get(f'field_decimal_{idx}', 2)
                    )
                except ValueError as e:
                    return str(e), 400
                field['depends_on'] = list(field_eval.get_calc_deps(field))

            elif field_type == 'table':
                columns = []
                col_idx = 0
                while True:
                    if col_idx >= MAX_TABLE_COLUMNS:
                        return f'{label} 的列数不能超过 {MAX_TABLE_COLUMNS}', 400
                    col_label = request.form.get(f'col_label_{idx}_{col_idx}')
                    if col_label is None:
                        break
                    col_label = col_label.strip()
                    if not col_label:
                        col_idx += 1
                        continue
                    col_type = request.form.get(f'col_type_{idx}_{col_idx}', 'text')
                    col_formula = request.form.get(f'col_formula_{idx}_{col_idx}', '').strip()
                    if col_type == 'calculated' and not col_formula:
                        col_type = 'text'
                    if col_type == 'calculated':
                        try:
                            field_eval.validate_formula(col_formula)
                        except field_eval.FormulaError as e:
                            return f'{col_label} 公式无效：{e}', 400
                    col_default = limit_text(request.form.get(f'col_default_{idx}_{col_idx}', ''), 2000)
                    col_key = helpers.safe_col_key(col_label, col_idx, {c['key'] for c in columns})
                    columns.append({
                        'key': col_key,
                        'label': col_label,
                        'field_type': col_type,
                        'formula': col_formula if col_type == 'calculated' else '',
                        'default_value': col_default if col_type != 'calculated' else '',
                    })
                    col_idx += 1
                field['columns'] = columns or [{'key': 'col_0', 'label': '内容', 'field_type': 'text', 'formula': ''}]

            fields.append(field)
            idx += 1

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

    @app.route('/templates')
    def list_templates():
        templates = template_def.list_templates()
        category_filter = request.args.get('category', '').strip()
        if category_filter:
            templates = [t for t in templates if t.get('category', '') == category_filter]
        return render_template('list.html', templates=templates)

    @app.route('/template/<name>')
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
            return f'加载模板失败：{str(e)}', 500

        sid = str(uuid.uuid4())
        helpers.save_session_data(sid, {
            'template_name': tpl.name,
            'template_path': path,
            'template_filename': os.path.basename(path),
            'stored_name': tpl.data.get('source_docx', ''),
            'step': 'editor',
        })
        session['sid'] = sid

        return render_template(
            'editor.html',
            fields=tpl.data['fields'],
            field_count=tpl.field_count,
            template_name=tpl.name,
        )

    @app.route('/template/<name>/preview', methods=['POST'])
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
            return f'加载模板失败：{e}', 500

        fields = tpl.data.get('fields', [])
        field_values = {}
        for f in fields:
            key = f['key']
            if f.get('field_type') == 'table':
                columns = f.get('columns', [])
                rows = []
                for _ in range(2):
                    row = {col['key']: f'[{col["label"]}]' for col in columns}
                    rows.append(row)
                field_values[key] = rows
            else:
                field_values[key] = f.get('default_value', '') or f.get('label', key)

        source_docx = tpl.data.get('source_docx', '')
        output_path = os.path.join(helpers.OUTPUT_FOLDER, f'preview_{uuid.uuid4().hex[:8]}.docx')

        if source_docx:
            try:
                template_path = helpers.safe_uploaded_docx_path(source_docx)
            except ValueError as e:
                return str(e), 400
            if not os.path.exists(template_path):
                return '模板源文件不存在', 404
            doc = Document(template_path)
            ordered_fields = helpers.docx_write_order(fields)
            for field in ordered_fields:
                ftype = field.get('field_type')
                key = field.get('key')
                location = field.get('location', {})
                if ftype == 'table':
                    docx_builder.apply_table_field(doc, field, field_values.get(key, []))
                else:
                    docx_builder.apply_text_field(doc, location, field_values.get(key, ''), field.get('label', ''), key)
            doc.save(output_path)
        else:
            docx_builder.generate_from_scratch(tpl.data, field_values, output_path)

        return send_file(
            output_path,
            as_attachment=True,
            download_name=f'{tpl.name}_预览.docx',
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )

    @app.route('/template/<filename>/delete', methods=['POST'])
    def template_delete(filename):
        template_def.delete_template(os.path.basename(filename))
        return redirect(url_for('list_templates'))

    @app.route('/template/<filename>/copy', methods=['POST'])
    def template_copy(filename):
        new_filename = template_def.copy_template(filename)
        if not new_filename:
            return '复制模板失败', 500
        get_logger().info('Copied template %s -> %s', filename, new_filename)
        return redirect(url_for('list_templates'))

    @app.route('/template/<name>/versions')
    def template_versions(name):
        if name.endswith('.contract-template'):
            template_name = name[:-len('.contract-template')]
        else:
            template_name = name
        versions = template_def.list_versions(template_name)
        return render_template('versions.html',
            template_name=template_name, versions=versions)

    @app.route('/template/<name>/versions/<version_filename>/restore', methods=['POST'])
    def template_version_restore(name, version_filename):
        template_name = name[:-len('.contract-template')] if name.endswith('.contract-template') else name
        try:
            template_def.restore_version(template_name, version_filename)
        except FileNotFoundError as e:
            return str(e), 404
        return redirect(url_for('list_templates'))

    @app.route('/template-defaults', methods=['POST'])
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
            return jsonify({'success': False, 'message': f'加载模板失败：{e}'}), 500

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
                field['default_value'] = limit_text(request.form.get(f'field_{i}', ''))

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
                pass

        try:
            tpl.save(template_path_data)
        except Exception as e:
            return jsonify({'success': False, 'message': f'保存模板失败：{e}'}), 500

        return jsonify({
            'success': True,
            'message': '预制内容已保存到模板',
            'warnings': warnings_list,
        })
