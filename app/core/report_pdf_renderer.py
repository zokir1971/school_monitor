"""One lazily started PDF browser per application worker; isolated documents."""
from __future__ import annotations

import asyncio
import contextvars
import logging

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


class ReportPDFRenderer:
    def __init__(self, *, idle_seconds: float = 120.0):
        self._lock = asyncio.Lock()
        self._playwright = None
        self._browser = None
        self._idle_task = None
        self._idle_seconds = idle_seconds
        self._warmup_task = None
        self._closed = False

    def _cancel_idle(self):
        if self._idle_task is not None:
            self._idle_task.cancel()
            self._idle_task = None

    async def _close_locked(self):
        browser, playwright = self._browser, self._playwright
        self._browser = self._playwright = None
        try:
            if browser is not None:
                await browser.close()
        finally:
            if playwright is not None:
                await playwright.stop()

    def schedule_warmup(self):
        """Prepare only the browser, without retaining request/user/report data."""
        if self._closed or self._lock.locked():
            return
        if self._warmup_task is not None and not self._warmup_task.done():
            return
        # Empty Context prevents a detached task from retaining request-local
        # profiling state, session information or database transaction context.
        self._warmup_task = asyncio.create_task(
            self._warmup(), context=contextvars.Context(), name='report-pdf-warmup',
        )

    def _arm_idle(self):
        if self._browser is not None:
            self._idle_task = asyncio.create_task(
                self._close_after_idle(), context=contextvars.Context(),
            )

    async def _warmup(self):
        try:
            async with self._lock:
                self._cancel_idle()
                try:
                    cold = self._browser is None or not self._browser.is_connected()
                    await asyncio.wait_for(self._ensure_browser(), timeout=15.0)
                    if cold:
                        logger.info('Report PDF browser prepared')
                except Exception:
                    # Optional preparation must never turn a working form into
                    # an error. Actual signing still uses the normal renderer.
                    await self._close_locked()
                    raise
                finally:
                    self._arm_idle()
        except Exception:
            logger.warning('Could not prepare report PDF browser', exc_info=True)
        finally:
            if self._warmup_task is asyncio.current_task():
                self._warmup_task = None

    async def close(self):
        self._closed = True
        task = self._warmup_task
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self._warmup_task = None
        async with self._lock:
            self._cancel_idle()
            await self._close_locked()

    async def _close_after_idle(self):
        try:
            await asyncio.sleep(self._idle_seconds)
            async with self._lock:
                await self._close_locked()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.warning('Could not close idle report PDF browser', exc_info=True)
        finally:
            if self._idle_task is asyncio.current_task():
                self._idle_task = None

    async def _ensure_browser(self):
        if self._browser is not None and self._browser.is_connected():
            return
        await self._close_locked()
        playwright = await async_playwright().start()
        try:
            browser = await playwright.chromium.launch(headless=True)
        except BaseException:
            await playwright.stop()
            raise
        self._playwright, self._browser = playwright, browser

    @staticmethod
    async def _load_document(page, html: str):
        # These two report templates use inline CSS and a QR data URI.
        await page.set_content(html, wait_until='load')
        await asyncio.wait_for(page.evaluate('''async () => {
            await document.fonts.ready;
            await Promise.all(Array.from(document.images, image => image.decode()));
        }'''), timeout=30.0)

    @staticmethod
    async def _print_document(page) -> bytes:
        return await page.pdf(format='A4', print_background=True, margin={
            'top': '15mm', 'right': '15mm', 'bottom': '15mm', 'left': '15mm',
        })

    @staticmethod
    async def _prepare_structured_document(page):
        if await page.locator('math-field').count():
            # MathLive loads asynchronously; never print raw LaTeX.
            await page.wait_for_function(
                "customElements.get('math-field') && [...document.querySelectorAll('math-field')].every(el => el.shadowRoot && el.shadowRoot.querySelector('[part=content]')?.childElementCount > 0 && getComputedStyle(el.shadowRoot.querySelector('[part=container]')).visibility !== 'hidden')",
                timeout=30000)
            await asyncio.wait_for(page.evaluate("async () => { await document.fonts.ready; await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame); }"), timeout=30)

    @staticmethod
    async def _print_structured_document(page) -> bytes:
        return await page.pdf(format='A4', print_background=True, margin={
            'top': '12mm', 'bottom': '12mm', 'left': '10mm', 'right': '10mm',
        })

    async def render(self, html: str, *, structured: bool = False) -> bytes:
        # Bound memory use: one active PDF and one browser per worker.
        async with self._lock:
            self._cancel_idle()
            try:
                await self._ensure_browser()
                context = await self._browser.new_context()
                try:
                    page = await context.new_page()
                    await self._load_document(page, html)
                    if structured:
                        await self._prepare_structured_document(page)
                        return await self._print_structured_document(page)
                    return await self._print_document(page)
                finally:
                    await context.close()
            except BaseException:
                # Do not reuse a failed/cancelled document's browser or context.
                await self._close_locked()
                raise
            finally:
                self._arm_idle()


_renderer = ReportPDFRenderer()


async def render_report_pdf(html: str, *, structured: bool = False) -> bytes:
    return await _renderer.render(html, structured=structured)


def schedule_report_pdf_warmup():
    _renderer.schedule_warmup()


async def close_report_pdf_renderer():
    await _renderer.close()
