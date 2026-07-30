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
    "TRUSTED_HOSTS": ["127.0.0.1", "localhost", "[::1]"],
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
    "GENERATION_HISTORY_DAYS": 30,
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
    TRUSTED_HOSTS = ['127.0.0.1', 'localhost', '[::1]']
    REMOTE_ACCESS_TOKEN = ''
    REMOTE_TLS_CERT = ''
    REMOTE_TLS_KEY = ''
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
    GENERATION_HISTORY_DAYS = 30        # 已完成生成任务日志保留天数
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
        self.REMOTE_TLS_CERT = ''
        self.REMOTE_TLS_KEY = ''

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
        'GENERATION_HISTORY_DAYS': (1, 3650),
    }

    _VALID_LOG_LEVELS = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
    _DEFAULT_TRUSTED_HOSTS = ('127.0.0.1', 'localhost', '[::1]')
    _RATE_LIMIT_BOUNDS = ((1, 100000), (1, 86400))

    @classmethod
    def _validate_rate_limit(cls, value, label, default):
        import logging

        logger = logging.getLogger('contract_tool')
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            logger.warning('%s 必须是 [最大请求数, 时间窗口秒数]，使用默认值', label)
            return tuple(default)
        result = []
        for index, (minimum, maximum) in enumerate(cls._RATE_LIMIT_BOUNDS):
            validated = cls._validate_int(
                value[index], minimum, maximum, f'{label}[{index}]'
            )
            if validated is None:
                logger.warning('%s 包含无效值，使用默认值', label)
                return tuple(default)
            result.append(validated)
        return tuple(result)

    @classmethod
    def _validate_trusted_hosts(cls, value):
        import logging

        logger = logging.getLogger('contract_tool')
        if isinstance(value, str):
            value = value.split(',')
        if not isinstance(value, (list, tuple)):
            logger.warning('TRUSTED_HOSTS 必须是主机名列表，使用本机默认值')
            value = []
        hosts = list(cls._DEFAULT_TRUSTED_HOSTS)
        for item in value:
            host = str(item or '').strip()
            if (
                not host
                or host == '*'
                or len(host) > 255
                or any(character.isspace() for character in host)
                or '://' in host
                or '/' in host
            ):
                logger.warning('忽略不安全的 TRUSTED_HOSTS 项: %r', item)
                continue
            if host not in hosts:
                hosts.append(host)
        return hosts

    def _load_file(self):
        config_path = os.path.join(self.base_dir, 'config.json')
        if not os.path.isfile(config_path):
            return
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for key in ('HOST', 'PORT', 'DEBUG', 'ALLOW_REMOTE', 'MAX_CONTENT_LENGTH_MB',
                        'CLEANUP_DAYS', 'LOG_LEVEL', 'SESSION_TTL_HOURS',
                        'OUTPUT_CLEANUP_DAYS', 'GENERATION_HISTORY_DAYS'):
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
            if 'TRUSTED_HOSTS' in data:
                self.TRUSTED_HOSTS = self._validate_trusted_hosts(data['TRUSTED_HOSTS'])
            if 'RATE_LIMITS' in data and isinstance(data['RATE_LIMITS'], dict):
                for path, value in data['RATE_LIMITS'].items():
                    path = str(path or '').strip()
                    if not path.startswith('/'):
                        continue
                    default = self.RATE_LIMITS.get(path, self.RATE_LIMIT_DEFAULT)
                    self.RATE_LIMITS[path] = self._validate_rate_limit(
                        value, f'RATE_LIMITS[{path}]', default
                    )
            if 'RATE_LIMIT_DEFAULT' in data:
                self.RATE_LIMIT_DEFAULT = self._validate_rate_limit(
                    data['RATE_LIMIT_DEFAULT'], 'RATE_LIMIT_DEFAULT',
                    self.RATE_LIMIT_DEFAULT,
                )
            if 'RATE_LIMIT_GLOBAL' in data:
                self.RATE_LIMIT_GLOBAL = self._validate_rate_limit(
                    data['RATE_LIMIT_GLOBAL'], 'RATE_LIMIT_GLOBAL',
                    self.RATE_LIMIT_GLOBAL,
                )
            if 'RATE_LIMIT_LOCALHOST' in data:
                self.RATE_LIMIT_LOCALHOST = self._validate_rate_limit(
                    data['RATE_LIMIT_LOCALHOST'], 'RATE_LIMIT_LOCALHOST',
                    self.RATE_LIMIT_LOCALHOST,
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            import logging
            logging.getLogger('contract_tool').warning('config.json 解析失败，将使用默认配置')

    def _load_env(self):
        for key in ('HOST', 'PORT', 'DEBUG', 'ALLOW_REMOTE', 'MAX_CONTENT_LENGTH_MB',
                    'CLEANUP_DAYS', 'LOG_LEVEL', 'SESSION_TTL_HOURS',
                    'OUTPUT_CLEANUP_DAYS', 'GENERATION_HISTORY_DAYS'):
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
        trusted_hosts = os.environ.get('CT_TRUSTED_HOSTS')
        if trusted_hosts is not None:
            self.TRUSTED_HOSTS = self._validate_trusted_hosts(trusted_hosts)
        self.REMOTE_ACCESS_TOKEN = os.environ.get('CT_REMOTE_ACCESS_TOKEN', '').strip()
        self.REMOTE_TLS_CERT = os.environ.get('CT_REMOTE_TLS_CERT', '').strip()
        self.REMOTE_TLS_KEY = os.environ.get('CT_REMOTE_TLS_KEY', '').strip()


config = Config()
