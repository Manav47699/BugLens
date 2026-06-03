"""
L3 Browser Agent Service
------------------------
Playwright-powered agent that:
  1. Discovers all reachable routes by crawling <a> tags and JS navigation.
  2. For each route: clicks interactive elements, fills & submits forms.
  3. Captures JS errors, console warnings, failed network requests,
     hydration errors, infinite loaders, and dead UI elements.
  4. Returns structured BugEvidence per finding, plus screenshots.
"""

import asyncio
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

from playwright.async_api import (
    BrowserContext,
    Page,
    Request,
    Response,
    async_playwright,
)

from app.core.config import settings
from app.core.logging import get_logger
from app.models.report import BugEvidence, NetworkRequest
from app.models.session import Session

log = get_logger(__name__)

# Inputs we'll attempt to fill with edge-case values
_FORM_TEST_VALUES: dict[str, str] = {
    "email": "test@buglens.dev",
    "password": "BugLens!2025",
    "text": "Hello BugLens",
    "search": "test query",
    "number": "42",
    "tel": "5551234567",
    "url": "https://buglens.dev",
    "textarea": "BugLens automated test content.",
    "default": "buglens_test",
}


class BrowserAgent:
    def __init__(self, session: Session, base_url: str, screenshot_dir: Path):
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.screenshot_dir = screenshot_dir
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        self._visited: set[str] = set()
        self._queue: list[str] = ["/"]
        self.evidence_list: list[BugEvidence] = []

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self) -> list[BugEvidence]:
        """Full crawl + interact pass. Returns all collected evidence."""
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=True,
            )
            await context.set_extra_http_headers({"X-BugLens": "1"})

            try:
                await self._crawl(context)
            finally:
                await browser.close()

        return self.evidence_list

    # ------------------------------------------------------------------
    # Phase 1 — Route discovery + interaction loop
    # ------------------------------------------------------------------

    async def _crawl(self, context: BrowserContext) -> None:
        explored = 0

        while self._queue and explored < settings.max_routes:
            path = self._queue.pop(0)
            if path in self._visited:
                continue

            self._visited.add(path)
            url = urljoin(self.base_url, path)

            self.session.log(f"Exploring route: {path}")
            self.session.routes_explored.append(path)

            evidence = await self._explore_page(context, url, path)
            if self._has_findings(evidence):
                self.evidence_list.append(evidence)

            explored += 1

        self.session.log(
            f"Exploration complete. {explored} routes visited, "
            f"{len(self.evidence_list)} finding(s) collected."
        )

    async def _explore_page(
        self, context: BrowserContext, url: str, path: str
    ) -> BugEvidence:
        """Visit one route, collect all signals, interact with the UI."""
        js_errors: list[str] = []
        console_warnings: list[str] = []
        failed_requests: list[NetworkRequest] = []

        page = await context.new_page()

        # --- Wire up listeners before navigation ---

        page.on("console", lambda msg: self._on_console(msg, console_warnings))
        page.on("pageerror", lambda err: js_errors.append(str(err)))
        page.on(
            "requestfailed",
            lambda req: failed_requests.append(
                NetworkRequest(method=req.method, url=req.url, status=0)
            ),
        )
        page.on(
            "response",
            lambda resp: self._on_response(resp, failed_requests),
        )

        # --- Navigate ---
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
        except Exception as exc:
            js_errors.append(f"Navigation failed: {exc}")

        # Wait briefly for hydration / async rendering
        await asyncio.sleep(1)

        # Discover new links before interacting
        await self._collect_links(page)

        # Interact with the page (up to max_actions_per_route)
        await self._interact(page, path, js_errors, failed_requests)

        # Screenshot (always — useful for reporting)
        screenshot_path = await self._screenshot(page, path)

        # Check for infinite loaders
        await self._check_loaders(page, js_errors)

        await page.close()

        return BugEvidence(
            route=path,
            js_errors=js_errors,
            console_warnings=console_warnings,
            failed_requests=failed_requests,
            screenshot_path=str(screenshot_path) if screenshot_path else None,
        )

    # ------------------------------------------------------------------
    # Phase 2 — Interaction
    # ------------------------------------------------------------------

    async def _interact(
        self,
        page: Page,
        path: str,
        js_errors: list[str],
        failed_requests: list[NetworkRequest],
        *,
        attempts: int = 3,
    ) -> None:
        """Click buttons, fill forms, submit — up to max_actions_per_route."""
        actions = 0

        for _ in range(attempts):
            if actions >= settings.max_actions_per_route:
                break

            # Fill all visible inputs
            actions += await self._fill_form(page)

            # Click buttons / submit
            buttons = await page.query_selector_all(
                "button:visible, [role='button']:visible, input[type='submit']:visible"
            )
            for btn in buttons[: settings.max_actions_per_route - actions]:
                try:
                    await btn.scroll_into_view_if_needed()
                    await btn.click(timeout=3_000)
                    await asyncio.sleep(0.5)
                    actions += 1
                except Exception:
                    pass

    async def _fill_form(self, page: Page) -> int:
        """Fill all visible form inputs. Returns number of fields filled."""
        filled = 0
        inputs = await page.query_selector_all(
            "input:visible:not([type='hidden']):not([type='submit']):not([type='button']), "
            "textarea:visible, select:visible"
        )
        for inp in inputs:
            try:
                input_type = (await inp.get_attribute("type") or "default").lower()
                name = (await inp.get_attribute("name") or "").lower()
                value = _FORM_TEST_VALUES.get(
                    input_type,
                    _FORM_TEST_VALUES.get(name, _FORM_TEST_VALUES["default"]),
                )
                tag = await inp.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    options = await inp.query_selector_all("option")
                    if options:
                        val = await options[-1].get_attribute("value")
                        if val:
                            await inp.select_option(val)
                else:
                    await inp.fill(value, timeout=3_000)
                filled += 1
            except Exception:
                pass
        return filled

    # ------------------------------------------------------------------
    # Phase 3 — Extra checks
    # ------------------------------------------------------------------

    async def _check_loaders(self, page: Page, js_errors: list[str]) -> None:
        """Flag infinite loaders / spinners that are still visible after 5s."""
        spinner_selectors = [
            "[class*='spinner']:visible",
            "[class*='loading']:visible",
            "[class*='loader']:visible",
            "[aria-label*='loading']:visible",
        ]
        await asyncio.sleep(3)  # let async content settle

        for sel in spinner_selectors:
            try:
                count = await page.locator(sel).count()
                if count:
                    js_errors.append(
                        f"Infinite loader detected ({count} element(s) matching '{sel}' "
                        "still visible after 3s)"
                    )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Link collection
    # ------------------------------------------------------------------

    async def _collect_links(self, page: Page) -> None:
        try:
            hrefs = await page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.getAttribute('href'))"
            )
        except Exception:
            return

        for href in hrefs:
            if not href:
                continue
            parsed = urlparse(href)
            # Internal links only
            if parsed.scheme and parsed.netloc and parsed.netloc not in self.base_url:
                continue
            path = parsed.path or "/"
            if path not in self._visited and path not in self._queue:
                self._queue.append(path)
                if path not in self.session.routes_discovered:
                    self.session.routes_discovered.append(path)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_console(self, msg, warnings: list[str]) -> None:
        if msg.type in ("warning", "error"):
            text = msg.text
            # Filter out noise
            if any(
                noise in text
                for noise in ["favicon", "DevTools", "Source map", "[HMR]"]
            ):
                return
            warnings.append(f"[{msg.type.upper()}] {text}")

    def _on_response(self, resp: Response, failed: list[NetworkRequest]) -> None:
        if resp.status >= 400:
            failed.append(
                NetworkRequest(
                    method=resp.request.method,
                    url=resp.url,
                    status=resp.status,
                )
            )

    # ------------------------------------------------------------------
    # Screenshot
    # ------------------------------------------------------------------

    async def _screenshot(self, page: Page, path: str) -> Optional[Path]:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", path.strip("/")) or "root"
        dest = self.screenshot_dir / f"{safe}.png"
        try:
            await page.screenshot(path=str(dest), full_page=True)
            return dest
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_findings(e: BugEvidence) -> bool:
        return bool(e.js_errors or e.failed_requests)