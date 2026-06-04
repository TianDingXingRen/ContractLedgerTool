"""Application configuration loaded from config.json and environment variables."""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


CONFIG_DEFAULTS = {
    "HOST": "127.0.0.1",
    "PORT": 5000,
    "DEBUG": False,
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


def ensure_config_file():
    """若 config.json 不存在，自动生成有效的 JSON 配置文件"""
    config_path = os.path.join(BASE_DIR, 'config.json')
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

    def __init__(self):
        self._load_file()
        self._load_env()

    def _load_file(self):
        config_path = os.path.join(BASE_DIR, 'config.json')
        if not os.path.isfile(config_path):
            return
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for key in ('HOST', 'PORT', 'DEBUG', 'MAX_CONTENT_LENGTH_MB',
                        'CLEANUP_DAYS', 'LOG_LEVEL', 'SESSION_TTL_HOURS',
                        'OUTPUT_CLEANUP_DAYS'):
                if key in data:
                    val = data[key]
                    if key == 'DEBUG':
                        # 统一转为 bool：JSON bool 已是 bool，字符串也需兼容
                        val = bool(val) if not isinstance(val, str) else val.lower() in ('1', 'true', 'yes')
                    setattr(self, key, val)
            if 'RATE_LIMITS' in data and isinstance(data['RATE_LIMITS'], dict):
                self.RATE_LIMITS.update(data['RATE_LIMITS'])
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
        for key in ('HOST', 'PORT', 'DEBUG', 'MAX_CONTENT_LENGTH_MB',
                    'CLEANUP_DAYS', 'LOG_LEVEL', 'SESSION_TTL_HOURS',
                    'OUTPUT_CLEANUP_DAYS'):
            env_val = os.environ.get(f'CT_{key}')
            if env_val is None:
                continue
            if key in ('PORT', 'MAX_CONTENT_LENGTH_MB', 'CLEANUP_DAYS',
                       'SESSION_TTL_HOURS', 'OUTPUT_CLEANUP_DAYS'):
                try:
                    setattr(self, key, int(env_val))
                except ValueError:
                    import logging
                    logging.getLogger('contract_tool').warning(
                        '环境变量 CT_%s 的值 "%s" 无法解析为整数，使用默认值', key, env_val)
            elif key == 'DEBUG':
                setattr(self, key, env_val.lower() in ('1', 'true', 'yes'))
            else:
                setattr(self, key, env_val)


config = Config()
