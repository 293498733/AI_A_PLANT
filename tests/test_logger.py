import logging
from pipeline.logger import CleanupFilter, TerminalFormatter, get, _LOGGER


class TestCleanupFilter:
    def test_blocks_clean_context(self):
        f = CleanupFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "请清理上下文", (), None)
        assert f.filter(record) is False

    def test_blocks_english_clean(self):
        f = CleanupFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "start fresh now", (), None)
        assert f.filter(record) is False

    def test_allows_normal(self):
        f = CleanupFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "task completed", (), None)
        assert f.filter(record) is True

    def test_case_insensitive(self):
        f = CleanupFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "CLEAN CONTEXT please", (), None)
        assert f.filter(record) is False

    def test_partial_match_works(self):
        f = CleanupFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "should清理上下文here", (), None)
        assert f.filter(record) is False


class TestTerminalFormatter:
    def test_info_no_color_on_message(self):
        fmt = TerminalFormatter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "normal message", (), None)
        result = fmt.format(record)
        assert "normal message" in result

    def test_warning_adds_color(self):
        fmt = TerminalFormatter()
        record = logging.LogRecord("test", logging.WARNING, "", 0, "warning!", (), None)
        result = fmt.format(record)
        assert "\033[33m" in result

    def test_error_adds_color(self):
        fmt = TerminalFormatter()
        record = logging.LogRecord("test", logging.ERROR, "", 0, "error!", (), None)
        result = fmt.format(record)
        assert "\033[31m" in result


class TestGetUninitialized:
    def test_raises_when_not_init(self, monkeypatch):
        # Save and clear the global logger
        monkeypatch.setattr("pipeline.logger._LOGGER", None)
        try:
            get()
            assert False, "should have raised"
        except RuntimeError:
            pass
