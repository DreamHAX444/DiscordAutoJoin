"""
Discord-specific actions: JavaScript snippets for monitoring and control,
plus the safe_eval wrapper for executing JS in the page.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, TYPE_CHECKING
from playwright.async_api import Error as PlaywrightError

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger("DiscordAutoJoin")

# ── JavaScript Snippets ───────────────────────────────────────────────────────

MONITOR_JS: str = """() => {
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
}"""

CLICK_MIC_JS: str = """() => {
    const micBtn = document.querySelector('button[aria-label*="ute" i], button[aria-label*="icrophone" i], button[aria-label*="Turn off" i]');
    if (micBtn) micBtn.click();
}"""


# ── Safe JS Evaluation ────────────────────────────────────────────────────────


async def safe_eval(page: "Page", js: str, timeout: int = 10) -> Optional[Any]:
    """Evaluate JavaScript in the page with timeout and error handling.

    Args:
        page: Playwright Page object.
        js: JavaScript string or function to evaluate.
        timeout: Maximum seconds to wait for evaluation.

    Returns:
        The JS evaluation result, or None if the evaluation failed
        (timeout, page closed, or any non-fatal Playwright error).

    Raises:
        PlaywrightError: Re-raised if the browser/context was closed
                         (fatal — caller must restart).
    """
    try:
        return await asyncio.wait_for(page.evaluate(js), timeout=timeout)
    except PlaywrightError as e:
        if "Target page, context or browser has been closed" in str(
            e
        ) or "Browser closed" in str(e):
            raise e
        logger.debug(f"safe_eval PlaywrightError: {e}")
        return None
    except asyncio.TimeoutError:
        logger.debug(f"safe_eval timed out after {timeout}s")
        return None
    except Exception as e:
        logger.debug(f"safe_eval unexpected error: {type(e).__name__}: {e}")
        return None
