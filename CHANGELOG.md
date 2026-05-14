# Changelog

All notable changes to DiscordAutoJoin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-05-14

### Added

- **Modular architecture**: Split monolithic 832-line `main.py` into 12 focused modules with clean acyclic dependency graph (`actions`, `automation`, `browser`, `chrome_flags`, `config`, `lock`, `logging_setup`, `main`, `resource_guard`, `state`, `tray`, `__init__`)
- **Comprehensive test suite**: 239 tests across 9 test files with 69% code coverage
  - `test_actions.py` (22 tests, 100% coverage) — `safe_eval()`, `MONITOR_JS`, `CLICK_MIC_JS`
  - `test_browser.py` (25 tests, 98% coverage) — Chrome process management with mocked `psutil`
  - `test_config.py` (30 tests, 100% coverage) — config loading, defaults, file I/O
  - `test_integration.py` (41 tests) — end-to-end flows with mocked Playwright
  - `test_lock.py` (18 tests, 100% coverage) — PID-based instance locking
  - `test_logging_setup.py` (20 tests, 100% coverage) — Console, CategoryFilter, DEBUG_MODE
  - `test_resource_guard.py` (18 tests, 100% coverage) — route interception, CSS injection
  - `test_state.py` (30 tests, 100% coverage) — RLock-protected state transitions
  - `test_tray.py` (35 tests, 86% coverage) — icon generation, menu, callbacks, startup
- **CI/CD pipeline** (`.github/workflows/ci.yml`): 3 jobs — lint (ruff), test (Python 3.9–3.12 matrix with coverage), build (wheel artifact)
- **CLI entry points**: `discord-autojoin` and `discord-autojoin-debug` via `pyproject.toml` console_scripts
- **`--version` / `-V` flag**: Print version and exit without starting the application
- **`--debug` flag**: Enable verbose console output for all log messages
- **`pyproject.toml`**: Modern build configuration with `setuptools.build_meta` backend, SPDX license, dependency ranges, pytest/coverage config
- **`MANIFEST.in`**: Excludes development artifacts (venv, cache, crash_dumps, logs) from distributions
- **`CONTRIBUTING.md`**: Development setup, testing, and contribution guidelines
- **`CHANGELOG.md`**: This file

### Changed

- **Security hardening**: Removed 4 dangerous Chrome flags (`--disable-web-security`, `--disable-features=TranslateUI`, `--disable-extensions`, `--disable-sync`)
- **Process management**: Replaced deprecated `wmic`/PowerShell with cross-platform `psutil` for Chrome process detection and priority management
- **Instance locking**: Replaced `os.kill(pid, 0)` (broken on Windows) with `psutil.pid_exists()` + Win32 `OpenProcess`/`CloseHandle` fallback
- **Thread safety**: All shared state protected by `threading.RLock` with property-based accessors
- **Logging**: Unified `Console` class with category tagging, silent mode for health checks, rotating file handler (5 MB, 3 backups)
- **Error handling**: `safe_eval()` wrapper with timeout, browser-closed detection, and error classification
- **Configuration**: JSON config with UTF-8 encoding, defaults merging, graceful corruption recovery
- **Chrome flags**: Curated set of 27 safe flags with resource limits and anti-detection measures
- **Resource optimization**: Domain blocking via Playwright route interception, CSS injection for performance
- **Build system**: Migrated from PyInstaller `.spec` to standard `pyproject.toml` with `python -m build --wheel`
- **Version**: Centralized `VERSION` constant in `main.py`, exported via `__init__.py`
- **README**: Comprehensive documentation with architecture diagram, test stats, CI/CD section, and 9-file test table

### Fixed

- `main_debug()` entry point: Now supports `--version` flag (previously started the full app)
- `logger.info()` call in `_run_app()`: Changed to `log.info()` to use the `Console` wrapper with `category` support
- Integration tests: Fixed `mock_page.locator` (sync `MagicMock` instead of `AsyncMock`) and missing `evaluate.return_value`
- Wheel build: Excluded `venv/`, `cache/`, `crash_dumps/`, `logs/` directories via `[tool.setuptools.package-data]` and `[tool.setuptools.packages.find] exclude`

### Removed

- Monolithic `main.py` (832 lines → split into 12 modules)
- PyInstaller `.spec` file and `build.bat`
- Deprecated `License :: OSI Approved :: MIT License` classifier
- Legacy `setuptools.backends._legacy:_Backend` build backend

## [0.1.0] — Initial Prototype

### Added

- Basic Discord voice channel auto-join via Playwright
- System tray icon with pystray
- Chrome persistent context with anti-detection flags
- Domain blocking and CSS injection for resource optimization
- JavaScript-based Discord UI state monitoring (`MONITOR_JS`, `CLICK_MIC_JS`)
- Windows startup registration via HKCU registry
- Instance locking via PID file
- JSON configuration file
- PyInstaller build pipeline