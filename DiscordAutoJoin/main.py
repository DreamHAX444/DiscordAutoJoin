import os, sys, ctypes, logging, asyncio, threading, winreg, traceback, shutil, subprocess, re, json, time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from PIL import Image, ImageDraw
import pystray
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

# ── Configuration Management ──────────────────────────────────────────────────
APP_DATA_DIR = os.path.join(os.environ["APPDATA"], "DiscordAutoJoin")
CHROME_PROFILE_DIR = os.path.join(APP_DATA_DIR, "ChromeProfile")
LOG_FILE = os.path.join(APP_DATA_DIR, "app.log")
LOCK_FILE = os.path.join(APP_DATA_DIR, "app.lock")
CONFIG_FILE = os.path.join(APP_DATA_DIR, "config.json")
STATUS_FILE = os.path.join(APP_DATA_DIR, "status.txt")
os.makedirs(APP_DATA_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "DISCORD_URL": "https://discord.com/channels/1436354443636379732/1436354444462784625",
    "MAX_JOIN_RETRIES": 30,
    "POLL_INTERVAL": 5.0,
    "RESTART_DELAY": 5,
    "HEALTH_LOG_EVERY": 12,
    "MAX_CONSECUTIVE_ERRS": 3,
    "MAX_RELOAD_FAILS": 2,
    "MAX_LAUNCH_RETRIES": 5
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r') as f:
            loaded = json.load(f)
            # Merge and save back if any keys were missing
            merged = {**DEFAULT_CONFIG, **loaded}
            with open(CONFIG_FILE, 'w') as out:
                json.dump(merged, out, indent=4)
            return merged
    except Exception as e:
        print(f"Config load error: {e}, using defaults.")
        return DEFAULT_CONFIG

CONFIG = load_config()

# ── Anti-Detection & Optimization Constants ──────────────────────────────────
CHROME_ARGS = [
    '--disable-blink-features=AutomationControlled', '--disable-extensions',
    '--disable-default-apps', '--disable-sync', '--disable-breakpad',
    '--disable-crash-reporter', '--disable-logging', '--no-default-browser-check',
    '--disable-client-side-phishing-detection', '--disable-domain-reliability',
    '--disable-speech-api', '--disable-component-update', '--disable-hang-monitor',
    '--disable-prompt-on-repost', '--disable-ipc-flooding-protection', '--disable-dev-tools',
    '--metrics-recording-only', '--disable-background-timer-throttling',
    '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows',
    '--disable-background-mode', '--no-sandbox', '--disable-gpu', '--disable-gpu-compositing',
    '--disable-software-rasterizer', '--disable-dev-shm-usage', '--disable-site-isolation-trials',
    '--disable-canvas-aa', '--disable-2d-canvas-clip-aa', '--disable-webgl',
    '--js-flags=--max-old-space-size=128', '--disk-cache-size=1', '--disable-notifications',
    '--disable-popup-blocking', '--renderer-process-limit=1', '--disable-gpu-sandbox',
    '--disable-accelerated-2d-canvas', '--disable-accelerated-video-decode',
    '--disable-print-preview', '--disable-spell-checking', '--disable-translate',
    '--disable-web-security', '--disable-dinosaur-easter-egg', '--no-pings', '--no-first-run',
    '--no-zygote', '--disable-partial-raster', '--media-cache-size=1',
    '--enable-features=ReducedReferrerGranularity', '--start-maximized',
]

BLOCKED_DOMAINS = re.compile(
    r'(sentry\.io|google-analytics|googletagmanager|doubleclick|'
    r'newrelic|datadoghq|cdn\.discordapp\.com/attachments|'
    r'media\.discordapp\.net|images-ext)', re.IGNORECASE
)

OPTIMIZE_CSS = '''
*, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; }
[class*="gif"], [class*="avatar"] img:not([class*="voice"]) { visibility: hidden !important; }
'''

# ── Logger ───────────────────────────────────────────────────────────────────
logger = logging.getLogger("DiscordAutoJoin")
logger.setLevel(logging.DEBUG)

class CategoryFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, 'category'):
            record.category = 'SYS'
        return True

logger.addFilter(CategoryFilter())

_fmt = logging.Formatter('[%(asctime)s] %(levelname)-8s [%(category)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
_fh = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(_fmt)
logger.addHandler(_fh)

class Console:
    @staticmethod
    def _log(level, category, msg, silent=False):
        if not silent: print(f"[{category}] {level}: {msg}", flush=True)
        extra = {'category': category}
        if level == "INFO": logger.info(msg, extra=extra)
        elif level == "WARN": logger.warning(msg, extra=extra)
        elif level == "ERROR": logger.error(msg, extra=extra)
        elif level == "OK": logger.info(msg, extra=extra)

    @staticmethod
    def info(msg, silent=False, category="SYS"): Console._log("INFO", category, msg, silent)
    @staticmethod
    def ok(msg, silent=False, category="SYS"): Console._log("OK", category, msg, silent)
    @staticmethod
    def warn(msg, silent=False, category="SYS"): Console._log("WARN", category, msg, silent)
    @staticmethod
    def error(msg, silent=False, category="SYS"): Console._log("ERROR", category, msg, silent)

log = Console

# ── Global State ─────────────────────────────────────────────────────────────
class AppState:
    def __init__(self):
        self.status = "Initializing"
        self.first_run_done = threading.Event()
        self.should_exit = threading.Event()
        self.paused = False
        self.force_reconnect = False
        self.browser_hwnd = None
        self.browser_hidden = False
        self.is_restarting = False
        self.restart_count = 0
        self.start_time = time.time()
        self.last_action = "App Started"
        self.action_timestamp = datetime.now()

state = AppState()
icon = None

def update_last_action(action, category="STATE", silent=True):
    state.last_action = action
    state.action_timestamp = datetime.now()
    log.info(action, silent=silent, category=category)

# ── Tray Icon & Menus ────────────────────────────────────────────────────────
_icon_cache = {}

def _get_icon(color):
    if color not in _icon_cache:
        img = Image.new('RGB', (64, 64), (0, 0, 0))
        ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=color)
        _icon_cache[color] = img
    return _icon_cache[color]

def _build_menu():
    pause_text = "Resume Automation" if state.paused else "Pause Automation"
    items = [
        pystray.MenuItem("Status Dashboard", _show_status),
        pystray.MenuItem(pause_text, _toggle_pause),
        pystray.MenuItem("Force Reconnect", _trigger_reconnect),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Show/Hide Chrome", _toggle_browser),
        pystray.MenuItem("View Log", lambda *_: os.startfile(LOG_FILE)),
    ]
    if state.status == "Waiting for login":
        items.insert(0, pystray.MenuItem("Login Done", _on_login_done))
        items.insert(1, pystray.Menu.SEPARATOR)
    items.extend([
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Restart App", _restart_app),
        pystray.MenuItem("Exit", _exit_app),
    ])
    return pystray.Menu(*items)

def set_tray(status, color):
    state.status = status
    if icon:
        # Override visual if paused, but maintain underlying logical status
        display_color = "gray" if state.paused else color
        display_status = f"Paused ({status})" if state.paused else status
        icon.icon = _get_icon(display_color)
        icon.title = f"Auto-Join: {display_status}"
        icon.menu = _build_menu()
        icon.update_menu()

# ── Tray Actions ─────────────────────────────────────────────────────────────
def _on_login_done(*_):
    update_last_action("Manual Login Confirmed", category="USR")
    state.first_run_done.set()
    set_tray("Connecting...", "yellow")

def _toggle_pause(*_):
    state.paused = not state.paused
    action = "Paused" if state.paused else "Resumed"
    update_last_action(f"Automation {action} by user", category="USR")
    set_tray(state.status, "green" if state.status == "Connected" else "yellow")

def _trigger_reconnect(*_):
    update_last_action("Force Reconnect Initiated by user", category="USR")
    state.force_reconnect = True

def _show_status(*_):
    uptime = str(timedelta(seconds=int(time.time() - state.start_time)))
    time_since_action = str(timedelta(seconds=int((datetime.now() - state.action_timestamp).total_seconds())))
    
    content = f"""=== Discord Auto-Join Status Dashboard ===
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

[ System State ]
Status: {state.status}
Automation: {'PAUSED' if state.paused else 'ACTIVE'}
Uptime: {uptime}
Last Action: {state.last_action} ({time_since_action} ago)
Consecutive Restarts: {state.restart_count}

[ Configuration ]
Target URL: {CONFIG['DISCORD_URL']}
Poll Interval: {CONFIG['POLL_INTERVAL']}s
Max Join Retries: {CONFIG['MAX_JOIN_RETRIES']}
Max Launch Retries: {CONFIG.get('MAX_LAUNCH_RETRIES', 5)}
"""
    with open(STATUS_FILE, "w") as f:
        f.write(content)
    os.startfile(STATUS_FILE)

def _toggle_browser(*_):
    if not state.browser_hwnd: _find_chrome_hwnd()
    if not state.browser_hwnd: return
    if state.browser_hidden:
        ctypes.windll.user32.ShowWindow(state.browser_hwnd, 9)
        state.browser_hidden = False
    else:
        ctypes.windll.user32.ShowWindow(state.browser_hwnd, 6)
        state.browser_hidden = True

def _restart_app(*_):
    log.info("Restarting app via tray...", silent=True, category="USR")
    state.is_restarting = True
    state.should_exit.set()
    if icon: icon.stop()

def _exit_app(*_):
    log.info("Exiting app via tray...", silent=True, category="USR")
    state.should_exit.set()
    if icon: icon.stop()

def _find_chrome_hwnd():
    hwnds = []
    buf = ctypes.create_unicode_buffer(260)
    def cb(hwnd, _):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            n = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if 0 < n < 260:
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 260)
                if "discord" in buf.value.lower():
                    hwnds.append(hwnd)
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(cb), 0)
    if hwnds: state.browser_hwnd = hwnds[0]

# ── Startup Registration ─────────────────────────────────────────────────────
def register_startup():
    script = os.path.abspath(sys.argv[0])
    cmd = f'"{sys.executable}"' if getattr(sys, 'frozen', False) else f'"{sys.executable}" "{script}"'
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE | winreg.KEY_READ)
        winreg.SetValueEx(key, "DiscordAutoJoin", 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
    except Exception as e:
        log.warn(f"Registry startup failed: {e}", category="SYS")

# ── Consolidated JavaScript ──────────────────────────────────────────────────
MONITOR_JS = '''() => {
    const joinXPath = "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'join voice')]";
    const joinBtn = document.evaluate(joinXPath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    const joinVisible = joinBtn && joinBtn.offsetWidth > 0;
    
    const camOff = !!document.querySelector('[aria-label="Turn On Camera"]');
    const micBtn = document.querySelector('button[aria-label*="ute" i], button[aria-label*="icrophone" i], button[aria-label*="Turn off" i]');
    
    let micUnmuted = false;
    if (micBtn) {
        const l = (micBtn.getAttribute('aria-label') || '').toLowerCase();
        const isMute = (l.includes('mute') && !l.includes('unmute')) || l.includes('turn off');
        micUnmuted = micBtn.hasAttribute('aria-checked') 
            ? (isMute ? micBtn.getAttribute('aria-checked') !== 'true' : micBtn.getAttribute('aria-checked') === 'true')
            : isMute;
    }
    return { joinVisible, camOff, micUnmuted };
}'''

CLICK_MIC_JS = '''() => {
    const micBtn = document.querySelector('button[aria-label*="ute" i], button[aria-label*="icrophone" i], button[aria-label*="Turn off" i]');
    if (micBtn) micBtn.click();
}'''

async def safe_eval(page, js, timeout=10):
    try:
        return await asyncio.wait_for(page.evaluate(js), timeout=timeout)
    except PlaywrightError as e:
        if "Target page, context or browser has been closed" in str(e) or "Browser closed" in str(e):
            raise e
        return None
    except Exception:
        return None

# ── Chrome Cleanup & Optimization ────────────────────────────────────────────
def kill_stale_chrome():
    """Aggressively terminate Chrome processes locked to our profile."""
    prof_name = os.path.basename(CHROME_PROFILE_DIR)
    ps_cmd = f"Get-CimInstance Win32_Process | Where-Object {{ $_.Name -match 'chrome.exe' -and $_.CommandLine -match '{prof_name}' }} | Stop-Process -Force"
    try:
        subprocess.run(["powershell", "-Command", ps_cmd], creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
    except Exception:
        pass
    
    # Wait for processes to die
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            chk = subprocess.run(
                ["powershell", "-Command", f"@((Get-CimInstance Win32_Process | Where-Object {{ $_.Name -match 'chrome.exe' -and $_.CommandLine -match '{prof_name}' }}).Id).Count"],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=3
            )
            if chk.stdout.strip() == "0": break
        except Exception:
            break
        time.sleep(0.5)

def remove_chrome_locks():
    """Wipe Playwright/Chrome lockfiles to prevent TargetClosedError."""
    locks = ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile", ".parentlock"]
    for fname in locks:
        path = os.path.join(CHROME_PROFILE_DIR, fname)
        try:
            if os.path.exists(path): os.remove(path)
        except Exception:
            pass
            
    # Also clean up Crashpad to prevent profile corruption warnings
    crashpad_dir = os.path.join(CHROME_PROFILE_DIR, "Crashpad")
    try:
        if os.path.exists(crashpad_dir): shutil.rmtree(crashpad_dir, ignore_errors=True)
    except Exception:
        pass

def lower_chrome_priority():
    try:
        subprocess.run('wmic process where "name=\'chrome.exe\'" CALL setpriority "below normal"',
                       shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        pass

async def optimize_page(page):
    async def handle_route(route):
        if BLOCKED_DOMAINS.search(route.request.url): await route.abort()
        else: await route.continue_()
    try:
        await page.route('**/*', handle_route)
        await page.add_style_tag(content=OPTIMIZE_CSS)
    except Exception:
        pass

# ── Core Automation Loop ─────────────────────────────────────────────────────
async def automation_loop():
    async with async_playwright() as p:
        while not state.should_exit.is_set():
            context = None
            state.browser_hwnd = None
            state.force_reconnect = False

            try:
                log.info("Preparing browser environment...", category="SYS")
                kill_stale_chrome()
                remove_chrome_locks()

                # Launch with exponential backoff for TargetClosedError resilience
                launch_exc = None
                max_launch_retries = CONFIG.get('MAX_LAUNCH_RETRIES', 5)
                for attempt in range(1, max_launch_retries + 1):
                    try:
                        context = await p.chromium.launch_persistent_context(
                            user_data_dir=CHROME_PROFILE_DIR, channel="chrome",
                            headless=False, no_viewport=True,
                            permissions=['camera', 'microphone'], args=CHROME_ARGS
                        )
                        launch_exc = None
                        break
                    except Exception as e:
                        launch_exc = e
                        log.warn(f"Launch attempt {attempt}/{max_launch_retries} failed: {type(e).__name__}", category="ERR", silent=True)
                        if context:
                            try: await context.close()
                            except: pass
                        kill_stale_chrome()
                        remove_chrome_locks()
                        await asyncio.sleep(2 ** attempt)

                if launch_exc: 
                    raise Exception(f"Failed to launch browser after {max_launch_retries} attempts. Last error: {launch_exc}")
                
                lower_chrome_priority()

                page = context.pages[0] if context.pages else await context.new_page()
                await optimize_page(page)
                
                log.info("Loading Discord...", category="NET")
                set_tray("Loading...", "yellow")
                await page.goto(CONFIG['DISCORD_URL'], wait_until="domcontentloaded", timeout=60000)
                update_last_action("Navigated to Discord", silent=False)

                # Session Check
                if await page.locator('input[name="email"], [class*="authBox"]').count() > 0:
                    log.warn("Authentication required.", category="NET")
                    set_tray("Waiting for login", "blue")
                    state.first_run_done.clear()
                    while not state.first_run_done.is_set() and not state.should_exit.is_set() and not state.force_reconnect:
                        await asyncio.sleep(1)
                    if state.should_exit.is_set() or state.force_reconnect: 
                        if state.force_reconnect: continue
                        break
                        
                    await page.goto(CONFIG['DISCORD_URL'], wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(5)

                # Join Voice Sequence
                set_tray("Connecting...", "yellow")
                connected = False
                for attempt in range(1, CONFIG['MAX_JOIN_RETRIES'] + 1):
                    while state.paused and not state.should_exit.is_set() and not state.force_reconnect:
                        await asyncio.sleep(1)
                    if state.should_exit.is_set() or state.force_reconnect: break

                    log.info(f"Join attempt {attempt}", category="NET", silent=True)
                    try:
                        # Improved selector that is robust to translation and DOM changes
                        btn = page.locator('button:has-text("Join Voice"), [role="button"][aria-label*="join" i], button[class*="joinBtn"]').first
                        await btn.click(timeout=3000)
                        await page.locator('[aria-label="Disconnect"]').first.wait_for(state="visible", timeout=8000)
                        connected = True
                        update_last_action("Joined Voice Channel", silent=False)
                        break
                    except PlaywrightTimeoutError:
                        await asyncio.sleep(min(3 * (2 ** (attempt - 1)), 60))
                    except PlaywrightError as e:
                        if "Target page, context or browser has been closed" in str(e) or "Browser closed" in str(e):
                            raise e

                if state.should_exit.is_set(): break
                if state.force_reconnect: continue # restarts the outer while loop
                if not connected:
                    raise Exception("Exhausted voice join retries")

                # Hardware Toggles
                try:
                    await page.locator('[aria-label="Turn On Camera"]').first.click(timeout=3000)
                except Exception: pass
                
                ui = await safe_eval(page, MONITOR_JS)
                if ui and ui.get('micUnmuted'):
                    await safe_eval(page, CLICK_MIC_JS)

                # Minimize
                _find_chrome_hwnd()
                if state.browser_hwnd:
                    ctypes.windll.user32.ShowWindow(state.browser_hwnd, 6)
                    state.browser_hidden = True

                set_tray("Connected", "green")
                state.restart_count = 0
                log.ok("Monitoring active", category="SYS")

                poll, errs, reload_fails = 0, 0, 0

                # ── Monitoring Loop ──
                while not state.should_exit.is_set():
                    if state.force_reconnect:
                        log.info("Force reconnecting...", category="USR")
                        break
                    
                    while state.paused and not state.should_exit.is_set() and not state.force_reconnect:
                        await asyncio.sleep(1)
                    if state.should_exit.is_set() or state.force_reconnect: break

                    await asyncio.sleep(CONFIG['POLL_INTERVAL'])
                    poll += 1

                    try:
                        if page.is_closed():
                            raise PlaywrightError("Page closed")
                            
                        ui = await safe_eval(page, MONITOR_JS)
                    except PlaywrightError as e:
                        log.error(f"Browser connection lost: {e}", category="ERR")
                        break # break monitor loop, triggers clean restart

                    if ui is None:
                        errs += 1
                        if errs >= CONFIG['MAX_CONSECUTIVE_ERRS']:
                            try:
                                log.warn("Page unresponsive. Reloading...", category="SYS")
                                await page.reload(wait_until="domcontentloaded", timeout=30000)
                                errs = 0
                                update_last_action("Reloaded Unresponsive Page")
                            except Exception:
                                reload_fails += 1
                                if reload_fails >= CONFIG['MAX_RELOAD_FAILS']: 
                                    log.error("Failed to reload page. Restarting context...", category="ERR")
                                    break
                        continue
                    
                    errs = 0
                    if poll % CONFIG['HEALTH_LOG_EVERY'] == 0:
                        log.info(f"Health Check - Voice: {'Drop' if ui['joinVisible'] else 'OK'} | Cam: {'Off' if ui['camOff'] else 'On'} | Mic: {'Unmuted' if ui['micUnmuted'] else 'Muted'}", category="SYS", silent=True)

                    if ui['joinVisible']:
                        log.error("Voice dropped.", category="NET")
                        update_last_action("Voice Disconnected", silent=False)
                        break
                    if ui['camOff']:
                        try: await page.locator('[aria-label="Turn On Camera"]').first.click(timeout=3000)
                        except Exception: pass
                    if ui['micUnmuted']:
                        await safe_eval(page, CLICK_MIC_JS)

            except Exception as e:
                err_msg = str(e)
                log.error(f"Critical Loop Error: {err_msg}", category="ERR")
                if "Target page, context or browser has been closed" not in err_msg and "Browser closed" not in err_msg:
                    logger.error(traceback.format_exc())
                set_tray("Error", "darkred")
            
            finally:
                if context:
                    try: await context.close()
                    except Exception: pass
                
                if not state.should_exit.is_set() and not state.force_reconnect:
                    state.restart_count += 1
                    delay = min(CONFIG['RESTART_DELAY'] * (2 ** (state.restart_count - 1)), 300)
                    update_last_action(f"Backoff Wait ({delay}s)", silent=True)
                    
                    # Wait handle pause & force_reconnect during backoff
                    wait_until = time.time() + delay
                    while time.time() < wait_until and not state.should_exit.is_set():
                        if state.force_reconnect: break
                        await asyncio.sleep(1)

def run_asyncio_loop():
    try: asyncio.run(automation_loop())
    except Exception as e: logger.error(traceback.format_exc())

# ── Instance Locking & Boot ──────────────────────────────────────────────────
def acquire_lock():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                os.kill(int(f.read().strip()), 0)
            sys.exit(1)
        except Exception: pass
    with open(LOCK_FILE, 'w') as f: f.write(str(os.getpid()))

if __name__ == "__main__":
    acquire_lock()
    register_startup()
    log.info(f"App Started. Config loaded from {CONFIG_FILE}", category="SYS")

    auto_thread = threading.Thread(target=run_asyncio_loop, daemon=True)
    auto_thread.start()

    try:
        icon = pystray.Icon("DiscordAutoJoin", _get_icon("gray"), "Auto-Join: Initializing", _build_menu())
        icon.run()
    finally:
        state.should_exit.set()
        auto_thread.join(timeout=10)
        if os.path.exists(LOCK_FILE): os.remove(LOCK_FILE)
        if state.is_restarting: subprocess.Popen([sys.executable] + sys.argv)