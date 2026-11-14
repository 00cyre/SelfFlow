"""Playwright browser session for Flow: stealth profile, login, generation."""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import BrowserContext, Page, async_playwright

from . import state, wire

PROFILE_DIR = Path(os.environ.get("SELFFLOW_PROFILE", str(Path.home() / ".selfflow" / "chrome-profile")))
FLOW_HOME = wire.FLOW_ORIGIN + "/"
APP_URL = FLOW_HOME  # signed in shows the projects home; signed out redirects to /about
PROJECT_URL = FLOW_HOME + "project/{pid}"

# Runs before any page script in every document of the persistent profile.
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
const origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (p) =>
    p.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : origQuery(p);
"""

_READY_JS = """
() => ({
    at: (globalThis.WIZ_global_data || {}).SNlM0e || null,
    captcha: !!(window.grecaptcha && window.grecaptcha.enterprise && window.grecaptcha.enterprise.execute),
    origin: location.origin,
    path: location.pathname,
})
"""

_SITE_KEY_JS = """
() => {
    for (const s of document.querySelectorAll('script[src*="recaptcha/enterprise.js"]')) {
        const m = (s.src || '').match(/[?&]render=([^&]+)/);
        if (m) return m[1];
    }
    return null;
}
"""

_MINT_JS = """
async ([siteKey, action]) => {
    const g = window.grecaptcha && window.grecaptcha.enterprise;
    if (!g) return { error: 'NO_GRECAPTCHA' };
    const realAssign = Object.assign;
    Object.assign = function (target, ...sources) {
        const out = realAssign(target, ...sources);
        if (out && out.action === 'extension_hijack_detected') out.action = action;
        return out;
    };
    try {
        const token = await new Promise((resolve, reject) => {
            g.ready(() => g.execute(siteKey, { action }).then(resolve).catch(reject));
        });
        return { token };
    } catch (e) {
        return { error: String(e) };
    } finally {
        Object.assign = realAssign;
    }
}
"""

_RPC_JS = """
async ([rpcid, freq]) => {
    const wiz = globalThis.WIZ_global_data || {};
    const body = new URLSearchParams({ 'f.req': freq, at: wiz.SNlM0e || '' });
    const url = '/_/AiSandboxAngularFrontend/data/batchexecute'
        + '?rpcids=' + encodeURIComponent(rpcid)
        + '&source-path=' + encodeURIComponent(location.pathname)
        + '&f.sid=' + encodeURIComponent(wiz.FdrFJe || '')
        + '&bl=' + encodeURIComponent(wiz.cfb2h || '')
        + '&hl=en&_reqid=' + Math.floor(100000 + Math.random() * 900000) + '&rt=c';
    const r = await fetch(url, {
        method: 'POST',
        credentials: 'include',
        headers: { 'content-type': 'application/x-www-form-urlencoded;charset=UTF-8', 'x-same-domain': '1' },
        body,
    });
    return { status: r.status, text: await r.text() };
}
"""


class FlowError(RuntimeError):
    pass


class FlowBrowser:
    def __init__(self, profile: Optional[Path] = None):
        self.profile = profile or PROFILE_DIR
        self.profile.mkdir(parents=True, exist_ok=True)
        self._pw: Any = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._site_key: Optional[str] = None

    # ── lifecycle ───────────────────────────────────────────────────────

    async def start(self, headed: Optional[bool] = None) -> Page:
        if self._context and self._context.pages:
            return self._page
        self._pw = await async_playwright().start()
        self._context = await self._pw.chromium.launch_persistent_context(
            str(self.profile),
            headless=_headless() if headed is None else not headed,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check",
                "--disable-infobars",
                "--disable-background-timer-throttling",
            ],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1440, "height": 900},
        )
        await self._context.add_init_script(STEALTH_JS)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        return self._page

    async def close(self) -> None:
        if self._context:
            await self._context.close()
        if self._pw:
            await self._pw.stop()
        self._context = self._pw = self._page = None

    # ── page helpers ───────────────────────────────────────────────────

    async def wait_ready(self, page: Page, *, timeout_s: int = 60, captcha: bool = False) -> dict:
        deadline = time.monotonic() + timeout_s
        last: dict = {}
        while time.monotonic() < deadline:
            try:
                last = await page.evaluate(_READY_JS)
                if self._is_authenticated(last) and (last.get("captcha") or not captcha):
                    return last
            except Exception:
                pass
            await asyncio.sleep(1)
        description = self._missing(last, captcha)
        raise FlowError(
            "Flow not ready at " + (page.url or "?") + "; " + description
            + ". Sign in once with `selfflow --login`, then retry."
        )

    def _is_authenticated(self, info: dict) -> bool:
        if not info.get("at"):
            return False
        if info.get("origin") != wire.FLOW_ORIGIN:
            return False
        return not str(info.get("path") or "").startswith("/about")

    def _missing(self, info: dict, captcha: bool) -> str:
        missing = []
        if not info.get("at"):
            missing.append("session token")
        if captcha and not info.get("captcha"):
            missing.append("reCAPTCHA")
        if info.get("at") and info.get("origin") == wire.FLOW_ORIGIN and str(info.get("path") or "").startswith("/about"):
            missing.append("Flow is on /about: open Create with Google Flow and finish signing in")
        if info.get("at") and info.get("origin") != wire.FLOW_ORIGIN:
            missing.append("Google account sign-in was reached, but Flow is not open yet")
        return "missing/invalid: " + ", ".join(missing)

    async def sign_in(self, timeout_s: int = 1200) -> None:
        page = await self.start(headed=True)
        await page.goto(APP_URL, wait_until="domcontentloaded")
        print(
            "Sign in to Flow in the Chrome window; waiting for an authenticated page...",
            flush=True,
        )
        await self.wait_ready(page, timeout_s=timeout_s)
        print("Flow session detected and saved to " + str(self.profile), flush=True)

    async def mint_captcha(self, page: Page, action: str = wire.CAPTCHA_ACTION) -> str:
        await self.wait_ready(page, timeout_s=45, captcha=True)
        if not self._site_key:
            self._site_key = await page.evaluate(_SITE_KEY_JS)
            if not self._site_key:
                raise FlowError("could not find the reCAPTCHA site key on the Flow page")
        out = await page.evaluate(_MINT_JS, [self._site_key, action])
        if not isinstance(out, dict) or not out.get("token"):
            raise FlowError(f"reCAPTCHA token failed: {out}")
        return out["token"]

    async def rpc(self, rpcid: str, freq: str) -> Any:
        out = await self._page.evaluate(_RPC_JS, [rpcid, freq])
        if not isinstance(out, dict) or out.get("status") != 200:
            raise FlowError(f"RPC {rpcid} failed: HTTP {out.get('status')} {str(out.get('text', ''))[:300]}")
        return wire.payload_for(out["text"], rpcid)

    # ── Flow operations ────────────────────────────────────────────────

    async def project(self) -> str:
        """Current tab's project, then the saved one, then a new one."""
        pid = project_from_url(self._page.url) or state.load_project_id()
        if pid:
            return pid
        pid = wire.read_created_project(
            await self.rpc(wire.RPC_CREATE_PROJECT, wire.create_project_request("SelfFlow project"))
        )
        state.save_project_id(pid)
        return pid

    async def open_project(self, project_id: str) -> None:
        url = PROJECT_URL.format(pid=project_id)
        if self._page.url.rstrip("/") != url.rstrip("/"):
            await self._page.goto(url, wait_until="domcontentloaded")
        await self.wait_ready(self._page, captcha=True)

    async def generate_images(
        self,
        *,
        prompt: str,
        model: str = "nano-banana-pro",
        aspect: str = "1:1",
        count: int = 1,
        seed: Optional[int] = None,
        project_id: Optional[str] = None,
        reference_ids: Optional[list[str]] = None,
    ) -> list[wire.GeneratedImage]:
        page = await self.start()
        await self.wait_ready(page)
        pid = project_id or await self.project()
        await self.open_project(pid)

        token = await self.mint_captcha(page)
        freq = wire.image_request(
            prompt=prompt, project_id=pid, count=count, aspect=aspect,
            model=model, seed=seed, references=reference_ids or [],
        )
        payload = await self.rpc(wire.RPC_GENERATE_IMAGE, wire.apply_captcha(freq, token))
        images = wire.read_images(payload)
        if not images:
            raise FlowError("Flow returned no image URL (generation may still be pending in the project)")
        return images


def _headless() -> bool:
    return os.environ.get("SELFFLOW_HEADED", "").lower() not in {"1", "true", "yes"}


def project_from_url(url: str) -> Optional[str]:
    match = re.search(r"/project/([0-9a-fA-F-]{36})", url or "")
    return match.group(1) if match else None
