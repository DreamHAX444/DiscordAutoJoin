"""
Core automation orchestrator — the heart of the application.

Lifecycle per iteration:
  1. Kill stale Chrome processes and remove lock files.
  2. Launch a persistent Chrome context with the Discord profile.
  3. Navigate to the target Discord voice channel.
  4. If not logged in, wait for manual login via tray menu.
  5. Click 'Join Voice', enable camera, mute mic.
  6. Enter monitoring loop: poll health, re-enable camera, mute mic.
  7. On disconnect or error, close context and restart with backoff.

Runs until state.should_exit is set (via tray Exit or fatal error).
"""

import asyncio
import time
import traceback
import ctypes
import logging

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

from .config import CONFIG, CHROME_PROFILE_DIR
from .chrome_flags import CHROME_ARGS
from .state import state
from .logging_setup import log
from .browser import kill_stale_chrome, remove_chrome_locks, lower_chrome_priority, find_chrome_hwnd
from .resource_guard import optimize_page
from .actions import MONITOR_JS, CLICK_MIC_JS, safe_eval
from .tray import set_tray, update_last_action

logger = logging.getLogger("DiscordAutoJoin")


async def automation_loop():
    """Main automation orchestrator — the heart of the application.

    Lifecycle per iteration:
      1. Kill stale Chrome processes and remove lock files.
      2. Launch a persistent Chrome context with the Discord profile.
      3. Navigate to the target Discord voice channel.
      4. If not logged in, wait for manual login via tray menu.
      5. Click 'Join Voice', enable camera, mute mic.
      6. Enter monitoring loop: poll health, re-enable camera, mute mic.
      7. On disconnect or error, close context and restart with backoff.

    Runs until state.should_exit is set (via tray Exit or fatal error).
    """
    async with async_playwright() as p:
        while not state.should_exit.is_set():
            context = None
            state.browser_hwnd = None
            state.force_reconnect = False

            try:
                log.info("Preparing browser environment...", category="SYS")
                await kill_stale_chrome()
                remove_chrome_locks()

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
                            try:
                                await context.close()
                            except Exception as close_err:
                                logger.debug(f"Context close during retry failed: {close_err}")
                        await kill_stale_chrome()
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
                        if state.force_reconnect:
                            continue
                        break

                    await page.goto(CONFIG['DISCORD_URL'], wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(5)

                # Join Voice Sequence
                set_tray("Connecting...", "yellow")
                connected = False
                for attempt in range(1, CONFIG['MAX_JOIN_RETRIES'] + 1):
                    while state.paused and not state.should_exit.is_set() and not state.force_reconnect:
                        await asyncio.sleep(1)
                    if state.should_exit.is_set() or state.force_reconnect:
                        break

                    log.info(f"Join attempt {attempt}", category="NET", silent=True)
                    try:
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

                if state.should_exit.is_set():
                    break
                if state.force_reconnect:
                    continue
                if not connected:
                    raise Exception("Exhausted voice join retries")

                # Hardware Toggles
                try:
                    await page.locator('[aria-label="Turn On Camera"]').first.click(timeout=3000)
                except Exception as e:
                    logger.debug(f"Camera toggle on join failed: {e}")

                ui = await safe_eval(page, MONITOR_JS)
                if ui and ui.get('micUnmuted'):
                    await safe_eval(page, CLICK_MIC_JS)

                # Minimize
                find_chrome_hwnd(state)
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
                    if state.should_exit.is_set() or state.force_reconnect:
                        break

                    await asyncio.sleep(CONFIG['POLL_INTERVAL'])
                    poll += 1

                    try:
                        if page.is_closed():
                            raise PlaywrightError("Page closed")

                        ui = await safe_eval(page, MONITOR_JS)
                    except PlaywrightError as e:
                        log.error(f"Browser connection lost: {e}", category="ERR")
                        break

                    if ui is None:
                        errs += 1
                        if errs >= CONFIG['MAX_CONSECUTIVE_ERRS']:
                            try:
                                log.warn("Page unresponsive. Reloading...", category="SYS")
                                await page.reload(wait_until="domcontentloaded", timeout=30000)
                                errs = 0
                                update_last_action("Reloaded Unresponsive Page")
                            except Exception as reload_err:
                                logger.debug(f"Page reload failed: {reload_err}")
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
                        try:
                            await page.locator('[aria-label="Turn On Camera"]').first.click(timeout=3000)
                        except Exception as e:
                            logger.debug(f"Camera re-enable failed: {e}")
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
                    try:
                        await context.close()
                    except Exception as close_err:
                        logger.debug(f"Context close in finally failed: {close_err}")

                if not state.should_exit.is_set() and not state.force_reconnect:
                    state.restart_count += 1
                    delay = min(CONFIG['RESTART_DELAY'] * (2 ** (state.restart_count - 1)), 300)
                    update_last_action(f"Backoff Wait ({delay}s)", silent=True)

                    wait_until = time.time() + delay
                    while time.time() < wait_until and not state.should_exit.is_set():
                        if state.force_reconnect:
                            break
                        await asyncio.sleep(1)


def run_asyncio_loop():
    """Entry point for the asyncio automation thread.

    Runs the main automation_loop() coroutine via asyncio.run().
    All unhandled exceptions are logged with full traceback.
    """
    try:
        asyncio.run(automation_loop())
    except Exception as e:
        logger.error(f"Fatal asyncio error: {e}\n{traceback.format_exc()}")