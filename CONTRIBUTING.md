# Contributing to DiscordAutoJoin

Thanks for your interest in contributing! This document explains the project structure, coding standards, and workflow.

## 📁 Project Structure

```
DiscordAutoJoin/
├── __init__.py          # Package exports (VERSION, CONFIG, state, entry points)
├── main.py              # Entry point: CLI parsing, lock, tray, thread launch
├── chrome_flags.py      # 27 curated safe Chrome flags (no dependencies)
├── config.py            # Path constants, JSON config loading with UTF-8
├── logging_setup.py     # Rotating file logger, CategoryFilter, Console class
├── lock.py              # PID-based instance locking with stale lock detection
├── state.py             # AppState singleton with RLock-protected properties
├── resource_guard.py    # Domain blocking regex + CSS injection
├── actions.py           # MONITOR_JS, CLICK_MIC_JS, safe_eval() wrapper
├── browser.py           # Chrome process management (psutil-based)
├── tray.py              # System tray icon, menu, callbacks, startup registration
├── automation.py        # Core orchestrator: 7-step lifecycle loop
├── build.bat            # PyInstaller build script
├── cache/               # Runtime cache directory
├── crash_dumps/         # Crash dump storage
└── logs/                # Log file storage

tests/
├── __init__.py
├── conftest.py          # Shared fixtures (temp_appdata, clean_config, reset_state)
├── test_config.py       # Unit tests for config.py
├── test_state.py        # Unit tests for state.py (including thread safety)
├── test_lock.py         # Unit tests for lock.py
├── test_resource_guard.py  # Unit tests for resource_guard.py
└── test_integration.py  # End-to-end tests with mocked Playwright

plans/
└── roadmap.md           # Full transformation roadmap (7 phases)

pyproject.toml           # Package metadata, dependencies, pytest config
README.md                # User-facing documentation
CONTRIBUTING.md          # This file
```

## 🔗 Dependency Graph

Modules must follow this dependency order (no circular imports):

```
Level 0 (no internal deps):
    chrome_flags.py, config.py, state.py, resource_guard.py, actions.py

Level 1 (depends on Level 0):
    logging_setup.py → config.py
    lock.py → config.py, logging_setup.py
    browser.py → config.py, logging_setup.py

Level 2 (depends on Level 0-1):
    tray.py → config.py, state.py, logging_setup.py, browser.py

Level 3 (depends on Level 0-2):
    automation.py → config.py, chrome_flags.py, state.py, logging_setup.py,
                    browser.py, resource_guard.py, actions.py, tray.py

Level 4 (depends on Level 0-3):
    __init__.py → all above
    main.py → __init__.py, tray.py
```

**Rule:** A module at level N may only import from levels 0 through N-1. Never import upward.

## 🧵 Thread Safety

The application runs two threads:

1. **Main thread** — System tray icon (`pystray.Icon.run()`)
2. **Automation thread** — Asyncio event loop (`run_asyncio_loop()`)

All shared mutable state lives in [`state.py`](DiscordAutoJoin/state.py) and is protected by `threading.RLock`:

```python
# ✅ Correct — uses property with lock
state.status = "Connected"
current = state.status

# ❌ Wrong — bypasses the lock
state._status = "Connected"
```

`threading.Event` objects (`first_run_done`, `should_exit`) are inherently thread-safe and exposed directly.

## 📝 Coding Standards

### Docstrings

All public functions and classes must have Google-style docstrings:

```python
def load_config():
    """Load configuration from disk, merging with defaults.

    On first run, creates the config file with DEFAULT_CONFIG values.
    On subsequent runs, merges saved config with defaults so new keys
    are always present.

    Returns:
        dict: Merged configuration dictionary. Falls back to DEFAULT_CONFIG
              on any error.
    """
```

### Error Handling

- Never use bare `except:` or `except: pass`
- Always catch specific exception types
- Log non-critical failures at DEBUG level: `logger.debug(f"Context: {e}")`
- Re-raise fatal errors that require restart
- Use `safe_eval()` for all JavaScript evaluation in the page

### Logging

Use the `log` (Console) object for user-visible messages and the `logger` object for debug-only messages:

```python
from .logging_setup import log
import logging
logger = logging.getLogger("DiscordAutoJoin")

# User-visible (console + file):
log.info("Connected to voice", category="NET")
log.warn("Auth required", category="NET")
log.error("Connection lost", category="ERR")

# Debug-only (file only):
logger.debug(f"Non-critical failure: {e}")
```

Log categories: `SYS` (system), `NET` (network/Discord), `USR` (user action), `ERR` (error), `STATE` (state change).

### Imports

- Use relative imports within the package: `from .config import CONFIG`
- Standard library imports first, then third-party, then internal
- Never import from `main.py` in other modules (main is the entry point)

## 🧪 Testing

### Running Tests

```bash
# All tests with coverage:
pytest

# Unit tests only:
pytest -m unit

# Integration tests only:
pytest -m integration

# Specific test file:
pytest tests/test_config.py -v
```

### Writing Tests

- Use `pytest` fixtures from [`conftest.py`](tests/conftest.py) for temp directories and state reset
- Mock external dependencies (Playwright, Chrome, Discord API) — never make real network calls
- Mark integration tests with `@pytest.mark.integration`
- Mark slow tests with `@pytest.mark.slow`
- Aim for >60% coverage (enforced by `--cov-fail-under=60`)

### Test Fixtures

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `temp_appdata` | function | Creates temp %APPDATA% directory |
| `clean_config` | function | Fresh config file with defaults |
| `reset_state` | function | Resets AppState singleton between tests |
| `mock_lock_file` | function | Clean lock file path for lock tests |
| `sample_config_dict` | function | Sample config values for testing |

## 🔄 Pull Request Workflow

1. Fork the repository and create a feature branch
2. Make your changes following the coding standards above
3. Add/update tests for any new functionality
4. Run `pytest` and ensure all tests pass
5. Run `pytest --cov` and ensure coverage doesn't drop
6. Update documentation if needed (README, docstrings)
7. Submit a pull request with a clear description

## 🏷️ Versioning

The version is defined in [`main.py`](DiscordAutoJoin/main.py) as `VERSION = "1.0.0"` and follows [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking architectural changes
- **MINOR**: New features, new modules
- **PATCH**: Bug fixes, performance improvements, doc updates

## 🚀 Release Process

This section documents the step-by-step process for publishing a new release to PyPI.

### Prerequisites

- Push access to the [GitHub repository](https://github.com/DreamHAX444/DiscordAutoJoin)
- PyPI API token with upload permissions for the `DiscordAutoJoin` project
- `.pypirc` configured or `TWINE_USERNAME`/`TWINE_PASSWORD` environment variables set

### Release Checklist

1. **Update version** — Bump `VERSION` in [`DiscordAutoJoin/main.py`](DiscordAutoJoin/main.py) following semver
2. **Update changelog** — Add a new `## [X.Y.Z]` section in [`CHANGELOG.md`](CHANGELOG.md)
3. **Run full test suite** — `pytest` must pass with coverage ≥ 60%
4. **Run linting** — `ruff check DiscordAutoJoin/ tests/` and `ruff format --check DiscordAutoJoin/ tests/`
5. **Build wheel** — `python -m build --wheel`
6. **Check wheel** — `twine check dist/*.whl`
7. **Smoke test** — Run [`scripts/smoke_test.ps1`](scripts/smoke_test.ps1) to verify install from PyPI works
8. **Commit & tag**:
   ```bash
   git add -A
   git commit -m "vX.Y.Z: <brief description>"
   git tag -a vX.Y.Z -m "vX.Y.Z: <brief description>"
   git push origin main
   git push origin vX.Y.Z
   ```
9. **CI/CD publishes to PyPI** — The GitHub Actions [`publish`](.github/workflows/ci.yml) job triggers automatically on the tag push, verifies the tag matches the package version, builds the wheel, and publishes to PyPI via trusted publishing
10. **Create GitHub Release** — Go to [GitHub Releases](https://github.com/DreamHAX444/DiscordAutoJoin/releases/new), select the tag, attach the wheel, and paste the changelog entry
11. **Verify** — `pip install discordautojoin` from a clean environment and run `discord-autojoin --version`

### Automated Publishing

The CI/CD pipeline (`.github/workflows/ci.yml`) includes a `publish` job that:
- Triggers only on `v*` tag pushes (e.g., `v1.0.0`, `v2.0.0`)
- Runs after `lint`, `test`, and `build` jobs all pass
- Verifies the Git tag matches `VERSION` in `main.py`
- Builds a clean wheel and checks it with `twine check`
- Publishes to PyPI using the official [`pypa/gh-action-pypi-publish`](https://github.com/pypa/gh-action-pypi-publish) action

### Pre-commit Hooks

This project uses [pre-commit](https://pre-commit.com/) to enforce code quality before commits:

```bash
pip install pre-commit
pre-commit install
```

The hooks (configured in [`.pre-commit-config.yaml`](.pre-commit-config.yaml)) run `ruff` for linting and formatting on all staged Python files.

## 📋 Roadmap

See [`plans/roadmap.md`](plans/roadmap.md) for the full transformation plan:

- ✅ Phase 1: Security Hardening
- ✅ Phase 2: Performance Optimization & Code Cleanup
- ✅ Phase 3: Architectural Redesign (12 modules)
- ✅ Phase 4: Final Integration, Testing & Documentation
- ✅ Phase 5: Finalization & Hardening
- ✅ Phase 6: Distribution & Release Readiness
- ✅ Phase 7: Release Pipeline & Distribution
- ✅ Phase 8: Post-Release Hardening & Automation