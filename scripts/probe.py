"""Headless readiness probe: session token, reCAPTCHA site key, one mint. No generation."""

import asyncio

from selfflow.browser import FlowBrowser, FLOW_HOME


async def main() -> None:
    browser = FlowBrowser()
    try:
        page = await browser.start(headed=False)
        await page.goto(FLOW_HOME, wait_until="domcontentloaded")
        info = await browser.wait_ready(page, timeout_s=60, captcha=True)
        print("token:", bool(info.get("at")), "captcha:", info.get("captcha"))
        print("webdriver:", await page.evaluate("() => navigator.webdriver"))
        print("plugins:", await page.evaluate("() => navigator.plugins.length"))
        token = await browser.mint_captcha(page)
        print("captcha token length:", len(token), "prefix:", token[:12])
    finally:
        await browser.close()


asyncio.run(main())
