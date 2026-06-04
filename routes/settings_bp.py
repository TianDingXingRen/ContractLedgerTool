"""System settings routes: autostart toggle, diagnostics, session reset."""

import os
import platform
import sys

from flask import request, redirect, url_for, session, jsonify, render_template, send_file, abort

import ledger_store
import pdf_exporter
import template_def
from config import config as app_config
from utils import helpers
from utils.errors import wants_json
from utils.logger import get_logger


def _autostart_json(enabled=None, error=''):
    status = helpers.autostart_status()
    if enabled is not None:
        status['enabled'] = enabled
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


def _tail_lines(path, max_lines=40):
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read().splitlines()[-max_lines:]
    except OSError:
        return []


def _diagnostics_payload():
    log_path = os.path.join(helpers.BASE_DIR or '', 'logs', 'app.log')
    autostart = helpers.autostart_status()
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
    return {
        'app': {
            'python': sys.version.split()[0],
            'platform': platform.platform(),
            'host': app_config.HOST,
            'port': app_config.PORT,
            'debug': bool(app_config.DEBUG),
        },
        'paths': {
            'base': helpers.BASE_DIR,
            'templates': template_def.TEMPLATES_DIR,
            'uploads': helpers.UPLOAD_FOLDER,
            'output': helpers.OUTPUT_FOLDER,
            'sessions': helpers.SESSION_FOLDER,
            'database': ledger_store.DB_PATH,
            'log': log_path,
        },
        'counts': {
            'templates': template_count,
            'contracts': contract_total,
            'backups': len(backups),
        },
        'autostart': autostart,
        'pdf': pdf_exporter.diagnose_environment(),
        'recent_logs': _tail_lines(log_path),
    }


def _known_folder(key):
    folders = {
        'data': ledger_store.DATA_DIR,
        'logs': os.path.join(helpers.BASE_DIR or '', 'logs'),
        'output': helpers.OUTPUT_FOLDER,
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


def register(app):
    @app.route('/autostart/enable', methods=['POST'])
    def autostart_enable():
        try:
            helpers.enable_autostart()
            if wants_json():
                return _autostart_json(enabled=True)
            return redirect(url_for('index'))
        except Exception as e:
            if wants_json():
                return _autostart_json(error=f'开启自启动失败：{e}')
            return redirect(url_for('index', autostart_error=f'开启自启动失败：{e}'))

    @app.route('/autostart/disable', methods=['POST'])
    def autostart_disable():
        try:
            helpers.disable_autostart()
            if wants_json():
                return _autostart_json(enabled=False)
            return redirect(url_for('index'))
        except Exception as e:
            if wants_json():
                return _autostart_json(error=f'关闭自启动失败：{e}')
            return redirect(url_for('index', autostart_error=f'关闭自启动失败：{e}'))

    @app.route('/diagnostics')
    def diagnostics():
        return render_template('diagnostics.html', diagnostics=_diagnostics_payload())

    @app.route('/api/diagnostics')
    def api_diagnostics():
        return jsonify(_diagnostics_payload())

    @app.route('/diagnostics/open-folder', methods=['POST'])
    def diagnostics_open_folder():
        key = request.form.get('folder', '').strip()
        try:
            path = _known_folder(key)
            _open_folder(path)
            return jsonify({'success': True, 'path': path})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400

    @app.route('/backups')
    def backups():
        return render_template('backups.html', backups=ledger_store.list_backups())

    @app.route('/backups/create', methods=['POST'])
    def backup_create():
        try:
            backup = ledger_store.create_backup()
            if wants_json():
                return jsonify({'success': True, 'backup': backup})
            return redirect(url_for('backups'))
        except Exception as e:
            if wants_json():
                return jsonify({'success': False, 'message': str(e)}), 400
            return redirect(url_for('backups', error=str(e)))

    @app.route('/backups/<filename>/restore', methods=['POST'])
    def backup_restore(filename):
        try:
            ledger_store.restore_backup(filename)
            if wants_json():
                return jsonify({'success': True})
            return redirect(url_for('backups'))
        except Exception as e:
            if wants_json():
                return jsonify({'success': False, 'message': str(e)}), 400
            return redirect(url_for('backups', error=str(e)))

    @app.route('/backups/<filename>/download')
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

    @app.route('/reset')
    def reset():
        session.pop('sid', None)
        return redirect(url_for('index'))
