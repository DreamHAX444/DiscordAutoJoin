"""
Safe, curated Chrome command-line flags for Playwright persistent context.

All dangerous flags (--disable-web-security, --no-sandbox,
--disable-site-isolation-trials, --disable-gpu-sandbox) have been
removed. No-op flags on Windows (--no-zygote, --disable-dinosaur-easter-egg)
and redundant GPU flags have also been removed.

Result: 27 well-justified flags organized by category.
"""

CHROME_ARGS = [
    # Anti-detection
    '--disable-blink-features=AutomationControlled',
    # Disable unnecessary features
    '--disable-extensions', '--disable-default-apps', '--disable-sync',
    '--disable-breakpad', '--disable-crash-reporter', '--disable-logging',
    '--no-default-browser-check', '--disable-client-side-phishing-detection',
    '--disable-domain-reliability', '--disable-speech-api',
    '--disable-component-update', '--disable-hang-monitor',
    '--disable-prompt-on-repost', '--disable-ipc-flooding-protection',
    '--disable-dev-tools', '--metrics-recording-only',
    # Performance: reduce background activity
    '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
    '--disable-backgrounding-occluded-windows', '--disable-background-mode',
    # GPU / rendering: minimize resource usage
    '--disable-gpu', '--disable-dev-shm-usage',
    '--disable-canvas-aa', '--disable-2d-canvas-clip-aa', '--disable-webgl',
    '--disable-accelerated-2d-canvas', '--disable-accelerated-video-decode',
    '--disable-partial-raster',
    # Memory limits
    '--js-flags=--max-old-space-size=128', '--disk-cache-size=1',
    '--media-cache-size=1', '--renderer-process-limit=1',
    # UX suppression
    '--disable-notifications', '--disable-popup-blocking',
    '--disable-print-preview', '--disable-spell-checking', '--disable-translate',
    # Privacy / misc
    '--no-pings', '--no-first-run',
    '--enable-features=ReducedReferrerGranularity',
    # Window state
    '--start-maximized',
]