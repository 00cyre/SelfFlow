"""Print live page state headlessly to diagnose sign-in and script availability."""

import asyncio

from selfflow.browser import FlowBrowser


async def main() -> None:
    browser = FlowBrowser()
    try:
        page = await browser.start(headed=False)
        await page.goto("https://flow.google.com/", wait_until="networkidle")
        print("url:", page.url)
        print("title:", await page.title())
        print(await page.evaluate("""() => ({
            wiz: Object.keys(globalThis.WIZ_global_data || {}).slice(0, 20),
            at: !!(globalThis.WIZ_global_data || {}).SNlM0e,
            grecaptcha: typeof window.grecaptcha,
            enterprise: !!(window.grecaptcha && window.grecaptcha.enterprise),
            cookies: document.cookie.split("; ").map(c => c.split("=")[0]).slice(0, 25),
            buttons: [...document.querySelectorAll('button, a')].map(e => e.innerText.trim()).filter(Boolean).slice(0, 20),
        })"""))
    finally:
        await browser.close()


asyncio.run(main())
