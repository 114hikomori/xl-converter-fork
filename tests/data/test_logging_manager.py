import logging
from unittest.mock import patch, MagicMock

import pytest

import data.logging_manager as logging_manager
from data.logging_manager import LoggingManager, DEFAULT_LEVEL


@pytest.fixture(autouse=True)
def reset_singleton():
    LoggingManager._instance = None
    yield
    LoggingManager._instance = None

@pytest.fixture
def fresh_logger():
    """A throwaway logger so tests never mutate the real root logger."""
    logger = logging.Logger("test_logging_manager_root")
    yield logger
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

@pytest.fixture
def manager(fresh_logger):
    with patch("logging.getLogger", return_value=fresh_logger):
        return LoggingManager()

@pytest.fixture
def isolated_logs_dir(tmp_path, monkeypatch):
    """Points LOGS_DIR/LOGS_PATH at a throwaway directory so file-handler
    tests never touch the real logs folder."""
    logs_dir = tmp_path / "logs"
    monkeypatch.setattr(logging_manager, "LOGS_DIR", str(logs_dir))
    monkeypatch.setattr(logging_manager, "LOGS_PATH", str(logs_dir / "logs.txt"))
    return logs_dir


def test_singleton_instance():
    assert LoggingManager() is LoggingManager()

def test_init_sets_up_stream_handler_and_default_level(manager, fresh_logger):
    assert manager.stream_handler in fresh_logger.handlers
    assert fresh_logger.level == DEFAULT_LEVEL

def test_setLevel_valid(manager, fresh_logger):
    manager.setLevel("DEBUG")
    assert fresh_logger.level == logging.DEBUG

def test_setLevel_invalid(manager, fresh_logger):
    with patch.object(fresh_logger, "error") as mock_error:
        manager.setLevel("NOT_A_LEVEL")
    mock_error.assert_called_once()
    assert "NOT_A_LEVEL" in mock_error.call_args[0][0]
    assert fresh_logger.level == DEFAULT_LEVEL

def test_startLoggingToFile_creates_and_attaches_handler(manager, fresh_logger, isolated_logs_dir):
    manager.startLoggingToFile()
    assert manager.file_handler is not None
    assert manager.file_handler in fresh_logger.handlers
    assert manager.isLoggingToFile() is True

def test_startLoggingToFile_sets_level(manager, fresh_logger, isolated_logs_dir):
    manager.startLoggingToFile(level="DEBUG")
    assert fresh_logger.level == logging.DEBUG

def test_startLoggingToFile_no_level_leaves_level_unchanged(manager, fresh_logger, isolated_logs_dir):
    fresh_logger.setLevel(logging.ERROR)
    manager.startLoggingToFile()
    assert fresh_logger.level == logging.ERROR

def test_stopLoggingToFile_closes_and_detaches_handler(manager, fresh_logger, isolated_logs_dir):
    manager.startLoggingToFile()
    handler = manager.file_handler
    manager.stopLoggingToFile()
    assert handler not in fresh_logger.handlers
    assert manager.file_handler is None
    assert manager.isLoggingToFile() is False
    assert fresh_logger.level == DEFAULT_LEVEL

def test_stopLoggingToFile_noop_when_never_started(manager, fresh_logger):
    manager.stopLoggingToFile()  # Must not raise
    assert manager.file_handler is None

def test_startLoggingToFile_after_stop_creates_fresh_handler(manager, fresh_logger, isolated_logs_dir):
    """Regression test for the stale-closed-handler bug: stopLoggingToFile()
    must reset file_handler to None, or the next startLoggingToFile() call
    re-attaches the already-closed handler instead of building a fresh one,
    and every log record afterward is silently dropped."""
    manager.startLoggingToFile()
    old_handler = manager.file_handler

    manager.stopLoggingToFile()
    manager.startLoggingToFile()

    assert manager.file_handler is not old_handler
    assert manager.file_handler in fresh_logger.handlers
    assert old_handler not in fresh_logger.handlers
    assert old_handler.stream is None               # Confirmed dead
    assert manager.file_handler.stream is not None  # Fresh and working

def test_isLoggingToFile_false_by_default(manager):
    assert manager.isLoggingToFile() is False

def test_wipeLogsDir_no_logs(manager, isolated_logs_dir):
    assert manager.wipeLogsDir() == "No logs have been found."

def test_wipeLogsDir_success(manager, isolated_logs_dir):
    isolated_logs_dir.mkdir(parents=True)
    (isolated_logs_dir / "logs.txt").write_text("x")
    assert manager.wipeLogsDir() == "Successfully deleted logs folder."
    assert not isolated_logs_dir.exists()

def test_wipeLogsDir_oserror(manager, isolated_logs_dir):
    isolated_logs_dir.mkdir(parents=True)
    with patch("shutil.rmtree", side_effect=OSError("permission denied")):
        result = manager.wipeLogsDir()
    assert "Cannot wipe logs folder." in result
    assert "permission denied" in result

def test_getLogsDir(manager, isolated_logs_dir):
    assert manager.getLogsDir() == str(isolated_logs_dir)
