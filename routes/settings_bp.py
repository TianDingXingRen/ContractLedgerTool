"""System settings routes: autostart toggle, diagnostics, session reset."""

import os
import platform
import sys

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from core.maintenance_gate import maintenance_gate

import ledger_store
import template_def
from config import config as app_config
from runtime.flask_paths import current_runtime_paths
from services import data_protection_service, handover_service
from services.handover_archive import MAX_FULL_PACKAGE_ARCHIVE_BYTES
from utils.autostart import (
    autostart_status,
    disable_autostart,
    enable_autostart,
)
from utils.errors import wants_json, GENERIC_ERROR
from utils.logger import get_logger


def _autostart_json(enabled=None, error=''):
    if enabled is None:
        status = dict(autostart_status())
    else:
        # Enabling/disabling already completed the expensive PowerShell
        # operation. Do not immediately launch a second status query.
        status = {
            'enabled': bool(enabled),
            'supported': os.name == 'nt',
            'description': '已开启' if enabled else '未开启',
            'source': 'updated',
        }
    payload = {
        'success': not bool(error),
        'enabled': bool(status.get('enabled')),
        'supported': bool(status.get('supported')),
        'label': '开' if status.get('enabled') else '关',
        'description': status.get('description', ''),
        'source': status.get('source', 'none'),
        'message': error,
    }
    return jsonify(payload), (500 if error else 200)


def _diagnostics_payload(include_autostart=True):
    paths = current_runtime_paths()
    log_path = os.path.join(str(paths.logs_dir), 'app.log')
    if include_autostart:
        autostart = autostart_status()
    else:
        autostart = {
            'enabled': False,
            'supported': os.name == 'nt',
            'description': '检测中',
            'task_state': '',
            'startup_path': '',
            'message': '',
        }
    try:
        template_count = len(template_def.list_templates())
    except Exception as e:
        template_count = -1
        get_logger().warning('诊断页无法获取模板数量：%s', e)
    try:
        contract_total = ledger_store.get_contract_stats().get('total', 0)
    except Exception as e:
        contract_total = -1
        get_logger().warning('诊断页无法获取合同统计：%s', e)
    backups = ledger_store.list_backups()
    generation_integrity = current_app.extensions[
        'contract_tool'
    ].generation_recovery.diagnostics()
    return {
        'app': {
            'python': sys.version.split()[0],
            # platform.platform() performs an expensive Windows probe on its
            # first call. The concise values below are sufficient here.
            'platform': f'{platform.system()} {platform.release()}',
            'host': current_app.config.get(
                'CONTRACT_TOOL_BIND_HOST', app_config.HOST
            ),
            'port': current_app.config.get(
                'CONTRACT_TOOL_BIND_PORT', app_config.PORT
            ),
            'debug': bool(app_config.DEBUG),
        },
        'paths': {
            'base': str(paths.base_dir),
            'templates': template_def.TEMPLATES_DIR,
            'uploads': str(paths.uploads_dir),
            'output': str(paths.output_dir),
            'sessions': str(paths.sessions_dir),
            'database': ledger_store.DB_PATH,
            'log': log_path,
        },
        'counts': {
            'templates': template_count,
            'contracts': contract_total,
            'backups': len(backups),
        },
        'autostart': autostart,
        'data_protection': data_protection_service.data_protection_status(
            current_app.extensions['runtime_paths']
        ),
        'generation_integrity': generation_integrity,
    }


def _known_folder(key):
    paths = current_runtime_paths()
    folders = {
        'data': ledger_store.DATA_DIR,
        'logs': str(paths.logs_dir),
        'output': str(paths.output_dir),
        'backups': ledger_store.BACKUP_DIR,
    }
    if key not in folders:
        raise ValueError('目录类型无效')
    path = os.path.abspath(folders[key])
    os.makedirs(path, exist_ok=True)
    return path


def _open_folder(path):
    if os.name == 'nt':
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        raise RuntimeError('当前系统不支持从网页打开目录')


def _register_data_protection_routes(bp):
    @bp.route('/data-protection/enable', methods=['POST'])
    def data_protection_enable():
        if request.form.get('acknowledge_recovery') != '1':
            message = '请先确认已了解 EFS 私钥丢失会导致数据无法恢复'
            if wants_json():
                return jsonify({'success': False, 'message': message}), 400
            return redirect(url_for('settings.diagnostics', protection_error=message))
        try:
            with maintenance_gate.exclusive():
                ledger_store.close_connections()
                report = data_protection_service.enable_data_protection(
                    current_app.extensions['runtime_paths']
            )
            if not report['success']:
                if report.get('rollback_errors'):
                    message = (
                        f"EFS 启用失败且回滚不完整，{len(report['rollback_errors'])} 项需人工处理；"
                        '请立即查看日志'
                    )
                else:
                    message = f"EFS 启用失败，已回滚 {report.get('rolled_back', 0)} 项"
                get_logger().warning('EFS 部分启用，错误项已写入内部报告')
                if wants_json():
                    return jsonify({'success': False, 'message': message}), 400
                return redirect(url_for('settings.diagnostics', protection_error=message))
            message = f"EFS 已启用，共加密 {report['encrypted']} 个文件/目录"
            if wants_json():
                return jsonify({
                    'success': True,
                    'message': message,
                    'encrypted': int(report.get('encrypted', 0)),
                })
            return redirect(url_for('settings.diagnostics', protection_message=message))
        except Exception:
            get_logger().error('启用本地数据保护失败', exc_info=True)
            message = '本地数据保护失败，请查看日志'
            if wants_json():
                return jsonify({'success': False, 'message': message}), 400
            return redirect(url_for('settings.diagnostics', protection_error=message))


def register(app):
    bp = Blueprint('settings', __name__)
    _register_data_protection_routes(bp)
    @bp.route('/api/autostart/status')
    def autostart_status_api():
        return _autostart_json()

    @bp.route('/autostart/enable', methods=['POST'])
    def autostart_enable():
        try:
            enable_autostart()
            if wants_json():
                return _autostart_json(enabled=True)
            return redirect(url_for('contracts.index'))
        except Exception as e:
            get_logger().error('开启自启动失败: %s', e, exc_info=True)
            if wants_json():
                return _autostart_json(error='开启自启动失败')
            return redirect(url_for('contracts.index', autostart_error='开启自启动失败'))

    @bp.route('/autostart/disable', methods=['POST'])
    def autostart_disable():
        try:
            disable_autostart()
            if wants_json():
                return _autostart_json(enabled=False)
            return redirect(url_for('contracts.index'))
        except Exception as e:
            get_logger().error('关闭自启动失败: %s', e, exc_info=True)
            if wants_json():
                return _autostart_json(error='关闭自启动失败')
            return redirect(url_for('contracts.index', autostart_error='关闭自启动失败'))

    @bp.route('/diagnostics')
    def diagnostics():
        return render_template(
            'diagnostics.html',
            diagnostics=_diagnostics_payload(include_autostart=False),
        )

    @bp.route('/api/diagnostics')
    def api_diagnostics():
        return jsonify(_diagnostics_payload())

    @bp.route('/diagnostics/open-folder', methods=['POST'])
    def diagnostics_open_folder():
        key = request.form.get('folder', '').strip()
        try:
            path = _known_folder(key)
            _open_folder(path)
            return jsonify({'success': True, 'path': path})
        except Exception as e:
            get_logger().error('打开文件夹失败: %s', e, exc_info=True)
            return jsonify({'success': False, 'message': GENERIC_ERROR}), 400

    @bp.route('/backups')
    def backups():
        return render_template(
            'backups.html',
            backups=ledger_store.list_backups(),
            full_packages=handover_service.list_full_backup_packages(),
            handover_owners=handover_service.list_handover_owners(), full_backup_max_archive_bytes=MAX_FULL_PACKAGE_ARCHIVE_BYTES,
        )

    @bp.route('/backups/create', methods=['POST'])
    def backup_create():
        try:
            backup = ledger_store.create_backup()
            if wants_json():
                return jsonify({'success': True, 'backup': backup})
            return redirect(url_for('settings.backups'))
        except Exception as e:
            get_logger().error('备份操作失败: %s', e, exc_info=True)
            if wants_json():
                return jsonify({'success': False, 'message': GENERIC_ERROR}), 400
            return redirect(url_for('settings.backups', error=GENERIC_ERROR))

    @bp.route('/backups/<filename>/restore', methods=['POST'])
    def backup_restore(filename):
        try:
            ledger_store.restore_backup(filename)
            if wants_json():
                return jsonify({'success': True})
            return redirect(url_for('settings.backups'))
        except Exception as e:
            get_logger().error('备份操作失败: %s', e, exc_info=True)
            if wants_json():
                return jsonify({'success': False, 'message': GENERIC_ERROR}), 400
            return redirect(url_for('settings.backups', error=GENERIC_ERROR))

    @bp.route('/backups/<filename>/download')
    def backup_download(filename):
        try:
            path = ledger_store.backup_path(filename)
        except FileNotFoundError:
            abort(404)
        return send_file(
            path,
            as_attachment=True,
            download_name=os.path.basename(path),
            mimetype='application/octet-stream',
        )

    @bp.route('/backups/full/create', methods=['POST'])
    def full_backup_create():
        try:
            package = handover_service.create_full_backup_package(
                label=request.form.get('label', 'handover'),
                paths=current_runtime_paths(),
            )
            if wants_json():
                return jsonify({'success': True, 'package': package})
            return redirect(url_for('settings.backups', message='完整数据包已生成'))
        except Exception as e:
            get_logger().error('完整数据包生成失败: %s', e, exc_info=True)
            if wants_json():
                return jsonify({'success': False, 'message': GENERIC_ERROR}), 400
            return redirect(url_for('settings.backups', error=GENERIC_ERROR))

    @bp.route('/backups/full/upload', methods=['POST'])
    def full_backup_upload():
        try:
            package = handover_service.upload_full_backup_package(
                request.files.get('file'),
                paths=current_runtime_paths(),
            )
            if wants_json():
                return jsonify({'success': True, 'package': package})
            return redirect(url_for('settings.backups', message='完整数据包已上传并通过校验'))
        except ValueError:
            get_logger().warning('完整数据包上传校验失败', exc_info=True)
            message = '完整数据包校验失败'
            if wants_json():
                return jsonify({'success': False, 'message': message}), 400
            return redirect(url_for('settings.backups', error=message))

    @bp.route('/backups/full/<filename>/download')
    def full_backup_download(filename):
        try:
            path = handover_service.full_package_path(filename)
        except FileNotFoundError:
            abort(404)
        return send_file(
            path,
            as_attachment=True,
            download_name=os.path.basename(path),
            mimetype='application/zip',
        )

    @bp.route('/backups/full/<filename>/restore', methods=['POST'])
    def full_backup_restore(filename):
        try:
            result = handover_service.restore_full_backup_package(
                filename,
                paths=current_runtime_paths(),
            )
            if wants_json():
                return jsonify({'success': True, 'rollback': result['rollback']})
            return redirect(url_for('settings.backups', message='完整数据包已恢复，恢复前数据已自动留存回滚包'))
        except ValueError:
            get_logger().warning('完整数据包恢复校验失败', exc_info=True)
            message = '完整数据包恢复校验失败'
            if wants_json():
                return jsonify({'success': False, 'message': message}), 400
            return redirect(url_for('settings.backups', error=message))
        except Exception as e:
            get_logger().error('完整数据包恢复失败: %s', e, exc_info=True)
            if wants_json():
                return jsonify({'success': False, 'message': GENERIC_ERROR}), 400
            return redirect(url_for('settings.backups', error=GENERIC_ERROR))

    @bp.route('/backups/handover/export', methods=['POST'])
    def handover_export():
        owner = request.form.get('owner', '').strip()
        include_closed = request.form.get('include_closed') == '1'
        try:
            result = handover_service.export_handover_checklist(
                str(current_runtime_paths().output_dir),
                owner,
                include_closed=include_closed,
                paths=current_runtime_paths(),
            )
            if wants_json():
                return jsonify({'success': True, 'export': {
                    'filename': result['filename'],
                    'download_name': result['download_name'],
                    'summary': result['summary'],
                }})
            return send_from_directory(
                os.path.abspath(current_runtime_paths().output_dir),
                os.path.basename(result['filename']),
                as_attachment=True,
                download_name=result['download_name'],
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            )
        except ValueError:
            get_logger().warning('交接清单参数无效', exc_info=True)
            message = '交接清单参数无效'
            if wants_json():
                return jsonify({'success': False, 'message': message}), 400
            return redirect(url_for('settings.backups', error=message))
        except Exception as e:
            get_logger().error('交接清单导出失败: %s', e, exc_info=True)
            if wants_json():
                return jsonify({'success': False, 'message': GENERIC_ERROR}), 400
            return redirect(url_for('settings.backups', error=GENERIC_ERROR))

    @bp.route('/reset', methods=['POST'])
    def reset():
        session.pop('sid', None)
        return redirect(url_for('contracts.index'))

    app.register_blueprint(bp)
