"""
Resource guard — blocks analytics/tracking domains and injects CSS
optimizations into the Discord page to reduce CPU/GPU/memory usage.
"""

import re
import logging

logger = logging.getLogger("DiscordAutoJoin")

# ── Domain Blocking ───────────────────────────────────────────────────────────
BLOCKED_DOMAINS = re.compile(
    r'(sentry\.io|google-analytics|googletagmanager|doubleclick|'
    r'newrelic|datadoghq|cdn\.discordapp\.com/attachments|'
    r'media\.discordapp\.net|images-ext)', re.IGNORECASE
)

# ── CSS Optimization ──────────────────────────────────────────────────────────
OPTIMIZE_CSS = '''
*, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; }
[class*="gif"], [class*="avatar"] img:not([class*="voice"]) { visibility: hidden !important; }
'''


async def optimize_page(page):
    """Inject resource-saving optimizations into the Discord page.

    - Blocks requests to analytics/tracking domains via route interception.
    - Injects CSS to disable animations/transitions and hide GIFs/avatars.

    Args:
        page: Playwright Page object for the Discord tab.
    """
    async def handle_route(route):
        if BLOCKED_DOMAINS.search(route.request.url):
            await route.abort()
        else:
            await route.continue_()

    try:
        await page.route('**/*', handle_route)
        await page.add_style_tag(content=OPTIMIZE_CSS)
    except Exception as e:
        logger.debug(f"optimize_page failed: {e}")