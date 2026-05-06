import asyncio, os
from playwright.async_api import async_playwright

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
]

async def run():
    user_dir = os.path.join(os.environ['APPDATA'], 'DiscordAutoJoin', 'ChromeProfile')
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=user_dir,
                channel='chrome',
                headless=False,
                permissions=['camera', 'microphone'],
                args=CHROME_ARGS
            )
            page = browser.pages[0] if browser.pages else await browser.new_page()
            await page.goto("https://discord.com/channels/@me", wait_until="domcontentloaded")
            await asyncio.sleep(8)
            
            # evaluate and find all buttons with aria-labels or inner SVGs
            htmls = await page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button'));
                return btns.map(b => b.outerHTML).filter(h => h.toLowerCase().includes('mute') || h.toLowerCase().includes('mic'));
            }''')
            
            for h in htmls:
                print("BUTTON:", h)
                
            await browser.close()
    except Exception as e:
        print(f"FAILED: {e.__class__.__name__} - {e}")

if __name__ == "__main__":
    asyncio.run(run())
