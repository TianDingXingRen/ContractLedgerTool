"""Application configuration loaded from config.json and environment variables."""

import copy
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


CONFIG_DEFAULTS = {
    "HOST": "127.0.0.1",
    "PORT": 5000,
    "DEBUG": False,
    "ALLOW_REMOTE": False,
    "MAX_CONTENT_LENGTH_MB": 50,
    "CLEANUP_DAYS": 7,
    "LOG_LEVEL": "INFO",
    "RATE_LIMITS": {
        "/generate": [10, 60],
        "/generate-batch": [5, 60],
        "/template/upload-style": [20, 60],
    },
    "RATE_LIMIT_DEFAULT": [30, 60],
    "RATE_LIMIT_GLOBAL": [120, 60],
    "RATE_LIMIT_LOCALHOST": [1000, 60],
    "SESSION_TTL_HOURS": 168,
    "OUTPUT_CLEANUP_DAYS": 7,
}


def ensure_config_file(base_dir=None):
    """若 config.json 不存在，自动生成有效的 JSON 配置文件"""
    config_path = os.path.join(base_dir or BASE_DIR, 'config.json')
    if os.path.isfile(config_path):
        return
    defaults = dict(CONFIG_DEFAULTS)
    defaults['_comment'] = '合同生成工具配置文件。修改后重启即生效，环境变量前缀 CT_ 可覆盖对应项。'
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(defaults, f, ensure_ascii=False, indent=2)
        f.write('\n')


class Config:
    HOST = '127.0.0.1'
    PORT = 5000
    DEBUG = False
    ALLOW_REMOTE = False
    REMOTE_ACCESS_TOKEN = ''
    MAX_CONTENT_LENGTH_MB = 50
    CLEANUP_DAYS = 7
    RATE_LIMITS = {
        '/generate': (10, 60),
        '/generate-batch': (5, 60),
        '/template/upload-style': (20, 60),
    }
    RATE_LIMIT_DEFAULT = (30, 60)
    RATE_LIMIT_GLOBAL = (120, 60)       # 单个 IP 全局限制：(N次, M秒)
    RATE_LIMIT_LOCALHOST = (1000, 60)   # 本地回环地址放松限制
    SESSION_TTL_HOURS = 168             # 会话过期时间（默认7天）
    OUTPUT_CLEANUP_DAYS = 7             # 临时文件清理天数
    LOG_LEVEL = 'INFO'

    def __init__(self, base_dir=None):
        self.base_dir = os.path.abspath(base_dir or BASE_DIR)
        self._reset_defaults()
        self._load_file()
        self._load_env()

    def _reset_defaults(self):
        """每次重新加载前恢复默认值，避免测试/多应用实例互相污染。"""
        for key, value in CONFIG_DEFAULTS.items():
            if key == 'RATE_LIMITS':
                setattr(self, key, {
                    path: tuple(limit) for path, limit in copy.deepcopy(value).items()
                })
            elif key.startswith('RATE_LIMIT_'):
                setattr(self, key, tuple(value))
            else:
                setattr(self, key, copy.deepcopy(value))
        self.REMOTE_ACCESS_TOKEN = ''

    def reload(self, base_dir=None):
        if base_dir is not None:
            self.base_dir = os.path.abspath(base_dir)
        self._reset_defaults()
        self._load_file()
        self._load_env()
        return self

    @staticmethod
    def _validate_int(val, min_val, max_val, label):
        """校验整数配置值在合法范围内。"""
        try:
            val = int(val)
        except (TypeError, ValueError):
            import logging
            logging.getLogger('contract_tool').warning('%s 值无效，使用默认值', label)
            return None
        if val < min_val or val > max_val:
            import logging
            logging.getLogger('contract_tool').warning(
                '%s 值 %d 超出范围 [%d, %d]，已限制在合法范围内', label, val, min_val, max_val)
            return max(min_val, min(max_val, val))
        return val

    _INT_BOUNDS = {
        'PORT': (1, 65535),
        'MAX_CONTENT_LENGTH_MB': (1, 500),
        'CLEANUP_DAYS': (1, 365),
        'SESSION_TTL_HOURS': (1, 8760),
        'OUTPUT_CLEANUP_DAYS': (1, 365),
    }

    _VALID_LOG_LEVELS = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}

    def _load_file(self):
        config_path = os.path.join(self.base_dir, 'config.json')
        if not os.path.isfile(config_path):
            return
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for key in ('HOST', 'PORT', 'DEBUG', 'ALLOW_REMOTE', 'MAX_CONTENT_LENGTH_MB',
                        'CLEANUP_DAYS', 'LOG_LEVEL', 'SESSION_TTL_HOURS',
                        'OUTPUT_CLEANUP_DAYS'):
                if key in data:
                    val = data[key]
                    if key in {'DEBUG', 'ALLOW_REMOTE'}:
                        # 统一转为 bool：JSON bool 已是 bool，字符串也需兼容
                        val = bool(val) if not isinstance(val, str) else val.lower() in ('1', 'true', 'yes')
                    elif key in self._INT_BOUNDS:
                        min_v, max_v = self._INT_BOUNDS[key]
                        val = self._validate_int(val, min_v, max_v, key)
                        if val is None:
                            continue
                    elif key == 'LOG_LEVEL':
                        val = str(val).upper()
                        if val not in self._VALID_LOG_LEVELS:
                            import logging
                            logging.getLogger('contract_tool').warning(
                                'LOG_LEVEL 值 "%s" 无效，使用默认值 INFO', val)
                            continue
                    setattr(self, key, val)
            if 'RATE_LIMITS' in data and isinstance(data['RATE_LIMITS'], dict):
                self.RATE_LIMITS.update({
                    k: tuple(v) for k, v in data['RATE_LIMITS'].items()
                    if isinstance(v, (list, tuple)) and len(v) == 2
                })
            if 'RATE_LIMIT_DEFAULT' in data:
                self.RATE_LIMIT_DEFAULT = tuple(data['RATE_LIMIT_DEFAULT'])
            if 'RATE_LIMIT_GLOBAL' in data:
                self.RATE_LIMIT_GLOBAL = tuple(data['RATE_LIMIT_GLOBAL'])
            if 'RATE_LIMIT_LOCALHOST' in data:
                self.RATE_LIMIT_LOCALHOST = tuple(data['RATE_LIMIT_LOCALHOST'])
        except (json.JSONDecodeError, TypeError, ValueError):
            import logging
            logging.getLogger('contract_tool').warning('config.json 解析失败，将使用默认配置')

    def _load_env(self):
        for key in ('HOST', 'PORT', 'DEBUG', 'ALLOW_REMOTE', 'MAX_CONTENT_LENGTH_MB',
                    'CLEANUP_DAYS', 'LOG_LEVEL', 'SESSION_TTL_HOURS',
                    'OUTPUT_CLEANUP_DAYS'):
            env_val = os.environ.get(f'CT_{key}')
            if env_val is None:
                continue
            if key in self._INT_BOUNDS:
                min_v, max_v = self._INT_BOUNDS[key]
                val = self._validate_int(env_val, min_v, max_v, f'CT_{key}')
                if val is not None:
                    setattr(self, key, val)
            elif key in {'DEBUG', 'ALLOW_REMOTE'}:
                setattr(self, key, env_val.lower() in ('1', 'true', 'yes'))
            elif key == 'LOG_LEVEL':
                val = env_val.upper()
                if val in self._VALID_LOG_LEVELS:
                    setattr(self, key, val)
                else:
                    import logging
                    logging.getLogger('contract_tool').warning(
                        '环境变量 CT_LOG_LEVEL 值 "%s" 无效，使用默认值', env_val)
            else:
                setattr(self, key, env_val)
        self.REMOTE_ACCESS_TOKEN = os.environ.get('CT_REMOTE_ACCESS_TOKEN', '').strip()


config = Config()
