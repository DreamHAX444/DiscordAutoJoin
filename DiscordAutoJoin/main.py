import os, sys, ctypes, logging, asyncio, threading, winreg, traceback, shutil, subprocess, re
from logging.handlers import RotatingFileHandler
from PIL import Image, ImageDraw
import pystray
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# ── Constants ────────────────────────────────────────────────────────────────
DISCORD_URL = "https://discord.com/channels/1436354443636379732/1436354444462784625"
MAX_JOIN_RETRIES = 30
POLL_INTERVAL = 2
RESTART_DELAY = 5
HEALTH_LOG_EVERY = 60       # log full status every N polls
MAX_CONSECUTIVE_ERRS = 3    # poll errors before attempting page reload
MAX_RELOAD_FAILS = 2        # failed reloads before full browser restart

CHROME_ARGS = [
    # Anti-detection
    '--disable-blink-features=AutomationControlled',
    # Disable unused subsystems
    '--disable-extensions',
    '--disable-default-apps',
    '--disable-sync',
    '--disable-breakpad',
    '--disable-crash-reporter',
    '--disable-logging',
    '--no-default-browser-check',
    '--disable-client-side-phishing-detection',
    '--disable-domain-reliability',
    '--disable-speech-api',
    '--disable-component-update',
    '--disable-component-extensions-with-background-pages',
    '--disable-hang-monitor',
    '--disable-prompt-on-repost',
    '--disable-ipc-flooding-protection',
    '--disable-dev-tools',
    '--metrics-recording-only',
    # Prevent background throttling (critical for voice stability)
    '--disable-background-timer-throttling',
    '--disable-renderer-backgrounding',
    '--disable-backgrounding-occluded-windows',
    '--disable-background-mode',
    # Memory & GPU optimization
    '--no-sandbox',
    '--disable-gpu',
    '--disable-gpu-compositing',
    '--disable-software-rasterizer',
    '--disable-dev-shm-usage',
    '--disable-site-isolation-trials',
    '--disable-canvas-aa',
    '--disable-2d-canvas-clip-aa',
    '--disable-gl-drawing-for-tests',
    '--disable-webgl',
    '--js-flags=--max-old-space-size=128',
    '--disk-cache-size=1',
    '--disable-notifications',
    '--disable-popup-blocking',
    # Process & renderer optimization
    '--renderer-process-limit=1',
    '--disable-gpu-sandbox',
    '--disable-accelerated-2d-canvas',
    '--disable-accelerated-video-decode',
    '--disable-print-preview',
    '--disable-spell-checking',
    '--disable-translate',
    '--disable-web-security',
    '--disable-dinosaur-easter-egg',
    '--no-pings',
    '--no-first-run',
    '--no-zygote',
    '--disable-partial-raster',
    '--disable-skia-runtime-opts',
    '--media-cache-size=1',
    '--disable-features=IsolateOrigins,site-per-process,Translate,'
        'OptimizationHints,MediaRouter,DialMediaRouteProvider,'
        'CalculateNativeWinOcclusion,InterestFeedContentSuggestions,'
        'CertificateTransparencyComponentUpdater,AutofillServerCommunication,'
        'PrivacySandboxSettings4,BackForwardCache,GlobalMediaControls,'
        'HeavyAdIntervention,PreloadMediaEngagementData,WebOTP,IdleDetection,'
        'WebUSB,WebBluetooth,DirectSockets,InstalledApp,WebPayments,'
        'FontAccess,ComputePressure,DigitalGoods,WindowPlacement',
    '--enable-features=ReducedReferrerGranularity',
    '--start-maximized',
]

# Domains to block (analytics, tracking, telemetry — saves bandwidth & CPU)
BLOCKED_DOMAINS = re.compile(
    r'(sentry\.io|google-analytics|googletagmanager|doubleclick|'
    r'newrelic|datadoghq|cdn\.discordapp\.com/attachments|'
    r'media\.discordapp\.net|images-ext)',
    re.IGNORECASE
)

# CSS injected to kill all animations/transitions (huge CPU saver when minimized)
OPTIMIZE_CSS = '''
*, *::before, *::after {
    animation-duration: 0s !important;
    animation-delay: 0s !important;
    transition-duration: 0s !important;
    transition-delay: 0s !important;
}
[class*="gif"], [class*="avatar"] img:not([class*="voice"]) {
    visibility: hidden !important;
}
'''

APP_DATA_DIR = os.path.join(os.environ["APPDATA"], "DiscordAutoJoin")
CHROME_PROFILE_DIR = os.path.join(APP_DATA_DIR, "ChromeProfile")
LOG_FILE = os.path.join(APP_DATA_DIR, "app.log")
LOCK_FILE = os.path.join(APP_DATA_DIR, "app.lock")
os.makedirs(APP_DATA_DIR, exist_ok=True)

# ── Logger ───────────────────────────────────────────────────────────────────
logger = logging.getLogger("DiscordAutoJoin")
logger.setLevel(logging.DEBUG)
_fmt = logging.Formatter('[%(asctime)s] %(levelname)-8s  %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
_fh = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(_fmt)
logger.addHandler(_fh)


class Console:
    """Minimal log proxy — prints to stdout and writes to rotating file."""
    @staticmethod
    def info(msg):
        print(f"INFO: {msg}", flush=True); logger.info(msg)

    @staticmethod
    def ok(msg):
        print(f"  OK: {msg}", flush=True); logger.info(msg)

    @staticmethod
    def warn(msg):
        print(f"WARN: {msg}", flush=True); logger.warning(msg)

    @staticmethod
    def error(msg):
        print(f" ERR: {msg}", flush=True); logger.error(msg)

log = Console

# ── Global State ─────────────────────────────────────────────────────────────
class AppState:
    def __init__(self):
        self.status = "Initializing"
        self.first_run_done = threading.Event()
        self.should_exit = threading.Event()
        self.browser_hwnd = None
        self.browser_hidden = False
        self.is_restarting = False
        self.restart_count = 0          # consecutive restarts (for backoff)

state = AppState()
icon = None

# ── Tray Icon ────────────────────────────────────────────────────────────────
_icon_cache = {}

def _get_icon(color):
    if color not in _icon_cache:
        img = Image.new('RGB', (64, 64), (0, 0, 0))
        ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=color)
        _icon_cache[color] = img
    return _icon_cache[color]

def _build_menu():
    items = [
        pystray.MenuItem("Show/Hide Chrome", _toggle_browser),
        pystray.MenuItem("View Log", lambda *_: os.startfile(LOG_FILE)),
    ]
    if state.status == "Waiting for login":
        items.append(pystray.MenuItem("Login Done", _on_login_done))
    items.extend([
        pystray.MenuItem("Restart", _restart_app),
        pystray.MenuItem("Exit", _exit_app),
    ])
    return pystray.Menu(*items)

def set_tray(status, color):
    state.status = status
    if icon:
        icon.icon = _get_icon(color)
        icon.title = f"Auto-Join: {status}"
        icon.menu = _build_menu()

# ── Tray Actions ─────────────────────────────────────────────────────────────
def _on_login_done(*_):
    log.ok("User confirmed login")
    state.first_run_done.set()
    set_tray("Connecting...", "yellow")

def _toggle_browser(*_):
    if not state.browser_hwnd:
        _find_chrome_hwnd()
    if not state.browser_hwnd:
        return
    if state.browser_hidden:
        ctypes.windll.user32.ShowWindow(state.browser_hwnd, 9)
        state.browser_hidden = False
    else:
        ctypes.windll.user32.ShowWindow(state.browser_hwnd, 6)
        state.browser_hidden = True

def _restart_app(*_):
    log.info("Restarting...")
    state.is_restarting = True
    state.should_exit.set()
    if icon: icon.stop()

def _exit_app(*_):
    log.info("Exiting...")
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
    ref = WNDENUMPROC(cb)
    ctypes.windll.user32.EnumWindows(ref, 0)
    if hwnds:
        state.browser_hwnd = hwnds[0]

# ── Startup Registration ────────────────────────────────────────────────────
def register_startup():
    script = os.path.abspath(sys.argv[0])
    if getattr(sys, 'frozen', False):
        cmd = f'"{sys.executable}"'
    else:
        pw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.exists(pw):
            pw = sys.executable
        cmd = f'"{pw}" "{script}"'

    # Method 1: Registry
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE | winreg.KEY_READ)
        try:
            val, _ = winreg.QueryValueEx(key, "DiscordAutoJoin")
            if val == cmd:
                winreg.CloseKey(key)
                log.ok("Registry startup OK")
                key = None
        except FileNotFoundError:
            pass
        if key:
            winreg.SetValueEx(key, "DiscordAutoJoin", 0, winreg.REG_SZ, cmd)
            winreg.CloseKey(key)
            log.ok("Registry startup set")
    except Exception as e:
        log.warn(f"Registry startup failed: {e}")

    # Method 2: VBS in Startup folder
    try:
        vbs_target = cmd.replace('"', '""')
        vbs_content = f'CreateObject("WScript.Shell").Run "{vbs_target}", 0, False\n'
        vbs_path = os.path.join(APP_DATA_DIR, "DiscordAutoJoin.vbs")
        needs_write = True
        if os.path.exists(vbs_path):
            with open(vbs_path, "r") as f:
                needs_write = f.read() != vbs_content
        if needs_write:
            with open(vbs_path, "w") as f:
                f.write(vbs_content)
        dest = os.path.join(
            os.environ["APPDATA"],
            r"Microsoft\Windows\Start Menu\Programs\Startup",
            "DiscordAutoJoin.vbs")
        shutil.copy2(vbs_path, dest)
        log.ok("Startup folder OK")
    except Exception as e:
        log.warn(f"Startup folder failed: {e}")

# ── Safe Async Helpers ───────────────────────────────────────────────────────
async def safe_eval(page, js, timeout=10):
    """Run page.evaluate with an asyncio timeout guard. Returns None on failure."""
    try:
        return await asyncio.wait_for(page.evaluate(js), timeout=timeout)
    except Exception:
        return None

async def page_alive(page):
    """Quick liveness check — returns True if the page responds within 5s."""
    if page.is_closed():
        return False
    return await safe_eval(page, "1+1", timeout=5) == 2

# ── Consolidated JavaScript ──────────────────────────────────────────────────
MONITOR_JS = '''() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const joinVisible = btns.some(b =>
        b.textContent && b.textContent.includes('Join Voice')
        && b.offsetWidth > 0 && b.offsetHeight > 0);
    const camOff = !!document.querySelector('[aria-label="Turn On Camera"]');
    const micBtn = btns.find(b => {
        const l = (b.getAttribute('aria-label') || '').toLowerCase();
        return l === 'mute' || l === 'unmute' || l.includes('microphone');
    });
    let micUnmuted = false;
    if (micBtn) {
        const l = micBtn.getAttribute('aria-label').toLowerCase();
        const isMute = (l.includes('mute') && !l.includes('unmute')) || l.includes('turn off');
        if (micBtn.hasAttribute('aria-checked')) {
            micUnmuted = isMute
                ? micBtn.getAttribute('aria-checked') !== 'true'
                : micBtn.getAttribute('aria-checked') === 'true';
        } else { micUnmuted = isMute; }
    }
    return { joinVisible, camOff, micUnmuted };
}'''

CLICK_MIC_JS = '''() => {
    const mb = Array.from(document.querySelectorAll('button[aria-label]')).find(b => {
        const l = b.getAttribute('aria-label').toLowerCase();
        return l === 'mute' || l === 'unmute' || l.includes('microphone');
    });
    if (mb) mb.click();
}'''

# ── Discord Actions ──────────────────────────────────────────────────────────
async def try_join_voice(page):
    selectors = [
        ('button:has-text("Join Voice")', "text"),
        ('[role="button"][aria-label*="join" i]', "aria"),
    ]
    for css, name in selectors:
        try:
            await page.locator(css).first.click(timeout=3000)
            log.ok(f"Clicked Join Voice [{name}]")
            break
        except PlaywrightTimeoutError:
            continue
    else:
        log.warn("Join Voice button not found")
        return False

    try:
        await page.locator('[aria-label="Disconnect"]').first.wait_for(
            state="visible", timeout=8000)
        log.ok("Voice connected")
        return True
    except PlaywrightTimeoutError:
        log.warn("Connection not verified")
        return False

async def enable_camera(page):
    try:
        await page.locator('[aria-label="Turn On Camera"]').first.click(timeout=5000)
        log.ok("Camera enabled")
        return True
    except PlaywrightTimeoutError:
        log.warn("Camera button not found (non-fatal)")
        return False

async def mute_mic(page):
    result = await safe_eval(page, MONITOR_JS)
    if result and result.get('micUnmuted'):
        await safe_eval(page, CLICK_MIC_JS)
        log.ok("Microphone muted")
    else:
        log.ok("Microphone already muted")

# ── Kill Stale Chrome ────────────────────────────────────────────────────────
def kill_stale_chrome():
    try:
        name = os.path.basename(CHROME_PROFILE_DIR)
        subprocess.run(
            f"wmic process where \"name='chrome.exe' and commandline like '%{name}%'\" call terminate",
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    except Exception:
        pass

# ── Lower Chrome Priority ────────────────────────────────────────────────────
def lower_chrome_priority():
    """Set all chrome.exe processes to BELOW_NORMAL priority to save CPU."""
    try:
        subprocess.run(
            'wmic process where "name=\'chrome.exe\'" CALL setpriority "below normal"',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        log.ok("Chrome priority lowered")
    except Exception:
        pass

# ── Optimize Page ────────────────────────────────────────────────────────────
async def optimize_page(page):
    """Block junk requests and inject animation-killing CSS."""
    # Block analytics, tracking, and heavy media we don't need
    async def handle_route(route):
        if BLOCKED_DOMAINS.search(route.request.url):
            await route.abort()
        else:
            await route.continue_()
    try:
        await page.route('**/*', handle_route)
        log.ok("Request blocker active")
    except Exception:
        pass

    # Inject CSS to disable animations/transitions
    try:
        await page.add_style_tag(content=OPTIMIZE_CSS)
        log.ok("Animations disabled")
    except Exception:
        pass

# ── Close Context Safely ─────────────────────────────────────────────────────
async def close_context(ctx):
    if not ctx:
        return
    try:
        await ctx.close()
    except Exception:
        pass

# ── Main Automation Loop ─────────────────────────────────────────────────────
async def automation_loop():
    async with async_playwright() as p:
        while not state.should_exit.is_set():
            context = None
            state.browser_hwnd = None
            state.browser_hidden = False
            try:
                # ── Launch ────────────────────────────────────────
                log.info("Launching Chrome...")
                kill_stale_chrome()
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=CHROME_PROFILE_DIR,
                    channel="chrome",
                    headless=False,
                    no_viewport=True,
                    permissions=['camera', 'microphone'],
                    args=CHROME_ARGS)
                log.ok("Chrome launched")
                lower_chrome_priority()

                # ── Navigate ──────────────────────────────────────
                page = context.pages[0] if context.pages else await context.new_page()
                await optimize_page(page)
                log.info("Loading Discord...")
                await page.goto(DISCORD_URL, wait_until="domcontentloaded", timeout=60000)
                try:
                    await page.wait_for_selector('[class*="sidebar"]', timeout=15000)
                except Exception:
                    pass
                log.ok("Page loaded")

                # ── Session Check ─────────────────────────────────
                if await page.locator('input[name="email"], [class*="authBox"]').count() > 0:
                    log.warn("No session — please log in, then tray → 'Login Done'")
                    set_tray("Waiting for login", "blue")
                    state.first_run_done.clear()
                    while not state.first_run_done.is_set() and not state.should_exit.is_set():
                        await asyncio.sleep(1)
                    if state.should_exit.is_set():
                        break
                    log.ok("Login confirmed")
                    await page.goto(DISCORD_URL, wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(5)
                else:
                    log.ok("Session active")

                # ── Join Voice ────────────────────────────────────
                set_tray("Connecting...", "yellow")
                connected = False
                for attempt in range(1, MAX_JOIN_RETRIES + 1):
                    if state.should_exit.is_set():
                        break
                    log.info(f"Join attempt {attempt}/{MAX_JOIN_RETRIES}")
                    if await try_join_voice(page):
                        connected = True
                        break
                    wait = min(3 * (2 ** (attempt - 1)), 120)
                    log.warn(f"Retrying in {wait}s...")
                    await asyncio.sleep(wait)

                if not connected:
                    log.error(f"Failed to join after {MAX_JOIN_RETRIES} attempts")
                    set_tray("Error", "darkred")
                    await asyncio.sleep(30)
                    await close_context(context)
                    continue

                # ── Post-connect setup ────────────────────────────
                await mute_mic(page)
                await enable_camera(page)

                # Minimize Chrome
                _find_chrome_hwnd()
                if state.browser_hwnd:
                    ctypes.windll.user32.ShowWindow(state.browser_hwnd, 6)
                    state.browser_hidden = True
                    log.ok("Chrome minimized")

                set_tray("Connected", "green")
                state.restart_count = 0  # reset backoff on success
                log.ok("Monitoring started")

                # ── Monitor Loop ──────────────────────────────────
                poll = 0
                consecutive_errs = 0
                reload_fails = 0

                while not state.should_exit.is_set():
                    await asyncio.sleep(POLL_INTERVAL)
                    poll += 1

                    # Liveness gate
                    if not await page_alive(page):
                        log.error("Page unresponsive — restarting browser")
                        break

                    ui = await safe_eval(page, MONITOR_JS)
                    if ui is None:
                        consecutive_errs += 1
                        log.warn(f"Poll failed ({consecutive_errs}/{MAX_CONSECUTIVE_ERRS})")
                        if consecutive_errs >= MAX_CONSECUTIVE_ERRS:
                            # Try reload before full restart
                            log.warn("Attempting page reload...")
                            try:
                                await page.reload(wait_until="domcontentloaded", timeout=30000)
                                await asyncio.sleep(3)
                                consecutive_errs = 0
                                log.ok("Page reloaded")
                            except Exception:
                                reload_fails += 1
                                log.error(f"Reload failed ({reload_fails}/{MAX_RELOAD_FAILS})")
                                if reload_fails >= MAX_RELOAD_FAILS:
                                    log.error("Too many reload failures — full restart")
                                    break
                        continue

                    consecutive_errs = 0  # reset on success

                    # Health log
                    if poll % HEALTH_LOG_EVERY == 0:
                        v = "DISCONNECTED" if ui['joinVisible'] else "CONNECTED"
                        c = "OFF" if ui['camOff'] else "ON"
                        m = "UNMUTED" if ui['micUnmuted'] else "MUTED"
                        log.info(f"Poll #{poll}: voice={v} cam={c} mic={m}")

                    # Voice dropped → full restart
                    if ui['joinVisible']:
                        log.error("Voice disconnected!")
                        set_tray("Disconnected", "red")
                        break

                    # Camera off → re-enable
                    if ui['camOff']:
                        log.warn("Camera off — re-enabling")
                        try:
                            await page.locator('[aria-label="Turn On Camera"]').first.click(timeout=3000)
                            log.ok("Camera re-enabled")
                        except Exception as e:
                            log.warn(f"Camera re-enable failed: {e}")

                    # Mic unmuted → re-mute
                    if ui['micUnmuted']:
                        log.warn("Mic unmuted — re-muting")
                        await safe_eval(page, CLICK_MIC_JS)

                # ── Cleanup ───────────────────────────────────────
                await close_context(context)
                context = None

                if not state.should_exit.is_set():
                    state.restart_count += 1
                    delay = min(RESTART_DELAY * (2 ** (state.restart_count - 1)), 300)
                    log.info(f"Restarting in {delay}s (attempt #{state.restart_count})...")
                    await asyncio.sleep(delay)

            except Exception as e:
                log.error(f"Critical: {e}")
                logger.error(traceback.format_exc())
                set_tray("Error", "darkred")
                await close_context(context)
                if not state.should_exit.is_set():
                    state.restart_count += 1
                    delay = min(RESTART_DELAY * (2 ** (state.restart_count - 1)), 300)
                    log.info(f"Retrying in {delay}s...")
                    await asyncio.sleep(delay)

def run_asyncio_loop():
    try:
        asyncio.run(automation_loop())
    except Exception as e:
        log.error(f"Automation thread crashed: {e}")
        logger.error(traceback.format_exc())

# ── Single Instance Lock ─────────────────────────────────────────────────────
def acquire_lock():
    try:
        if os.path.exists(LOCK_FILE):
            try:
                with open(LOCK_FILE, 'r') as f:
                    old_pid = int(f.read().strip())
                os.kill(old_pid, 0)
                print(f"ERROR: Already running (PID {old_pid}). Delete {LOCK_FILE} if wrong.")
                sys.exit(1)
            except (OSError, ValueError):
                pass
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
    except Exception as e:
        log.warn(f"Lock file error: {e}")

def release_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception:
        pass

# ── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    acquire_lock()
    log.info(f"Starting — Python {sys.version.split()[0]}, PID {os.getpid()}")
    register_startup()

    auto_thread = threading.Thread(target=run_asyncio_loop, daemon=True)
    auto_thread.start()

    try:
        icon = pystray.Icon("DiscordAutoJoin", _get_icon("gray"), "Auto-Join: Initializing", _build_menu())
        icon.run()
    finally:
        state.should_exit.set()
        auto_thread.join(timeout=10)
        release_lock()
        log.info("Exited")
        if state.is_restarting:
            subprocess.Popen([sys.executable] + sys.argv)
