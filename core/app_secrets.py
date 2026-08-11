"""Secret key persistence helpers for the Flask app."""

import logging
import os
import tempfile


_MIN_SECRET_LENGTH = 32


def _is_valid_secret(value):
    return len(str(value or '').strip()) >= _MIN_SECRET_LENGTH


def _write_secret_atomically(key_file, key):
    directory = os.path.dirname(key_file) or '.'
    os.makedirs(directory, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        prefix='.secret_key.', suffix='.tmp', dir=directory, text=True
    )
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(key)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            logging.getLogger('contract_tool').warning(
                '无法收紧临时密钥文件权限: %s', temporary_path,
                exc_info=True,
            )
        os.replace(temporary_path, key_file)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def load_or_create_secret_key(base_dir):
    env_key = os.environ.get('CONTRACT_TOOL_SECRET_KEY')
    if env_key:
        if not _is_valid_secret(env_key):
            raise ValueError('CONTRACT_TOOL_SECRET_KEY 长度至少需要 32 个字符')
        return env_key

    key_file = os.path.join(str(base_dir), '.secret_key')
    if os.path.exists(key_file):
        with open(key_file, 'r', encoding='utf-8') as f:
            existing_key = f.read().strip()
        if _is_valid_secret(existing_key):
            return existing_key
        logging.getLogger('contract_tool').warning(
            '本地密钥文件为空或过短，正在安全轮换: %s', key_file
        )

    key = os.urandom(32).hex()
    _write_secret_atomically(key_file, key)

    try:
        os.chmod(key_file, 0o600)
    except OSError:
        logging.getLogger('contract_tool').warning(
            '无法收紧本地密钥文件权限: %s', key_file, exc_info=True,
        )
    return key
