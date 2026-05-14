# DiscordAutoJoin v1.0

[![CI](https://github.com/DreamHAX444/DiscordAutoJoin/actions/workflows/ci.yml/badge.svg)](https://github.com/DreamHAX444/DiscordAutoJoin/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![Coverage](https://img.shields.io/badge/coverage-69%25-green)](https://github.com/DreamHAX444/DiscordAutoJoin)
[![Tests](https://img.shields.io/badge/tests-239%20passed-brightgreen)](https://github.com/DreamHAX444/DiscordAutoJoin)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey)](https://github.com/DreamHAX444/DiscordAutoJoin)

A powerful, persistent Windows background application that automatically joins a specific Discord voice channel, enables the camera, mutes the mic, and monitors connection health — all from a lightweight system tray icon.

## 🚀 Features

- **Automated Voice Connection:** Navigates to a Discord channel and joins voice automatically.
- **Camera Automation:** Silently re-enables the camera if Discord turns it off.
- **Microphone Management:** Ensures the microphone stays muted (configurable).
- **Persistent Monitoring:** Continuously checks connection health and auto-reconnects on drop.
- **System Tray Integration:** Runs silently in the background with a real-time diagnostic tray icon.
- **Windows Startup Support:** Registers itself to start automatically when Windows boots.
- **Resource Optimized:** Blocks analytics domains, disables animations, limits Chrome memory to ~128MB JS heap.
- **Thread-Safe State:** All shared state protected by `threading.RLock` for safe concurrent access.
- **Secure by Default:** Zero dangerous Chrome flags — all security boundaries intact.

## 🏗️ Architecture

The codebase is split into **12 focused modules** with a strict acyclic dependency graph:

```
main.py  ──►  __init__.py  ──►  automation.py  ──►  browser.py
   │              │                   │                 chrome_flags.py
   │              │                   ├──► actions.py    resource_guard.py
   │              │                   ├──► tray.py ──► state.py
   │              │                   └──► config.py
   │              ├──► lock.py ──► config.py
   │              └──► logging_setup.py ──► config.py
   └──► tray.py (icon ref)
```

| # | Module | Responsibility |
|---|--------|---------------|
| 1 | [`chrome_flags.py`](DiscordAutoJoin/chrome_flags.py) | 27 curated safe Chrome flags |
| 2 | [`config.py`](DiscordAutoJoin/config.py) | Path constants, JSON config with UTF-8 + field validation |
| 3 | [`logging_setup.py`](DiscordAutoJoin/logging_setup.py) | Rotating file logger, `CategoryFilter`, `Console` class |
| 4 | [`lock.py`](DiscordAutoJoin/lock.py) | PID-based instance locking with stale lock detection |
| 5 | [`state.py`](DiscordAutoJoin/state.py) | `AppState` singleton — 10 RLock-protected properties + 2 `threading.Event` |
| 6 | [`resource_guard.py`](DiscordAutoJoin/resource_guard.py) | Domain blocking regex + CSS injection |
| 7 | [`actions.py`](DiscordAutoJoin/actions.py) | `MONITOR_JS`, `CLICK_MIC_JS`, `safe_eval()` with timeout |
| 8 | [`browser.py`](DiscordAutoJoin/browser.py) | Chrome process management, lock removal, priority, HWND discovery |
| 9 | [`tray.py`](DiscordAutoJoin/tray.py) | Icon generation, dynamic menu, 6 tray callbacks, startup registration |
| 10 | [`automation.py`](DiscordAutoJoin/automation.py) | 7-step lifecycle orchestrator + `run_asyncio_loop()` |
| 11 | [`__init__.py`](DiscordAutoJoin/__init__.py) | Package exports |
| 12 | [`main.py`](DiscordAutoJoin/main.py) | Thin entry point (~90 lines): CLI parsing, lock, tray, thread launch |

## 🛠️ Technology Stack

- **Python 3.9+** — Core logic and automation
- **Playwright** — Browser automation for Discord web client interaction
- **PyStray** — System tray icon and menu management
- **Pillow** — Dynamic tray icon generation
- **psutil** — Cross-platform process management (priority, memory, PID checks)

## 📦 Installation

### Prerequisites

- Windows 10/11
- Python 3.9 or later
- Google Chrome installed

### Setup

```bash
# Clone the repository
git clone https://github.com/DreamHAX444/DiscordAutoJoin.git
cd DiscordAutoJoin

# Install the package with dependencies
pip install -e .

# Install Playwright's Chromium browser
playwright install chromium

# Or install just the dependencies manually:
pip install playwright>=1.40.0 pystray>=0.19.0 pillow>=10.0.0 psutil>=5.9.0
```

### Development Setup

```bash
pip install -e ".[dev]"     # Includes pytest, pytest-asyncio, pytest-cov
```

## 🖥️ Usage

### Running the Application

```bash
# Via console_scripts (after pip install):
discord-autojoin

# In debug mode (all messages printed to console):
discord-autojoin-debug

# Or run directly:
python -m DiscordAutoJoin.main
python -m DiscordAutoJoin.main --debug
python -m DiscordAutoJoin.main --version
```

### First Run

1. On first launch, the app opens Chrome and navigates to Discord.
2. **Log in manually** in the Chrome window if prompted.
3. Right-click the tray icon and select **"Confirm Login Done"**.
4. The app will join the configured voice channel, enable camera, mute mic, and minimize Chrome.

### Tray Menu

| Menu Item | Action |
|-----------|--------|
| Status / Uptime / Last Action | Real-time dashboard (read-only) |
| View Config | Shows current configuration values |
| Confirm Login Done | Signals that manual login is complete |
| Pause / Resume Automation | Temporarily halts monitoring |
| Force Reconnect | Triggers a full disconnect/reconnect cycle |
| Show / Hide Chrome | Toggles the Chrome window visibility |
| View Debug Log | Opens the log file in Notepad |
| Restart App | Clean restart of the application |
| Exit | Clean shutdown (releases lock, kills Chrome) |

### Configuration

The config file is stored at `%APPDATA%/DiscordAutoJoin/config.json` and is created automatically on first run with these defaults:

```json
{
    "DISCORD_URL": "https://discord.com/channels/...",
    "MAX_JOIN_RETRIES": 30,
    "POLL_INTERVAL": 5.0,
    "RESTART_DELAY": 5,
    "HEALTH_LOG_EVERY": 12,
    "MAX_CONSECUTIVE_ERRS": 3,
    "MAX_RELOAD_FAILS": 2,
    "MAX_LAUNCH_RETRIES": 5
}
```

Edit `DISCORD_URL` to point to your target voice channel. Missing keys are automatically filled from defaults on next launch.

### Logs

Logs are stored at `%APPDATA%/DiscordAutoJoin/app.log` with rotation (5 MB max, 3 backups).

## 🧪 Testing

**239 tests pass with 69% code coverage** (core modules at 100%).

```bash
# Run all tests with coverage:
pytest

# Run only unit tests:
pytest -m unit

# Run only integration tests:
pytest -m integration

# Run with verbose output:
pytest -v --tb=long

# Coverage report is generated in htmlcov/index.html
```

### Test Structure

| File | Tests | Coverage | What It Tests |
|------|-------|----------|---------------|
| [`tests/test_config.py`](tests/test_config.py) | 17 | 100% | Config loading, merging, missing keys, corrupt files |
| [`tests/test_state.py`](tests/test_state.py) | 27 | 100% | AppState properties, thread safety, events |
| [`tests/test_lock.py`](tests/test_lock.py) | 14 | 69% | Instance locking, stale lock detection, release |
| [`tests/test_resource_guard.py`](tests/test_resource_guard.py) | 23 | 67% | Domain blocking regex, CSS optimization |
| [`tests/test_actions.py`](tests/test_actions.py) | 22 | 100% | safe_eval(), MONITOR_JS, CLICK_MIC_JS |
| [`tests/test_browser.py`](tests/test_browser.py) | 25 | 98% | Chrome process management, locks, priority, HWND |
| [`tests/test_tray.py`](tests/test_tray.py) | 35 | 86% | Icon generation, menu, callbacks, startup |
| [`tests/test_logging_setup.py`](tests/test_logging_setup.py) | 20 | 100% | Console, CategoryFilter, DEBUG_MODE |
| [`tests/test_integration.py`](tests/test_integration.py) | 56 | — | Full flow with mocked Playwright, error recovery |

### CI/CD

GitHub Actions pipeline (`.github/workflows/ci.yml`):
- **Lint** — ruff check + format verification
- **Test** — pytest matrix across Python 3.9–3.12 with coverage
- **Build** — wheel artifact generation

## 📁 Data Directory

All application data is stored in `%APPDATA%/DiscordAutoJoin/`:

```
%APPDATA%/DiscordAutoJoin/
├── config.json          # User configuration
├── app.log              # Rotating log file
├── app.lock             # Instance lock file
└── ChromeProfile/       # Persistent Chrome profile (login session)
```

## 🛡️ Security

- **No dangerous Chrome flags:** `--disable-web-security`, `--no-sandbox`, `--disable-site-isolation-trials`, and `--disable-gpu-sandbox` have been removed.
- **Sandbox intact:** All Chrome process isolation and site isolation remain enabled.
- **No credentials stored:** Login session is handled entirely by Chrome's persistent profile.
- **No telemetry:** Analytics/tracking domains (Sentry, Google Analytics, New Relic, DataDog) are blocked at the request level.

## 📄 License

This project is for educational purposes. Use responsibly and adhere to Discord's Terms of Service.

## 🤝 Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for module structure, coding standards, and pull request guidelines.
