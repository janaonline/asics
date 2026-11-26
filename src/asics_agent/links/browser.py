"""The browser stage of the fetch chain, behind a small interface.

`Renderer` is all the chain knows: "give me the rendered text (and HTML) of this page". The default
implementation drives headless Chromium through Playwright on ONE background thread that runs an
asyncio loop (Playwright's sync API is bound to the thread that started it, and the steps run their link
checks on a thread pool). A different renderer (a remote browser service, a worker) only has to
implement `Renderer.render` and be passed to the chain (fetch_chain.ChainTools) or set with `set_renderer`.

Politeness: at most 2 pages at a time per host and 4 in all; images, media and fonts are not loaded.
robots.txt is checked by the chain before `render` is called.
"""

import asyncio
import re
import threading
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

INSTALL_HINT = "run `uv run playwright install chromium` once on this computer"
PAGE_TIMEOUT_MS = 40_000
SETTLE_MS = 8_000
PER_HOST, IN_ALL = 2, 4


@dataclass
class RenderResult:
    ok: bool
    text: str = ""
    html: str = ""
    body: bytes = b""  # the file itself, for a PDF
    content_type: str = ""
    final_url: str = ""
    status: int = 0
    error: str = ""  # why it failed (or "browser not installed")
    unavailable: bool = False  # the renderer cannot run at all on this computer


class Renderer(Protocol):
    """What the fetch chain needs from a browser."""

    def render(
        self, url: str, *, ignore_cert_errors: bool, user_agent: str, timeout: float = 60.0
    ) -> RenderResult: ...

    def close(self) -> None: ...


class ChromiumRenderer:
    """Headless Chromium through Playwright, on its own thread and event loop."""

    def __init__(self):
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._state: dict = {}
        self._unavailable = ""

    # -- thread and loop ------------------------------------------------------------------------
    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None:
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(
                    target=self._loop.run_forever, name="chromium-renderer", daemon=True
                )
                self._thread.start()
            return self._loop

    def render(
        self, url: str, *, ignore_cert_errors: bool, user_agent: str, timeout: float = 60.0
    ) -> RenderResult:
        if self._unavailable:
            return RenderResult(False, error=self._unavailable, unavailable=True)
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._render(url, ignore_cert_errors, user_agent), loop
        )
        try:
            return future.result(timeout=timeout + 20)
        except Exception as exc:  # timeout or a crashed browser: restart it next time
            future.cancel()
            self._state.clear()
            return RenderResult(False, error=f"{type(exc).__name__}: {str(exc)[:120]}")

    def close(self) -> None:
        loop = self._loop
        if loop is None:
            return

        async def shut():
            browser, pw = self._state.get("browser"), self._state.get("pw")
            if browser:
                await browser.close()
            if pw:
                await pw.stop()
            self._state.clear()

        try:
            asyncio.run_coroutine_threadsafe(shut(), loop).result(timeout=20)
        except Exception:
            pass
        loop.call_soon_threadsafe(loop.stop)
        self._loop = self._thread = None

    # -- inside the loop ------------------------------------------------------------------------
    async def _browser(self):
        if "browser" not in self._state:
            from playwright.async_api import async_playwright

            self._state["pw"] = await async_playwright().start()
            self._state["browser"] = await self._state["pw"].chromium.launch(headless=True)
            self._state["global"] = asyncio.Semaphore(IN_ALL)
            self._state["hosts"] = {}
        return self._state["browser"]

    async def _context(self, ignore_cert_errors: bool, user_agent: str):
        key = ("ctx", ignore_cert_errors, user_agent)
        if key not in self._state:
            browser = await self._browser()
            ctx = await browser.new_context(
                user_agent=user_agent,
                ignore_https_errors=ignore_cert_errors,
                locale="en-IN",
                viewport={"width": 1366, "height": 900},
            )

            async def lean(route):
                if route.request.resource_type in ("image", "media", "font"):
                    await route.abort()
                else:
                    await route.continue_()

            await ctx.route("**/*", lean)
            self._state[key] = ctx
        return self._state[key]

    async def _render(self, url: str, ignore_cert_errors: bool, user_agent: str) -> RenderResult:
        try:
            ctx = await self._context(ignore_cert_errors, user_agent)
        except Exception as exc:
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                self._unavailable = f"browser not installed: {INSTALL_HINT}"
            else:
                self._unavailable = f"browser could not start ({type(exc).__name__})"
            return RenderResult(False, error=self._unavailable, unavailable=True)
        host = urlsplit(url).netloc.lower()
        sems = self._state["hosts"]
        sem = sems.setdefault(host, asyncio.Semaphore(PER_HOST))
        async with self._state["global"], sem:
            if urlsplit(url).path.lower().endswith(".pdf"):
                return await self._get_file(ctx, url)
            return await self._get_page(ctx, url)

    async def _get_file(self, ctx, url: str) -> RenderResult:
        try:
            resp = await ctx.request.get(url, timeout=90_000)
            body = await resp.body()
        except Exception as exc:
            return RenderResult(False, error=f"{type(exc).__name__}: {str(exc)[:120]}")
        if resp.status != 200:
            return RenderResult(False, status=resp.status, error=f"HTTP {resp.status}")
        ctype = (resp.headers.get("content-type") or "application/pdf").split(";")[0]
        return RenderResult(True, body=body, content_type=ctype, final_url=resp.url, status=200)

    async def _get_page(self, ctx, url: str) -> RenderResult:
        page = await ctx.new_page()
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
            try:
                await page.wait_for_load_state("networkidle", timeout=SETTLE_MS)
            except Exception:
                pass  # some pages never go quiet: read what is there
            if "#/" in url:
                await page.wait_for_timeout(1500)  # a single-page app's route draws after load
            last = -1
            for _ in range(6):  # scroll: lazy lists draw as they come into view
                await page.mouse.wheel(0, 5000)
                await page.wait_for_timeout(300)
                size = await page.evaluate("document.body ? document.body.innerText.length : 0")
                if size == last:
                    break
                last = size
            status = resp.status if resp else 0
            if status >= 400:
                return RenderResult(False, status=status, error=f"HTTP {status}")
            text = await page.evaluate("document.body ? document.body.innerText : ''")
            html = await page.content()
            return RenderResult(
                True,
                text=re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", text)).strip(),
                html=html,
                content_type="text/html",
                final_url=page.url,
                status=status or 200,
            )
        except Exception as exc:
            first = str(exc).splitlines()[0][:140] if str(exc) else ""
            return RenderResult(False, error=f"{type(exc).__name__}: {first}")
        finally:
            await page.close()


_default: Renderer | None = None
_default_lock = threading.Lock()


def default_renderer() -> Renderer:
    global _default
    with _default_lock:
        if _default is None:
            _default = ChromiumRenderer()
        return _default


def set_renderer(renderer: Renderer | None) -> None:
    """Use another renderer (a remote browser service, a worker, a test double); None = Chromium."""
    global _default
    with _default_lock:
        _default = renderer
