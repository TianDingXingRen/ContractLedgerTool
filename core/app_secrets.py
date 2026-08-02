"""Secret key persistence helpers for the Flask app."""

import logging
import os


def load_or_create_secret_key(base_dir):
    env_key = os.environ.get('CONTRACT_TOOL_SECRET_KEY')
    if env_key:
        return env_key

    key_file = os.path.join(str(base_dir), '.secret_key')
    if os.path.exists(key_file):
        with open(key_file, 'r', encoding='utf-8') as f:
            return f.read().strip()

    key = os.urandom(32).hex()
    with open(key_file, 'w', encoding='utf-8') as f:
        f.write(key)

    try:
        os.chmod(key_file, 0o600)
    except OSError:
        logging.getLogger('contract_tool').warning(
            '无法收紧本地密钥文件权限: %s', key_file, exc_info=True,
        )
    return key
