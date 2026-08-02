"""Windows 自启动管理模块 — 从 helpers.py 拆分"""

import os
import sys
import subprocess
import threading
import time as _time

from utils.logger import get_logger
from utils.subprocess_utils import hidden_window_kwargs

# 模块级变量，由调用方在 app.py 初始化时设置
BASE_DIR = None
AUTOSTART_TASK_NAME = 'ContractLedgerTool'
AUTOSTART_LAUNCHER_NAME = 'ContractLedgerTool_Autostart.vbs'
AUTOSTART_LEGACY_LAUNCHER_NAMES = ('ContractLedgerTool.vbs',)

_autostart_cache = None
_autostart_cache_time = 0
_autostart_lock = threading.Lock()


# ── Internal helpers ──

def _ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def _run_powershell(script):
    return subprocess.run(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        timeout=30,
        **hidden_window_kwargs(),
    )


def _autostart_launch_parts():
    """返回 (可执行文件路径, 参数字符串)。

    对 PyInstaller 打包的 EXE：直接返回 EXE 路径 + --no-browser。
    对 Python 源码部署：优先使用 start.ps1 包装脚本（隐藏窗口），
    回退到直接启动 python app.py。
    """
    if BASE_DIR is None:
        raise RuntimeError('BASE_DIR 未初始化，请先调用 init_runtime()')

    # ── PyInstaller 单文件 EXE 模式 ──
    # 通过 PowerShell 启动 EXE 以隐藏控制台窗口
    if getattr(sys, 'frozen', False):
        powerShell = os.path.join(
            os.environ.get('SystemRoot', 'C:\\Windows'),
            'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe',
        )
        exe_path = sys.executable
        return powerShell, (
            f'-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden '
            f'-Command "Start-Process -FilePath {_ps_quote(exe_path)} '
            f'-ArgumentList \'--no-browser\' -WindowStyle Hidden"'
        )

    # ── Python 源码部署模式 ──
    powerShell = os.path.join(
        os.environ.get('SystemRoot', 'C:\\Windows'),
        'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe',
    )
    # 优先查找根目录的 start.ps1（安装版），再查找 installer_assets 中的（源码版）
    start_ps1_candidates = [
        os.path.join(BASE_DIR, 'start.ps1'),
        os.path.join(BASE_DIR, 'installer_assets', 'start.ps1'),
    ]
    start_ps1 = None
    for candidate in start_ps1_candidates:
        if os.path.isfile(candidate):
            start_ps1 = candidate
            break
    if start_ps1:
        return powerShell, (
            f'-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden '
            f'-File "{start_ps1}" -NoBrowser'
        )
    python_exe = sys.executable
    app_py = os.path.join(BASE_DIR, 'app.py')
    if not os.path.isfile(app_py):
        raise RuntimeError(f'自启动配置失败：找不到 app.py (BASE_DIR={BASE_DIR})')
    return powerShell, (
        f'-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden '
        f'-Command "& {_ps_quote(python_exe)} {_ps_quote(app_py)} '
        f'--host 127.0.0.1 --port 5000 --no-browser"'
    )


def _autostart_command_line():
    exe, args = _autostart_launch_parts()
    return f'"{exe}" {args}'.strip()


# ── Startup folder helpers ──

def _startup_folder():
    appdata = os.environ.get('APPDATA')
    if not appdata:
        raise RuntimeError('未找到当前用户的 APPDATA 目录')
    return os.path.join(appdata, 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')


def _startup_launcher_path():
    return os.path.join(_startup_folder(), AUTOSTART_LAUNCHER_NAME)


def _legacy_startup_launcher_paths():
    folder = _startup_folder()
    return [os.path.join(folder, name) for name in AUTOSTART_LEGACY_LAUNCHER_NAMES]


def _vbs_escape(value):
    return str(value).replace('"', '""')


def _startup_launcher_matches(path):
    try:
        with open(path, 'r', encoding='utf-16') as f:
            content = f.read()
    except Exception:
        return False
    command = _autostart_command_line()
    return command in content or _vbs_escape(command) in content


def _write_startup_launcher():
    folder = _startup_folder()
    os.makedirs(folder, exist_ok=True)
    _remove_legacy_startup_launchers()
    path = _startup_launcher_path()
    command = _autostart_command_line()
    content = (
        f"' ContractLedgerTool auto-start (via start.ps1 -NoBrowser)\n"
        f"' Command: {command}\n"
        'Set shell = CreateObject("WScript.Shell")\n'
        f'shell.CurrentDirectory = "{_vbs_escape(BASE_DIR)}"\n'
        f'shell.Run "{_vbs_escape(command)}", 0, False\n'
    )
    with open(path, 'w', encoding='utf-16') as f:
        f.write(content)
    return path


def _remove_legacy_startup_launchers():
    removed = False
    for path in _legacy_startup_launcher_paths():
        if os.path.exists(path):
            os.remove(path)
            removed = True
    return removed


def _remove_startup_launcher():
    removed = False
    for path in [_startup_launcher_path(), *_legacy_startup_launcher_paths()]:
        if os.path.exists(path):
            os.remove(path)
            removed = True
    return removed


# ── Public API ──

def autostart_status():
    global _autostart_cache, _autostart_cache_time
    now = _time.time()
    with _autostart_lock:
        if _autostart_cache is not None and (now - _autostart_cache_time) < 30:
            return _autostart_cache

    if os.name != 'nt':
        result = {
            'supported': False,
            'enabled': False,
            'source': 'none',
            'description': '当前系统不支持此功能',
            'message': '当前系统不支持此功能',
        }
        with _autostart_lock:
            _autostart_cache = result
            _autostart_cache_time = now
        return result

    startup_path = ''
    startup_enabled = False
    startup_valid = False
    startup_error = ''
    try:
        startup_path = _startup_launcher_path()
        for candidate in [startup_path, *_legacy_startup_launcher_paths()]:
            if os.path.isfile(candidate):
                startup_path = candidate
                startup_enabled = True
                startup_valid = _startup_launcher_matches(candidate)
                break
    except Exception:
        get_logger().warning(
            '无法读取自启动文件夹状态',
            exc_info=True,
        )
        startup_error = '无法读取启动文件夹状态'
    script = (
        f"$task = Get-ScheduledTask -TaskName {_ps_quote(AUTOSTART_TASK_NAME)} -ErrorAction SilentlyContinue; "
        "if ($task) { Write-Output $task.State }"
    )
    task_state = ''
    task_enabled = False
    task_error = ''
    try:
        result = _run_powershell(script)
    except Exception:
        get_logger().warning(
            '无法读取计划任务状态',
            exc_info=True,
        )
        task_error = '无法读取计划任务状态'
        result = None
    if result is not None:
        if result.returncode == 0:
            task_state = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ''
            task_enabled = task_state.lower() in {'ready', 'running'}
        else:
            get_logger().warning(
                '计划任务状态查询失败，退出码: %s',
                result.returncode,
            )
            task_error = '无法读取计划任务状态'

    enabled_sources = []
    if task_enabled:
        enabled_sources.append('计划任务')
    if startup_enabled and startup_valid:
        enabled_sources.append('启动文件夹')
    if enabled_sources:
        description = '、'.join(enabled_sources) + '已启用'
    elif task_state:
        description = f'计划任务状态为 {task_state}'
    elif startup_enabled:
        description = '启动文件夹脚本存在但路径已失效'
    else:
        description = '未开启'
    with _autostart_lock:
        _autostart_cache = {
            'supported': True,
            'enabled': bool(enabled_sources),
            'source': '+'.join(enabled_sources) or 'none',
            'description': description,
            'startup_enabled': startup_enabled,
            'startup_valid': startup_valid,
            'startup_path': startup_path,
            'task_enabled': task_enabled,
            'task_state': task_state,
            'message': task_error or startup_error,
        }
        _autostart_cache_time = now
    return _autostart_cache


def _verify_scheduled_task():
    """验证计划任务已创建并可运行。返回 (exists, state)"""
    script = (
        f"$task = Get-ScheduledTask -TaskName {_ps_quote(AUTOSTART_TASK_NAME)} -ErrorAction SilentlyContinue; "
        "if ($task) { Write-Output $task.State } else { Write-Output 'NOT_FOUND' }"
    )
    try:
        result = _run_powershell(script)
        if result.returncode == 0:
            state = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ''
            return state != 'NOT_FOUND', state
    except Exception:
        get_logger().debug('验证计划任务状态失败', exc_info=True)
    return False, ''


def enable_autostart():
    global _autostart_cache, _autostart_cache_time
    with _autostart_lock:
        _autostart_cache = None
        _autostart_cache_time = 0
    if os.name != 'nt':
        raise RuntimeError('当前系统不支持此功能')
    exe, args = _autostart_launch_parts()
    script = f"""
$Action = New-ScheduledTaskAction -Execute {_ps_quote(exe)} -Argument {_ps_quote(args)} -WorkingDirectory {_ps_quote(BASE_DIR)}
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
Register-ScheduledTask -TaskName {_ps_quote(AUTOSTART_TASK_NAME)} -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description 'Contract Ledger Tool auto start' -Force | Out-Null
"""
    try:
        result = _run_powershell(script)
    except subprocess.TimeoutExpired:
        get_logger().error('自启动计划任务注册超时（30秒），PowerShell 无响应')
        raise RuntimeError('自启动设置超时，请检查系统 PowerShell 是否正常')
    if result.returncode == 0:
        exists, state = _verify_scheduled_task()
        if exists:
            _remove_legacy_startup_launchers()
            get_logger().info('计划任务自启动已创建，状态：%s', state)
            return 'task'
        get_logger().warning('计划任务创建命令成功但验证失败：%s', result.stderr.strip() or result.stdout.strip())
        return 'task'
    else:
        get_logger().warning('计划任务创建失败（将使用启动文件夹回退）：%s',
                            result.stderr.strip() or result.stdout.strip() or '未知错误')

    # 回退：使用启动文件夹 VBS 脚本
    try:
        _write_startup_launcher()
        if not _startup_launcher_matches(_startup_launcher_path()):
            raise RuntimeError('启动脚本写入后验证不通过')
        get_logger().info('启动文件夹自启动已创建')
        return 'startup'
    except Exception as e:
        get_logger().error('自启动设置失败：%s', e)
        raise RuntimeError(f'自启动设置失败：{e}')


def disable_autostart():
    global _autostart_cache, _autostart_cache_time
    with _autostart_lock:
        _autostart_cache = None
        _autostart_cache_time = 0
    if os.name != 'nt':
        raise RuntimeError('当前系统不支持此功能')
    script = f"""
$task = Get-ScheduledTask -TaskName {_ps_quote(AUTOSTART_TASK_NAME)} -ErrorAction SilentlyContinue
if ($task) {{
    Unregister-ScheduledTask -TaskName {_ps_quote(AUTOSTART_TASK_NAME)} -Confirm:$false
}}
exit 0
"""
    task_removed = False
    task_error = ''
    try:
        result = _run_powershell(script)
        if result.returncode == 0:
            task_removed = True
        else:
            task_error = result.stderr.strip() or result.stdout.strip() or '未知错误'
    except subprocess.TimeoutExpired:
        get_logger().error('自启动计划任务移除超时')
        task_error = 'PowerShell 超时'

    startup_removed = _remove_startup_launcher()

    # 只要启动文件夹清理成功（这是实际生效的自启方式），就不报错
    # 计划任务移除失败通常是任务本就不存在，属于正常情况
    if startup_removed or task_removed:
        return
    if task_error:
        raise RuntimeError(f'自启动关闭失败：{task_error}')
    raise RuntimeError('自启动关闭失败：未找到任何自启动项')
