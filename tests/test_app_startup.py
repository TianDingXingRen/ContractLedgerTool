from app_startup import should_open_browser


def test_should_not_open_browser_when_disabled():
    assert should_open_browser(
        no_browser=True,
        debug=False,
        environ={'WERKZEUG_RUN_MAIN': 'true'},
    ) is False


def test_should_open_browser_without_debug_even_before_reloader():
    assert should_open_browser(
        no_browser=False,
        debug=False,
        environ={},
    ) is True


def test_should_open_browser_in_debug_reloader_process():
    assert should_open_browser(
        no_browser=False,
        debug=True,
        environ={'WERKZEUG_RUN_MAIN': 'true'},
    ) is True


def test_should_wait_for_reloader_when_debugging():
    assert should_open_browser(
        no_browser=False,
        debug=True,
        environ={},
    ) is False
