def test_secret_key_env_var_takes_precedence(tmp_path, monkeypatch):
    from core.app_secrets import load_or_create_secret_key

    env_secret = 'e' * 32
    monkeypatch.setenv('CONTRACT_TOOL_SECRET_KEY', env_secret)

    assert load_or_create_secret_key(tmp_path) == env_secret
    assert not (tmp_path / '.secret_key').exists()


def test_secret_key_reuses_existing_file(tmp_path, monkeypatch):
    from core.app_secrets import load_or_create_secret_key

    monkeypatch.delenv('CONTRACT_TOOL_SECRET_KEY', raising=False)
    persisted_secret = 'p' * 32
    (tmp_path / '.secret_key').write_text(
        persisted_secret + '\n', encoding='utf-8'
    )

    assert load_or_create_secret_key(tmp_path) == persisted_secret


def test_secret_key_is_created_when_missing(tmp_path, monkeypatch):
    from core.app_secrets import load_or_create_secret_key

    monkeypatch.delenv('CONTRACT_TOOL_SECRET_KEY', raising=False)

    key = load_or_create_secret_key(tmp_path)

    assert len(key) == 64
    int(key, 16)
    assert (tmp_path / '.secret_key').read_text(encoding='utf-8') == key


def test_empty_secret_key_file_is_rotated_atomically(tmp_path, monkeypatch):
    from core.app_secrets import load_or_create_secret_key

    monkeypatch.delenv('CONTRACT_TOOL_SECRET_KEY', raising=False)
    key_file = tmp_path / '.secret_key'
    key_file.write_text('', encoding='utf-8')

    key = load_or_create_secret_key(tmp_path)

    assert len(key) == 64
    assert key_file.read_text(encoding='utf-8') == key
    assert not list(tmp_path.glob('.secret_key.*.tmp'))
