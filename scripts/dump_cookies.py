"""List persistent-profile cookie names (values withheld) to assess sign-in state."""

import asyncio

from selfflow.browser import FlowBrowser


async def main() -> None:
    browser = FlowBrowser()
    try:
        page = await browser.start(headed=False)
        await page.goto("https://flow.google.com/", wait_until="domcontentloaded")
        cookies = await page.context.cookies()
        names = sorted({c["name"] for c in cookies})
        google = [n for n in names if n.startswith(("SID", "HSID", "SSID", "APISID", "SAPISID", "__Secure"))]
        print("total cookies:", len(names))
        print("google auth:", google)
        print("names:", names)
    finally:
        await browser.close()


asyncio.run(main())
