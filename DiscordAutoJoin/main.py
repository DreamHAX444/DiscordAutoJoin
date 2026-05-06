import os, sys, ctypes, logging, asyncio, threading, winreg, traceback, shutil, signal
from datetime import datetime
from logging.handlers import RotatingFileHandler
from PIL import Image, ImageDraw
import pystray
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DISCORD_URL = "https://discord.com/channels/1436354443636379732/1436354444462784625"
MAX_RETRIES = 30
RETRY_INTERVAL = 3
POLL_INTERVAL = 1
PAGE_CRASH_DELAY = 5
CHROME_ARGS = [
    '--disable-blink-features=AutomationControlled',
    '--disable-extensions',
    '--disable-default-apps',
    '--disable-background-timer-throttling',
    '--disable-renderer-backgrounding',
    '--disable-backgrounding-occluded-windows',
    '--disable-background-mode',
    '--no-sandbox',
    '--disable-gpu',
    # Memory optimization flags
    '--disable-dev-shm-usage',
    '--disable-site-isolation-trials',
    '--disable-features=IsolateOrigins,site-per-process,Translate,OptimizationHints,MediaRouter,DialMediaRouteProvider,CalculateNativeWinOcclusion,InterestFeedContentSuggestions,CertificateTransparencyComponentUpdater,AutofillServerCommunication,PrivacySandboxSettings4',
    '--disable-software-rasterizer',
    '--js-flags="--max-old-space-size=128"',
    '--disable-logging',
    '--disable-breakpad',
    '--disable-ipc-flooding-protection',
    '--disable-sync',
    '--disable-hang-monitor',
    '--disable-prompt-on-repost',
    '--start-maximized',
    # Extreme optimizations
    '--disable-dev-tools',
    '--no-default-browser-check',
    '--disable-client-side-phishing-detection',
    '--disable-crash-reporter',
    '--disable-domain-reliability',
    '--disable-speech-api',
    '--metrics-recording-only',
    '--disable-component-update',
    '--disable-component-extensions-with-background-pages',
    '--disk-cache-size=1',
    # Nuclear optimizations
    '--disable-gpu-compositing',
    '--disable-canvas-aa',
    '--disable-2d-canvas-clip-aa',
    '--disable-gl-drawing-for-tests',
    '--disable-webgl',
]

APP_DATA_DIR = os.path.join(os.environ["APPDATA"], "DiscordAutoJoin")
CHROME_PROFILE_DIR = os.path.join(APP_DATA_DIR, "ChromeProfile")
LOG_FILE = os.path.join(APP_DATA_DIR, "app.log")
LOCK_FILE = os.path.join(APP_DATA_DIR, "app.lock")
os.makedirs(APP_DATA_DIR, exist_ok=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# File Logger (must be created BEFORE Console class)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
logger = logging.getLogger("DiscordAutoJoin")
logger.setLevel(logging.DEBUG)
_fmt = logging.Formatter('[%(asctime)s] %(levelname)-8s  %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
_fh = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(_fmt)
logger.addHandler(_fh)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Console Printer (Simplified)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class Console:
    """Standard terminal output logger proxy."""
    @staticmethod
    def info(msg):
        print(f"INFO: {msg}", flush=True)
        logger.info(msg)

    @staticmethod
    def ok(msg):
        print(f"OK: {msg}", flush=True)
        logger.info(msg)

    @staticmethod
    def warn(msg):
        print(f"WARN: {msg}", flush=True)
        logger.warning(msg)

    @staticmethod
    def error(msg):
        print(f"ERROR: {msg}", flush=True)
        logger.error(msg)

    @staticmethod
    def step(msg):
        print(f"STEP: {msg}", flush=True)
        logger.info(msg)

    @staticmethod
    def detail(msg):
        print(f"DETAIL: {msg}", flush=True)
        logger.debug(msg)

    @staticmethod
    def status(voice="--", camera="--", poll="--"):
        print(f"MONITOR poll #{poll} voice: {voice} camera: {camera}", flush=True)
        logger.info(f"Monitor #{poll}: voice={voice}, camera={camera}")

    @staticmethod
    def divider(label=""):
        if label:
            print(f"\n--- {label} ---", flush=True)
        else:
            print("----------------------------------------------------------", flush=True)

log = Console




# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Global State
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class AppState:
    def __init__(self):
        self.status = "Initializing"
        self.first_run_done = threading.Event()
        self.should_exit = threading.Event()
        self.browser_hwnd = None
        self.browser_hidden = False
        self.is_restarting = False

state = AppState()
icon = None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tray Icon (cached to avoid regenerating PIL images every update)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_icon_cache = {}

def get_icon_image(color):
    if color not in _icon_cache:
        img = Image.new('RGB', (64, 64), color=(0, 0, 0))
        ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=color)
        _icon_cache[color] = img
    return _icon_cache[color]

def _build_menu():
    items = [
        pystray.MenuItem("Show/Hide Chrome", toggle_browser),
        pystray.MenuItem("View Log File", view_logs),
    ]
    if state.status == "Waiting for login":
        items.append(pystray.MenuItem("First-Run Done", on_done_first_run))
    items.extend([
        pystray.MenuItem("Restart", restart_app),
        pystray.MenuItem("Exit", exit_app)
    ])
    return pystray.Menu(*items)

def update_tray_status(status_str, color):
    state.status = status_str
    if icon is not None:
        icon.icon = get_icon_image(color)
        icon.title = f"Auto-Join: {status_str}"
        icon.menu = _build_menu()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tray Menu Actions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def on_done_first_run(icon_ref, item):
    log.ok("User confirmed login via tray menu")
    state.first_run_done.set()
    update_tray_status("Connecting...", "yellow")

def find_browser_window():
    hwnds = []
    buff = ctypes.create_unicode_buffer(260)
    def enum_cb(hwnd, lParam):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0 and length < 260:
                ctypes.windll.user32.GetWindowTextW(hwnd, buff, 260)
                title = buff.value
                # Playwright Chrome title can be just the page title without "Chrome"
                if "Discord" in title or ("discord.com" in title.lower()):
                    hwnds.append(hwnd)
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    _cb_ref = WNDENUMPROC(enum_cb)  # prevent garbage collection during call
    ctypes.windll.user32.EnumWindows(_cb_ref, 0)
    if hwnds:
        state.browser_hwnd = hwnds[0]
        return hwnds[0]
    return None

def toggle_browser(icon_ref, item):
    if not state.browser_hwnd:
        find_browser_window()
        if not state.browser_hwnd:
            log.warn("Could not find Chrome window")
            return
    if state.browser_hidden:
        ctypes.windll.user32.ShowWindow(state.browser_hwnd, 9)
        state.browser_hidden = False
        log.info("Chrome window restored")
    else:
        ctypes.windll.user32.ShowWindow(state.browser_hwnd, 6)
        state.browser_hidden = True
        log.info("Chrome window minimized")

def view_logs(icon_ref, item):
    os.startfile(LOG_FILE)

def restart_app(icon_ref, item):
    log.info("Restarting application...")
    state.is_restarting = True
    state.should_exit.set()
    if icon: icon.stop()

def exit_app(icon_ref, item):
    log.info("Exiting application...")
    state.should_exit.set()
    if icon: icon.stop()

def setup_tray():
    global icon
    icon = pystray.Icon("DiscordAutoJoin", get_icon_image("gray"), "Auto-Join: Initializing", _build_menu())
    icon.run()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Startup Registration (Registry + Startup Folder)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _get_startup_command():
    """Build the correct command to launch this app on boot."""
    script_path = os.path.abspath(sys.argv[0])

    if getattr(sys, 'frozen', False):
        # Running as compiled .exe (PyInstaller)
        return f'"{sys.executable}"'
    else:
        # Running as .py script — use pythonw.exe (no console window on boot)
        python_dir = os.path.dirname(sys.executable)
        pythonw = os.path.join(python_dir, "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = sys.executable  # fallback to python.exe
        return f'"{pythonw}" "{script_path}"'


def _create_vbs_launcher():
    """Create a silent VBS launcher so the app starts without a console flash."""
    script_path = os.path.abspath(sys.argv[0])
    vbs_path = os.path.join(APP_DATA_DIR, "DiscordAutoJoin.vbs")

    if getattr(sys, 'frozen', False):
        # .exe — just run it directly
        target = f'"{sys.executable}"'
    else:
        python_dir = os.path.dirname(sys.executable)
        pythonw = os.path.join(python_dir, "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = sys.executable  # fallback to python.exe
        target = f'"{pythonw}" "{script_path}"'

    target_vbs = target.replace('"', '""')
    vbs_content = f'CreateObject("WScript.Shell").Run "{target_vbs}", 0, False\n'

    if os.path.exists(vbs_path):
        with open(vbs_path, "r") as f:
            if f.read() == vbs_content:
                return vbs_path

    with open(vbs_path, "w") as f:
        f.write(vbs_content)

    return vbs_path


def register_startup():
    """Register app to run at Windows startup via Registry AND Startup folder."""
    log.step("Registering for Windows startup...")
    success_count = 0

    # ── Method 1: Registry ────────────────────────────────────────
    try:
        cmd = _get_startup_command()
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE | winreg.KEY_READ
        )
        already_matches = False
        try:
            existing_val, _ = winreg.QueryValueEx(key, "DiscordAutoJoin")
            if existing_val == cmd:
                already_matches = True
        except FileNotFoundError:
            pass

        if already_matches:
            log.ok("Registry entry already registered")
            winreg.CloseKey(key)
            success_count += 1
        else:
            winreg.SetValueEx(key, "DiscordAutoJoin", 0, winreg.REG_SZ, cmd)

            # Verify it was written correctly
            stored_val, _ = winreg.QueryValueEx(key, "DiscordAutoJoin")
            winreg.CloseKey(key)

            if stored_val == cmd:
                log.ok("Registry entry created and verified")
                log.detail(f"HKCU\\...\\Run\\DiscordAutoJoin = {cmd}")
                success_count += 1
            else:
                log.warn("Registry entry written but verification mismatch")
    except Exception as e:
        log.error(f"Registry method failed: {e}")

    # ── Method 2: Startup Folder (backup) ─────────────────────────
    try:
        vbs_path = _create_vbs_launcher()
        startup_folder = os.path.join(
            os.environ["APPDATA"],
            r"Microsoft\Windows\Start Menu\Programs\Startup"
        )

        dest = os.path.join(startup_folder, "DiscordAutoJoin.vbs")
        shutil.copy2(vbs_path, dest)
        log.ok("Startup folder shortcut created")
        log.detail(f"VBS launcher → {dest}")
        success_count += 1
    except Exception as e:
        log.error(f"Startup folder method failed: {e}")

    # ── Summary ───────────────────────────────────────────────────
    if success_count == 2:
        log.ok("Startup registered via both methods (redundant)")
    elif success_count == 1:
        log.ok("Startup registered via one method")
    else:
        log.error("Failed to register startup — app won't auto-start")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Join Voice
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def try_join_voice(page):
    selectors = [
        ('button:has-text("Join Voice")',          "text-match"),
        ('[role="button"][aria-label*="join" i]',   "aria-label"),
    ]
    clicked = False
    for css, name in selectors:
        try:
            loc = page.locator(css)
            await loc.first.click(timeout=3000)
            log.ok(f"Clicked Join Voice via [{name}]")
            clicked = True
            break
        except PlaywrightTimeoutError:
            continue

    if not clicked:
        log.warn("Join Voice button not found")
        return False

    log.info("Waiting for voice connection to establish...")
    try:
        await page.locator('[aria-label="Disconnect"]').first.wait_for(state="visible", timeout=8000)
        log.ok("Voice connection verified")
        return True
    except PlaywrightTimeoutError:
        log.warn("Clicked button but connection not verified")
        return False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Enable Camera
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def enable_camera(page):
    selectors = [
        '[aria-label="Turn On Camera"]',
        'button[class*="button"]:has([class*="camera"])',
    ]
    for css in selectors:
        try:
            await page.locator(css).first.click(timeout=5000)
            log.ok("Camera enabled")
            return True
        except PlaywrightTimeoutError:
            continue
    log.warn("Could not enable camera (non-fatal)")
    return False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Mute Microphone
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def mute_mic(page):
    """Mute the microphone if it's currently unmuted."""
    is_unmuted = await page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('button[aria-label]'));
        const mb = btns.find(b => {
            const l = b.getAttribute('aria-label').toLowerCase();
            return l === 'mute' || l === 'unmute' || l.includes('microphone');
        });
        if (!mb) return false;
        
        const label = mb.getAttribute('aria-label').toLowerCase();
        const isMuteLabel = (label.includes('mute') && !label.includes('unmute')) || label.includes('turn off');
        const isSwitch = mb.hasAttribute('aria-checked');
        
        if (isSwitch) {
            return isMuteLabel ? mb.getAttribute('aria-checked') !== 'true' : mb.getAttribute('aria-checked') === 'true';
        }
        return isMuteLabel;
    }''')
    
    if is_unmuted:
        try:
            # Click whatever button we evaluated
            await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button[aria-label]'));
                const mb = btns.find(b => {
                    const l = b.getAttribute('aria-label').toLowerCase();
                    return l === 'mute' || l === 'unmute' || l.includes('microphone');
                });
                if (mb) mb.click();
            }''')
            log.ok("Microphone muted")
            return True
        except Exception:
            pass
    else:
        log.ok("Microphone already muted")
        return True
        
    log.warn("Could not verify mic status (non-fatal)")
    return False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main Automation Loop
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def automation_loop():
    async with async_playwright() as p:
        while not state.should_exit.is_set():
            state.browser_hwnd = None
            state.browser_hidden = False
            context = None
            try:
                # ── Launch ───────────────────────────────────────────
                log.divider("LAUNCHING BROWSER")
                log.step("Starting Google Chrome...")
                try:
                    import subprocess
                    cmd = f'wmic process where "name=\'chrome.exe\' and commandline like \'%{os.path.basename(CHROME_PROFILE_DIR)}%\'" call terminate'
                    subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=CHROME_PROFILE_DIR,
                    channel="chrome",
                    headless=False,
                    no_viewport=True,  # fill the maximized window
                    permissions=['camera', 'microphone'],
                    args=CHROME_ARGS
                )
                log.ok("Chrome launched")

                # ── Navigate ─────────────────────────────────────────
                log.divider("NAVIGATING")
                # Reuse the default tab that persistent context opens (avoids duplicate tabs)
                if context.pages:
                    page = context.pages[0]
                else:
                    page = await context.new_page()

                log.info("Loading Discord channel...")
                # Use domcontentloaded — Discord uses WebSockets so networkidle hangs forever
                await page.goto(DISCORD_URL, wait_until="domcontentloaded", timeout=60000)
                log.info("DOM loaded, waiting for Discord app to render...")
                try:
                    await page.wait_for_selector('[class*="sidebar"]', timeout=15000)
                except Exception:
                    pass
                log.ok("Page loaded")

                # ── Session Check ────────────────────────────────────
                log.divider("SESSION CHECK")
                login_btn = page.locator('input[name="email"], [class*="authBox"]')
                if await login_btn.count() > 0:
                    log.warn("No saved session detected")
                    log.info("Please log into Discord in the Chrome window")
                    log.info("Then right-click tray icon → 'First-Run Done'")
                    update_tray_status("Waiting for login", "blue")
                    state.first_run_done.clear()
                    while not state.first_run_done.is_set() and not state.should_exit.is_set():
                        await asyncio.sleep(1)
                    if state.should_exit.is_set(): break
                    log.ok("Login confirmed — resuming")
                    await page.goto(DISCORD_URL, wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(5)
                else:
                    log.ok("Session active — logged in")

                # ── Join Voice ───────────────────────────────────────
                log.divider("JOINING VOICE")
                update_tray_status("Connecting...", "yellow")
                connected = False
                
                async def _join_voice_loop():
                    for attempt in range(1, MAX_RETRIES + 1):
                        if state.should_exit.is_set(): break
                        log.step(f"Attempt {attempt}/{MAX_RETRIES}")
                        if await try_join_voice(page):
                            return True
                        wait_time = min(RETRY_INTERVAL * (2 ** (attempt - 1)), 120)
                        log.warn(f"Failed — retrying in {wait_time}s")
                        await asyncio.sleep(wait_time)
                    return False

                try:
                    total_timeout = MAX_RETRIES * (RETRY_INTERVAL + 10)
                    connected = await asyncio.wait_for(_join_voice_loop(), timeout=total_timeout)
                except (asyncio.TimeoutError, TimeoutError):
                    log.error(f"Join voice sequence exceeded {total_timeout}s total timeout")
                    connected = False

                if not connected:
                    log.error(f"Could not join voice after {MAX_RETRIES} attempts or timeout")
                    update_tray_status("Error", "darkred")
                    await asyncio.sleep(30)
                    if context: await context.close()
                    continue

                # ── Mute Mic ─────────────────────────────────────────
                log.divider("MICROPHONE")
                await mute_mic(page)

                # ── Camera ───────────────────────────────────────────
                log.divider("CAMERA")
                await enable_camera(page)

                # ── Minimize ─────────────────────────────────────────
                find_browser_window()
                if state.browser_hwnd:
                    ctypes.windll.user32.ShowWindow(state.browser_hwnd, 6)
                    state.browser_hidden = True
                    log.ok("Chrome minimized to taskbar")

                # ── Connected ────────────────────────────────────────
                log.divider("CONNECTED")
                update_tray_status("Connected", "green")
                log.ok("All systems go — monitoring started")
                log.detail(f"Polling every {POLL_INTERVAL}s for voice + camera status")

                # ── Monitor ──────────────────────────────────────────
                poll = 0
                while not state.should_exit.is_set():
                    await asyncio.sleep(POLL_INTERVAL)
                    poll += 1
                    try:
                        if page.is_closed():
                            raise Exception("Page closed")

                        # Batch DOM queries
                        ui_state = await page.evaluate('''() => {
                            const joinBtns = Array.from(document.querySelectorAll('button')).filter(b => b.textContent && b.textContent.includes('Join Voice'));
                            const jb_visible = joinBtns.some(b => b.offsetWidth > 0 && b.offsetHeight > 0);
                            
                            const cb = document.querySelector('[aria-label="Turn On Camera"]');
                            
                            const btns = Array.from(document.querySelectorAll('button[aria-label]'));
                            const mb = btns.find(b => {
                                const l = b.getAttribute('aria-label').toLowerCase();
                                return l === 'mute' || l === 'unmute' || l.includes('microphone');
                            });
                            
                            let mic_unmuted = false;
                            if (mb) {
                                const label = mb.getAttribute('aria-label').toLowerCase();
                                const isMuteLabel = (label.includes('mute') && !label.includes('unmute')) || label.includes('turn off');
                                const isSwitch = mb.hasAttribute('aria-checked');
                                if (isSwitch) {
                                    mic_unmuted = isMuteLabel ? mb.getAttribute('aria-checked') !== 'true' : mb.getAttribute('aria-checked') === 'true';
                                } else {
                                    mic_unmuted = isMuteLabel;
                                }
                            }
                            
                            return {
                                jv: jb_visible,
                                cam_off: cb !== null,
                                mic_unmuted: mic_unmuted
                            };
                        }''')
                        jv = ui_state['jv']
                        cam_off = ui_state['cam_off']
                        mic_unmuted = ui_state['mic_unmuted']

                        cb = page.locator('[aria-label="Turn On Camera"]')

                        # Status report every ~60s
                        if poll % 60 == 0:
                            mic_str = "UNMUTED" if mic_unmuted else "MUTED"
                            log.status(
                                voice="DISCONNECTED" if jv else "CONNECTED",
                                camera="OFF" if cam_off else "ON",
                                poll=str(poll)
                            )
                            log.detail(f"mic: {mic_str}")

                        # Voice dropped
                        if jv:
                            log.divider("DISCONNECTION DETECTED")
                            log.error("Voice connection lost!")
                            update_tray_status("Disconnected", "red")
                            break

                        # Camera dropped — re-enable silently
                        if cam_off:
                            log.warn("Camera turned off — re-enabling")
                            try:
                                await cb.first.click()
                                log.ok("Camera re-enabled")
                            except Exception as e:
                                log.warn(f"Camera re-enable failed: {e}")

                        # Mic unmuted — re-mute silently
                        if mic_unmuted:
                            log.warn("Mic is unmuted — re-muting")
                            try:
                                await page.evaluate('''() => {
                                    const btns = Array.from(document.querySelectorAll('button[aria-label]'));
                                    const mb = btns.find(b => {
                                        const l = b.getAttribute('aria-label').toLowerCase();
                                        return l === 'mute' || l === 'unmute' || l.includes('microphone');
                                    });
                                    if (mb) mb.click();
                                }''')
                                log.ok("Mic re-muted")
                            except Exception as e:
                                log.warn(f"Mic re-mute failed: {e}")

                    except Exception as e:
                        log.error(f"Monitor error: {e}")
                        logger.debug(traceback.format_exc())
                        break

                # ── Cleanup ──────────────────────────────────────────
                if context:
                    log.info("Closing browser...")
                    try:
                        browser = context.browser
                        await context.close()
                        if browser:
                            await browser.close()
                    except Exception as e:
                        log.warn(f"Error during context close: {e}")
                    finally:
                        context = None
                if not state.should_exit.is_set():
                    log.info(f"Restarting in {PAGE_CRASH_DELAY}s...")
                    await asyncio.sleep(PAGE_CRASH_DELAY)

            except Exception as e:
                log.error(f"Critical error: {e}")
                logger.error(traceback.format_exc())
                update_tray_status("Error", "darkred")
                if context:
                    try: 
                        browser = context.browser
                        await context.close()
                        if browser:
                            await browser.close()
                    except Exception: 
                        pass
                if not state.should_exit.is_set():
                    log.info(f"Retrying in {PAGE_CRASH_DELAY}s...")
                    await asyncio.sleep(PAGE_CRASH_DELAY)

def run_asyncio_loop():
    try:
        asyncio.run(automation_loop())
    except Exception as e:
        log.error(f"Automation thread crashed: {e}")
        logger.error(traceback.format_exc())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Single Instance Lock
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def acquire_lock():
    """Prevent multiple instances from running simultaneously."""
    try:
        # Try to create lock file exclusively
        if os.path.exists(LOCK_FILE):
            # Check if the PID inside is still alive
            try:
                with open(LOCK_FILE, 'r') as f:
                    old_pid = int(f.read().strip())
                # Check if process is still running
                os.kill(old_pid, 0)  # doesn't kill, just checks
                # Process is alive — another instance is running
                print(f"ERROR: Another instance is already running (PID {old_pid}).")
                print(f"Delete {LOCK_FILE} if this is wrong.")
                sys.exit(1)
            except (OSError, ValueError):
                pass  # process is dead or file is corrupt, take over
        # Write our PID
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
    except Exception as e:
        log.warn(f"Could not create lock file: {e}")

def release_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception:
        pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Entry Point
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == "__main__":
    acquire_lock()
    log.divider("INITIALIZATION")
    log.info(f"Python {sys.version.split()[0]}")
    log.detail(f"PID: {os.getpid()}")
    register_startup()
    log.ok("System tray icon ready")

    auto_thread = threading.Thread(target=run_asyncio_loop, daemon=True)
    auto_thread.start()

    try:
        setup_tray()
    finally:
        # Graceful cleanup
        state.should_exit.set()
        auto_thread.join(timeout=10)
        release_lock()
        log.info("Application exited")
        if getattr(state, 'is_restarting', False):
            import subprocess
            subprocess.Popen([sys.executable] + sys.argv)
