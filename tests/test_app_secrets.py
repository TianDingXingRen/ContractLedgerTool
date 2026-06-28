def test_secret_key_env_var_takes_precedence(tmp_path, monkeypatch):
    from app_secrets import load_or_create_secret_key

    monkeypatch.setenv('CONTRACT_TOOL_SECRET_KEY', 'env-secret')

    assert load_or_create_secret_key(tmp_path) == 'env-secret'
    assert not (tmp_path / '.secret_key').exists()


def test_secret_key_reuses_existing_file(tmp_path, monkeypatch):
    from app_secrets import load_or_create_secret_key

    monkeypatch.delenv('CONTRACT_TOOL_SECRET_KEY', raising=False)
    (tmp_path / '.secret_key').write_text('persisted-secret\n', encoding='utf-8')

    assert load_or_create_secret_key(tmp_path) == 'persisted-secret'


def test_secret_key_is_created_when_missing(tmp_path, monkeypatch):
    from app_secrets import load_or_create_secret_key

    monkeypatch.delenv('CONTRACT_TOOL_SECRET_KEY', raising=False)

    key = load_or_create_secret_key(tmp_path)

    assert len(key) == 64
    int(key, 16)
    assert (tmp_path / '.secret_key').read_text(encoding='utf-8') == key
