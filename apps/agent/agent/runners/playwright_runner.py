"""Playwright runner - web sayfasi screenshot, yukleme kontrolu, element dogrulama.

Playwright async API kullanarak headless Chrome/Chromium uzerinden
web sayfasi islemleri gerceklestirir. Screenshot'lar S3'e yuklenir.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from agent.runners.base import BaseRunner
from agent.upload.s3_uploader import S3UploadError, bytes_to_base64

if TYPE_CHECKING:
    from agent.upload.s3_uploader import S3Uploader

logger = structlog.get_logger()

# Desteklenen aksiyonlar
_SUPPORTED_ACTIONS: frozenset[str] = frozenset(
    [
        "take_screenshot",
        "check_page_load",
        "check_element",
        "fill_form",
        "wait_for_response",
    ],
)

# Varsayilan degerler
_DEFAULT_VIEWPORT_WIDTH: int = 1920
_DEFAULT_VIEWPORT_HEIGHT: int = 1080
_DEFAULT_PAGE_TIMEOUT_MS: int = 30_000
_DEFAULT_ELEMENT_TIMEOUT_MS: int = 10_000
_DEFAULT_WAIT_UNTIL: str = "load"
_DEFAULT_RESPONSE_TIMEOUT_MS: int = 30_000

# Gecerli wait_until degerleri
_VALID_WAIT_UNTIL: frozenset[str] = frozenset(
    ["load", "domcontentloaded", "networkidle", "commit"],
)


class PlaywrightRunnerError(Exception):
    """Playwright runner'a ozel hata sinifi."""


class PlaywrightRunner(BaseRunner):
    """Playwright ile web sayfasi islemlerini calistiran runner.

    Screenshot alma, sayfa yukleme kontrolu, element dogrulama,
    form doldurma ve network response bekleme islemlerini gerceklestirir.

    Args:
        s3_uploader: Screenshot yukleme icin S3Uploader instance.
        screenshots_dir: Gecici screenshot dizini (opsiyonel, debug icin).
        default_timeout_ms: Varsayilan sayfa timeout suresi (milisaniye).
    """

    def __init__(
        self,
        s3_uploader: S3Uploader | None = None,
        screenshots_dir: str = "/tmp/rafraf/screenshots",
        default_timeout_ms: int = _DEFAULT_PAGE_TIMEOUT_MS,
    ) -> None:
        self._s3_uploader = s3_uploader
        self._screenshots_dir = screenshots_dir
        self._default_timeout_ms = default_timeout_ms

    @property
    def tool_name(self) -> str:
        """Runner'in destekledigi tool adi."""
        return "playwright"

    async def execute(self, action: str, params: dict[str, object]) -> dict[str, object]:
        """Playwright aksiyonunu calistirir.

        Args:
            action: Aksiyon adi (take_screenshot, check_page_load, vb.).
            params: Aksiyon parametreleri.

        Returns:
            Sonuc dictionary'si.

        Raises:
            ValueError: Bilinmeyen aksiyon.
        """
        if action not in _SUPPORTED_ACTIONS:
            msg = (
                f"Bilinmeyen Playwright aksiyonu: {action}. "
                f"Desteklenenler: {sorted(_SUPPORTED_ACTIONS)}"
            )
            raise ValueError(msg)

        url = params.get("url")
        if not isinstance(url, str) or not url:
            return {
                "success": False,
                "error": "url parametresi zorunlu (string)",
            }

        return await self._dispatch_action(action, url, params)

    async def _dispatch_action(
        self,
        action: str,
        url: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        """Aksiyonu ilgili metoda yonlendirir."""
        if action == "take_screenshot":
            return await self._take_screenshot(url, params)
        if action == "check_page_load":
            return await self._check_page_load(url, params)
        if action == "check_element":
            return await self._check_element(url, params)
        if action == "fill_form":
            return await self._fill_form(url, params)
        if action == "wait_for_response":
            return await self._wait_for_response(url, params)

        msg = f"Beklenmeyen aksiyon: {action}"
        raise ValueError(msg)

    async def _take_screenshot(
        self,
        url: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        """Sayfa veya element screenshot'i alir ve S3'e yukler.

        Args:
            url: Hedef sayfa URL'i.
            params: full_page, selector, viewport_width, viewport_height.

        Returns:
            success, screenshot_url veya screenshot_base64, page_title.
        """
        full_page = bool(params.get("full_page", False))
        selector = params.get("selector")
        viewport_width = params.get("viewport_width", _DEFAULT_VIEWPORT_WIDTH)
        viewport_height = params.get("viewport_height", _DEFAULT_VIEWPORT_HEIGHT)

        if not isinstance(viewport_width, int) or viewport_width < 1:
            viewport_width = _DEFAULT_VIEWPORT_WIDTH
        if not isinstance(viewport_height, int) or viewport_height < 1:
            viewport_height = _DEFAULT_VIEWPORT_HEIGHT

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return {
                "success": False,
                "error": "Playwright yuklu degil. 'pip install playwright' ile yukleyin.",
            }

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page(
                        viewport={"width": viewport_width, "height": viewport_height},
                    )
                    await page.goto(
                        url,
                        wait_until="load",
                        timeout=self._default_timeout_ms,
                    )

                    page_title = await page.title()

                    if isinstance(selector, str) and selector:
                        # Element screenshot
                        element = await page.wait_for_selector(
                            selector,
                            timeout=_DEFAULT_ELEMENT_TIMEOUT_MS,
                        )
                        if element is None:
                            return {
                                "success": False,
                                "error": f"Element bulunamadi: {selector}",
                            }
                        screenshot_bytes = await element.screenshot(type="png")
                    else:
                        # Full page veya viewport screenshot
                        screenshot_bytes = await page.screenshot(
                            full_page=full_page,
                            type="png",
                        )
                finally:
                    await browser.close()

        except Exception as exc:
            error_msg = str(exc)
            await logger.awarning(
                "Playwright screenshot hatasi",
                url=url,
                error=error_msg,
            )
            return {
                "success": False,
                "error": f"Screenshot alinamadi: {error_msg}",
            }

        # S3'e yukle
        return await self._upload_screenshot(
            screenshot_bytes=screenshot_bytes,
            page_title=page_title,
            url=url,
        )

    async def _upload_screenshot(
        self,
        screenshot_bytes: bytes,
        page_title: str,
        url: str,
    ) -> dict[str, object]:
        """Screenshot'i S3'e yukler veya base64 fallback dondurur."""
        if self._s3_uploader is not None:
            try:
                s3_key = f"screenshots/{int(time.time())}.png"
                screenshot_url = await self._s3_uploader.upload_bytes(
                    data=screenshot_bytes,
                    key=s3_key,
                )
                await logger.ainfo(
                    "Screenshot S3'e yuklendi",
                    url=url,
                    s3_key=s3_key,
                )
                return {
                    "success": True,
                    "screenshot_url": screenshot_url,
                    "page_title": page_title,
                }
            except S3UploadError as exc:
                await logger.awarning(
                    "S3 upload basarisiz, base64 fallback kullaniliyor",
                    error=str(exc),
                )

        # Fallback: base64 olarak dondur
        return {
            "success": True,
            "screenshot_base64": bytes_to_base64(screenshot_bytes),
            "page_title": page_title,
        }

    async def _check_page_load(
        self,
        url: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        """Sayfa yuklenme kontrolu yapar.

        Args:
            url: Kontrol edilecek URL.
            params: wait_until, timeout.

        Returns:
            success, page_title, load_time_ms.
        """
        wait_until = params.get("wait_until", _DEFAULT_WAIT_UNTIL)
        if not isinstance(wait_until, str) or wait_until not in _VALID_WAIT_UNTIL:
            wait_until = _DEFAULT_WAIT_UNTIL

        timeout = params.get("timeout", 30)
        if not isinstance(timeout, int) or timeout < 1:
            timeout = 30
        timeout_ms = timeout * 1000

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return {
                "success": False,
                "error": "Playwright yuklu degil.",
            }

        start_time = time.monotonic()

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page(
                        viewport={
                            "width": _DEFAULT_VIEWPORT_WIDTH,
                            "height": _DEFAULT_VIEWPORT_HEIGHT,
                        },
                    )
                    response = await page.goto(
                        url,
                        wait_until=wait_until,  # type: ignore[arg-type]
                        timeout=timeout_ms,
                    )

                    load_time_ms = int((time.monotonic() - start_time) * 1000)
                    page_title = await page.title()
                    status_code = response.status if response else None
                finally:
                    await browser.close()

        except Exception as exc:
            load_time_ms = int((time.monotonic() - start_time) * 1000)
            error_msg = str(exc)
            await logger.awarning(
                "Sayfa yukleme hatasi",
                url=url,
                error=error_msg,
                load_time_ms=load_time_ms,
            )
            return {
                "success": False,
                "error": f"Sayfa yuklenemedi: {error_msg}",
                "load_time_ms": load_time_ms,
            }

        return {
            "success": True,
            "page_title": page_title,
            "status_code": status_code,
            "load_time_ms": load_time_ms,
            "wait_until": wait_until,
        }

    async def _check_element(
        self,
        url: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        """Element varlik kontrolu yapar.

        Args:
            url: Hedef sayfa URL'i.
            params: selector, timeout.

        Returns:
            success, element_found, element_text, element_visible.
        """
        selector = params.get("selector")
        if not isinstance(selector, str) or not selector:
            return {
                "success": False,
                "error": "selector parametresi zorunlu (string)",
            }

        timeout = params.get("timeout", 10)
        if not isinstance(timeout, int) or timeout < 1:
            timeout = 10
        timeout_ms = timeout * 1000

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return {
                "success": False,
                "error": "Playwright yuklu degil.",
            }

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page(
                        viewport={
                            "width": _DEFAULT_VIEWPORT_WIDTH,
                            "height": _DEFAULT_VIEWPORT_HEIGHT,
                        },
                    )
                    await page.goto(
                        url,
                        wait_until="load",
                        timeout=self._default_timeout_ms,
                    )

                    element = await page.wait_for_selector(
                        selector,
                        timeout=timeout_ms,
                    )

                    if element is None:
                        return {
                            "success": True,
                            "element_found": False,
                            "selector": selector,
                        }

                    element_text = await element.text_content()
                    element_visible = await element.is_visible()

                    return {
                        "success": True,
                        "element_found": True,
                        "selector": selector,
                        "element_text": element_text,
                        "element_visible": element_visible,
                    }

                finally:
                    await browser.close()

        except Exception as exc:
            error_msg = str(exc)
            # Timeout = element bulunamadi (basarili ama bulunamadi)
            if "timeout" in error_msg.lower():
                return {
                    "success": True,
                    "element_found": False,
                    "selector": selector,
                    "error": f"Element bekleme zamani asimi: {error_msg}",
                }

            await logger.awarning(
                "Element kontrol hatasi",
                url=url,
                selector=selector,
                error=error_msg,
            )
            return {
                "success": False,
                "error": f"Element kontrolu basarisiz: {error_msg}",
            }

    async def _fill_form(
        self,
        url: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        """Form doldurma islemi.

        Args:
            url: Hedef sayfa URL'i.
            params: fields (list of {selector, value}), submit_selector.

        Returns:
            success, filled_count, submitted.
        """
        fields = params.get("fields")
        if not isinstance(fields, list) or not fields:
            return {
                "success": False,
                "error": "fields parametresi zorunlu (list of {selector, value})",
            }

        submit_selector = params.get("submit_selector")

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return {
                "success": False,
                "error": "Playwright yuklu degil.",
            }

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page(
                        viewport={
                            "width": _DEFAULT_VIEWPORT_WIDTH,
                            "height": _DEFAULT_VIEWPORT_HEIGHT,
                        },
                    )
                    await page.goto(
                        url,
                        wait_until="load",
                        timeout=self._default_timeout_ms,
                    )

                    filled_count = 0
                    for field in fields:
                        if not isinstance(field, dict):
                            continue
                        field_selector = field.get("selector")
                        field_value = field.get("value")
                        if not isinstance(field_selector, str) or not isinstance(field_value, str):
                            continue

                        await page.fill(field_selector, field_value)
                        filled_count += 1

                    submitted = False
                    if isinstance(submit_selector, str) and submit_selector:
                        await page.click(submit_selector)
                        submitted = True
                        # Submit sonrasi kisa bekleme
                        await page.wait_for_load_state("load", timeout=self._default_timeout_ms)

                finally:
                    await browser.close()

        except Exception as exc:
            error_msg = str(exc)
            await logger.awarning(
                "Form doldurma hatasi",
                url=url,
                error=error_msg,
            )
            return {
                "success": False,
                "error": f"Form doldurma basarisiz: {error_msg}",
            }

        return {
            "success": True,
            "filled_count": filled_count,
            "submitted": submitted,
        }

    async def _wait_for_response(
        self,
        url: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        """Belirli bir URL pattern'ine sahip network response bekler.

        Args:
            url: Hedef sayfa URL'i.
            params: url_pattern, timeout.

        Returns:
            success, response_url, response_status, response_time_ms.
        """
        url_pattern = params.get("url_pattern")
        if not isinstance(url_pattern, str) or not url_pattern:
            return {
                "success": False,
                "error": "url_pattern parametresi zorunlu (string)",
            }

        timeout = params.get("timeout", 30)
        if not isinstance(timeout, int) or timeout < 1:
            timeout = 30
        timeout_ms = timeout * 1000

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return {
                "success": False,
                "error": "Playwright yuklu degil.",
            }

        start_time = time.monotonic()

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page(
                        viewport={
                            "width": _DEFAULT_VIEWPORT_WIDTH,
                            "height": _DEFAULT_VIEWPORT_HEIGHT,
                        },
                    )

                    # Response beklemeyi baslat (sayfaya gitmeden once)
                    async with page.expect_response(
                        url_pattern,
                        timeout=timeout_ms,
                    ) as response_info:
                        await page.goto(
                            url,
                            wait_until="commit",
                            timeout=self._default_timeout_ms,
                        )

                    response = await response_info.value
                    response_time_ms = int((time.monotonic() - start_time) * 1000)

                    return {
                        "success": True,
                        "response_url": response.url,
                        "response_status": response.status,
                        "response_time_ms": response_time_ms,
                    }

                finally:
                    await browser.close()

        except Exception as exc:
            response_time_ms = int((time.monotonic() - start_time) * 1000)
            error_msg = str(exc)

            if "timeout" in error_msg.lower():
                return {
                    "success": False,
                    "error": f"Response bekleme zamani asimi ({timeout}sn): {error_msg}",
                    "response_time_ms": response_time_ms,
                }

            await logger.awarning(
                "Network response bekleme hatasi",
                url=url,
                url_pattern=url_pattern,
                error=error_msg,
            )
            return {
                "success": False,
                "error": f"Response bekleme basarisiz: {error_msg}",
                "response_time_ms": response_time_ms,
            }
