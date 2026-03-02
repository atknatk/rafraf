"""Unit tests for PlaywrightRunner."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.runners.playwright_runner import (
    PlaywrightRunner,
    PlaywrightRunnerError,
)
from agent.upload.s3_uploader import S3UploadError, S3Uploader


# --- Fixtures ---


@pytest.fixture
def mock_s3_uploader() -> AsyncMock:
    """Mock S3Uploader olusturur."""
    uploader = AsyncMock(spec=S3Uploader)
    uploader.upload_bytes = AsyncMock(
        return_value="https://test-bucket.s3.eu-west-1.amazonaws.com/screenshots/test.png",
    )
    return uploader


@pytest.fixture
def playwright_runner(mock_s3_uploader: AsyncMock) -> PlaywrightRunner:
    """Test icin PlaywrightRunner instance olusturur."""
    return PlaywrightRunner(
        s3_uploader=mock_s3_uploader,
        default_timeout_ms=5000,
    )


@pytest.fixture
def playwright_runner_no_s3() -> PlaywrightRunner:
    """S3 uploader olmadan PlaywrightRunner olusturur."""
    return PlaywrightRunner(
        s3_uploader=None,
        default_timeout_ms=5000,
    )


def _make_mock_element(
    screenshot_bytes: bytes = b"fake-png-data",
    text_content: str = "Element text",
    is_visible: bool = True,
) -> AsyncMock:
    """Mock Playwright element olusturur."""
    mock_el = AsyncMock()
    mock_el.screenshot = AsyncMock(return_value=screenshot_bytes)
    mock_el.text_content = AsyncMock(return_value=text_content)
    mock_el.is_visible = AsyncMock(return_value=is_visible)
    return mock_el


def _make_mock_page(
    title: str = "Test Page",
    screenshot_bytes: bytes = b"fake-png-data",
    goto_response_status: int = 200,
) -> AsyncMock:
    """Mock Playwright page olusturur."""
    mock_response = MagicMock()
    mock_response.status = goto_response_status

    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(return_value=mock_response)
    mock_page.title = AsyncMock(return_value=title)
    mock_page.screenshot = AsyncMock(return_value=screenshot_bytes)
    mock_page.fill = AsyncMock()
    mock_page.click = AsyncMock()
    mock_page.wait_for_load_state = AsyncMock()

    mock_element = _make_mock_element(screenshot_bytes=screenshot_bytes)
    mock_page.wait_for_selector = AsyncMock(return_value=mock_element)

    return mock_page


def _make_mock_async_playwright(mock_page: AsyncMock | None = None) -> MagicMock:
    """async_playwright() mock olusturur.

    async_playwright() bir async context manager dondurur.
    """
    if mock_page is None:
        mock_page = _make_mock_page()

    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()

    mock_chromium = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_pw = MagicMock()
    mock_pw.chromium = mock_chromium

    # async context manager olarak calismali
    mock_async_pw = AsyncMock()
    mock_async_pw.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_async_pw.__aexit__ = AsyncMock(return_value=False)

    return mock_async_pw


def _patch_playwright(mock_page: AsyncMock | None = None) -> MagicMock:
    """playwright.async_api modulu mock.

    Runner icerisinde `from playwright.async_api import async_playwright`
    yapildigi icin modul duzeyinde mock uygulanmalidir.
    """
    mock_pw_cm = _make_mock_async_playwright(mock_page)

    # async_playwright fonksiyonu olarak mock
    mock_func = MagicMock(return_value=mock_pw_cm)

    mock_module = MagicMock()
    mock_module.async_playwright = mock_func

    return mock_module


# --- PlaywrightRunner Init Tests ---


class TestPlaywrightRunnerInit:
    """PlaywrightRunner __init__ testleri."""

    def test_tool_name(self, playwright_runner: PlaywrightRunner) -> None:
        """tool_name 'playwright' dondurur."""
        assert playwright_runner.tool_name == "playwright"

    def test_default_timeout(self) -> None:
        """Varsayilan timeout dogru ayarlanir."""
        runner = PlaywrightRunner()
        assert runner._default_timeout_ms == 30_000

    def test_custom_timeout(self) -> None:
        """Ozel timeout ayarlanabilir."""
        runner = PlaywrightRunner(default_timeout_ms=10_000)
        assert runner._default_timeout_ms == 10_000


# --- execute() Tests ---


class TestPlaywrightRunnerExecute:
    """PlaywrightRunner.execute() metod testleri."""

    async def test_unknown_action_raises_error(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Bilinmeyen aksiyon ValueError firlatir."""
        with pytest.raises(ValueError, match="Bilinmeyen Playwright aksiyonu"):
            await playwright_runner.execute(
                "invalid_action",
                {"url": "https://example.com"},
            )

    async def test_missing_url_returns_error(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """url parametresi olmadan hata dondurur."""
        result = await playwright_runner.execute("take_screenshot", {})
        assert result["success"] is False
        assert "url" in str(result.get("error", ""))

    async def test_empty_url_returns_error(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Bos url ile hata dondurur."""
        result = await playwright_runner.execute("take_screenshot", {"url": ""})
        assert result["success"] is False

    async def test_non_string_url_returns_error(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """String olmayan url ile hata dondurur."""
        result = await playwright_runner.execute("take_screenshot", {"url": 123})
        assert result["success"] is False


# --- take_screenshot Tests ---


class TestTakeScreenshot:
    """take_screenshot aksiyon testleri."""

    async def test_screenshot_viewport_success(
        self,
        playwright_runner: PlaywrightRunner,
        mock_s3_uploader: AsyncMock,
    ) -> None:
        """Viewport screenshot basariyla alinir ve S3'e yuklenir."""
        mock_page = _make_mock_page()
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "take_screenshot",
                {"url": "https://example.com"},
            )

        assert result["success"] is True
        assert "screenshot_url" in result
        assert result["page_title"] == "Test Page"

    async def test_screenshot_full_page(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Full page screenshot alinir."""
        mock_page = _make_mock_page()
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "take_screenshot",
                {"url": "https://example.com", "full_page": True},
            )

        assert result["success"] is True
        mock_page.screenshot.assert_called_once_with(full_page=True, type="png")

    async def test_screenshot_element(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Element screenshot alinir."""
        mock_page = _make_mock_page()
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "take_screenshot",
                {"url": "https://example.com", "selector": "#main-content"},
            )

        assert result["success"] is True
        mock_page.wait_for_selector.assert_called_once()

    async def test_screenshot_element_not_found(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Element bulunamadiginda hata dondurur."""
        mock_page = _make_mock_page()
        mock_page.wait_for_selector = AsyncMock(return_value=None)
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "take_screenshot",
                {"url": "https://example.com", "selector": "#nonexistent"},
            )

        assert result["success"] is False
        assert "bulunamadi" in str(result.get("error", ""))

    async def test_screenshot_s3_failure_falls_back_to_base64(
        self,
        playwright_runner: PlaywrightRunner,
        mock_s3_uploader: AsyncMock,
    ) -> None:
        """S3 upload basarisiz olursa base64 fallback kullanilir."""
        mock_s3_uploader.upload_bytes.side_effect = S3UploadError("S3 down")
        mock_page = _make_mock_page()
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "take_screenshot",
                {"url": "https://example.com"},
            )

        assert result["success"] is True
        assert "screenshot_base64" in result
        assert "screenshot_url" not in result

    async def test_screenshot_no_s3_uploader_returns_base64(
        self,
        playwright_runner_no_s3: PlaywrightRunner,
    ) -> None:
        """S3 uploader yoksa base64 dondurur."""
        mock_page = _make_mock_page()
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner_no_s3.execute(
                "take_screenshot",
                {"url": "https://example.com"},
            )

        assert result["success"] is True
        assert "screenshot_base64" in result

    async def test_screenshot_playwright_not_installed(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Playwright yuklu degilse hata dondurur."""
        with patch.dict(sys.modules, {"playwright.async_api": None}):
            result = await playwright_runner.execute(
                "take_screenshot",
                {"url": "https://example.com"},
            )

        assert result["success"] is False
        assert "Playwright yuklu degil" in str(result.get("error", ""))

    async def test_screenshot_custom_viewport(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Ozel viewport boyutlari kullanilir."""
        mock_page = _make_mock_page()
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "take_screenshot",
                {
                    "url": "https://example.com",
                    "viewport_width": 800,
                    "viewport_height": 600,
                },
            )

        assert result["success"] is True

    async def test_screenshot_invalid_viewport_uses_default(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Gecersiz viewport degerleri varsayilana doner."""
        mock_page = _make_mock_page()
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "take_screenshot",
                {
                    "url": "https://example.com",
                    "viewport_width": -1,
                    "viewport_height": "invalid",
                },
            )

        assert result["success"] is True

    async def test_screenshot_page_error(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Sayfa yukleme hatasi durumunda hata dondurur."""
        mock_page = _make_mock_page()
        mock_page.goto = AsyncMock(side_effect=Exception("net::ERR_NAME_NOT_RESOLVED"))
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "take_screenshot",
                {"url": "https://invalid-domain.example.com"},
            )

        assert result["success"] is False
        assert "Screenshot alinamadi" in str(result.get("error", ""))


# --- check_page_load Tests ---


class TestCheckPageLoad:
    """check_page_load aksiyon testleri."""

    async def test_page_load_success(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Sayfa basariyla yuklenir."""
        mock_page = _make_mock_page(goto_response_status=200)
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "check_page_load",
                {"url": "https://example.com"},
            )

        assert result["success"] is True
        assert result["page_title"] == "Test Page"
        assert result["status_code"] == 200
        assert "load_time_ms" in result

    async def test_page_load_with_wait_until(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Ozel wait_until parametresi kullanilir."""
        mock_page = _make_mock_page()
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "check_page_load",
                {"url": "https://example.com", "wait_until": "networkidle"},
            )

        assert result["success"] is True
        assert result["wait_until"] == "networkidle"

    async def test_page_load_invalid_wait_until_uses_default(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Gecersiz wait_until degeri varsayilana doner."""
        mock_page = _make_mock_page()
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "check_page_load",
                {"url": "https://example.com", "wait_until": "invalid"},
            )

        assert result["success"] is True
        assert result["wait_until"] == "load"

    async def test_page_load_timeout(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Sayfa yukleme zamani asimi."""
        mock_page = _make_mock_page()
        mock_page.goto = AsyncMock(side_effect=Exception("Timeout 5000ms exceeded"))
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "check_page_load",
                {"url": "https://slow.example.com", "timeout": 1},
            )

        assert result["success"] is False
        assert "yuklenemedi" in str(result.get("error", ""))
        assert "load_time_ms" in result

    async def test_page_load_playwright_not_installed(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Playwright yuklu degilse hata dondurur."""
        with patch.dict(sys.modules, {"playwright.async_api": None}):
            result = await playwright_runner.execute(
                "check_page_load",
                {"url": "https://example.com"},
            )

        assert result["success"] is False

    async def test_page_load_invalid_timeout_uses_default(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Gecersiz timeout degeri varsayilana doner."""
        mock_page = _make_mock_page()
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "check_page_load",
                {"url": "https://example.com", "timeout": -1},
            )

        assert result["success"] is True


# --- check_element Tests ---


class TestCheckElement:
    """check_element aksiyon testleri."""

    async def test_element_found(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Element basariyla bulunur."""
        mock_page = _make_mock_page()
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "check_element",
                {"url": "https://example.com", "selector": "#main"},
            )

        assert result["success"] is True
        assert result["element_found"] is True
        assert result["element_text"] == "Element text"
        assert result["element_visible"] is True

    async def test_element_not_found_returns_none(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Element bulunamadiginda element_found=False dondurur."""
        mock_page = _make_mock_page()
        mock_page.wait_for_selector = AsyncMock(return_value=None)
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "check_element",
                {"url": "https://example.com", "selector": "#nonexistent"},
            )

        assert result["success"] is True
        assert result["element_found"] is False

    async def test_element_timeout(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Element bekleme zamani asimi."""
        mock_page = _make_mock_page()
        mock_page.wait_for_selector = AsyncMock(
            side_effect=Exception("Timeout 10000ms exceeded waiting for selector"),
        )
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "check_element",
                {"url": "https://example.com", "selector": "#slow-element", "timeout": 1},
            )

        assert result["success"] is True
        assert result["element_found"] is False

    async def test_element_missing_selector_returns_error(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """selector parametresi olmadan hata dondurur."""
        result = await playwright_runner.execute(
            "check_element",
            {"url": "https://example.com"},
        )
        assert result["success"] is False
        assert "selector" in str(result.get("error", ""))

    async def test_element_empty_selector_returns_error(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Bos selector ile hata dondurur."""
        result = await playwright_runner.execute(
            "check_element",
            {"url": "https://example.com", "selector": ""},
        )
        assert result["success"] is False

    async def test_element_page_error(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Sayfa yukleme hatasi durumunda hata dondurur."""
        mock_page = _make_mock_page()
        mock_page.goto = AsyncMock(side_effect=Exception("Connection refused"))
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "check_element",
                {"url": "https://example.com", "selector": "#main"},
            )

        assert result["success"] is False


# --- fill_form Tests ---


class TestFillForm:
    """fill_form aksiyon testleri."""

    async def test_fill_form_success(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Form basariyla doldurulur."""
        mock_page = _make_mock_page()
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "fill_form",
                {
                    "url": "https://example.com/form",
                    "fields": [
                        {"selector": "#name", "value": "John Doe"},
                        {"selector": "#email", "value": "john@example.com"},
                    ],
                },
            )

        assert result["success"] is True
        assert result["filled_count"] == 2
        assert result["submitted"] is False

    async def test_fill_form_with_submit(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Form doldurulup submit edilir."""
        mock_page = _make_mock_page()
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "fill_form",
                {
                    "url": "https://example.com/form",
                    "fields": [{"selector": "#name", "value": "John"}],
                    "submit_selector": "#submit-btn",
                },
            )

        assert result["success"] is True
        assert result["submitted"] is True
        mock_page.click.assert_called_once_with("#submit-btn")

    async def test_fill_form_missing_fields_returns_error(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """fields parametresi olmadan hata dondurur."""
        result = await playwright_runner.execute(
            "fill_form",
            {"url": "https://example.com/form"},
        )
        assert result["success"] is False
        assert "fields" in str(result.get("error", ""))

    async def test_fill_form_empty_fields_returns_error(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Bos fields listesi ile hata dondurur."""
        result = await playwright_runner.execute(
            "fill_form",
            {"url": "https://example.com/form", "fields": []},
        )
        assert result["success"] is False

    async def test_fill_form_invalid_field_skipped(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Gecersiz field'lar atlanir."""
        mock_page = _make_mock_page()
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "fill_form",
                {
                    "url": "https://example.com/form",
                    "fields": [
                        {"selector": "#name", "value": "John"},
                        "invalid_field",  # dict degil, atlanacak
                        {"selector": 123, "value": "test"},  # selector string degil, atlanacak
                    ],
                },
            )

        assert result["success"] is True
        assert result["filled_count"] == 1

    async def test_fill_form_page_error(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Form doldurma sirasinda hata."""
        mock_page = _make_mock_page()
        mock_page.fill = AsyncMock(side_effect=Exception("Element is not an input"))
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "fill_form",
                {
                    "url": "https://example.com/form",
                    "fields": [{"selector": "#main", "value": "test"}],
                },
            )

        assert result["success"] is False
        assert "Form doldurma basarisiz" in str(result.get("error", ""))

    async def test_fill_form_playwright_not_installed(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Playwright yuklu degilse hata dondurur."""
        with patch.dict(sys.modules, {"playwright.async_api": None}):
            result = await playwright_runner.execute(
                "fill_form",
                {
                    "url": "https://example.com/form",
                    "fields": [{"selector": "#name", "value": "John"}],
                },
            )

        assert result["success"] is False


# --- wait_for_response Tests ---


class TestWaitForResponse:
    """wait_for_response aksiyon testleri."""

    async def test_wait_for_response_success(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Network response basariyla yakalanir."""
        mock_page = _make_mock_page()

        # expect_response async context manager mock
        mock_response = MagicMock()
        mock_response.url = "https://api.example.com/data"
        mock_response.status = 200

        mock_response_info = MagicMock()

        # value, Playwright'ta async property (await edilir)
        async def _mock_value() -> MagicMock:
            return mock_response

        # PropertyMock ile async property simule et
        type(mock_response_info).value = property(lambda self: _mock_value())

        mock_expect_cm = AsyncMock()
        mock_expect_cm.__aenter__ = AsyncMock(return_value=mock_response_info)
        mock_expect_cm.__aexit__ = AsyncMock(return_value=False)

        mock_page.expect_response = MagicMock(return_value=mock_expect_cm)
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "wait_for_response",
                {
                    "url": "https://example.com",
                    "url_pattern": "**/api/**",
                },
            )

        assert result["success"] is True
        assert result["response_url"] == "https://api.example.com/data"
        assert result["response_status"] == 200
        assert "response_time_ms" in result

    async def test_wait_for_response_missing_pattern_returns_error(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """url_pattern parametresi olmadan hata dondurur."""
        result = await playwright_runner.execute(
            "wait_for_response",
            {"url": "https://example.com"},
        )
        assert result["success"] is False
        assert "url_pattern" in str(result.get("error", ""))

    async def test_wait_for_response_empty_pattern_returns_error(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Bos url_pattern ile hata dondurur."""
        result = await playwright_runner.execute(
            "wait_for_response",
            {"url": "https://example.com", "url_pattern": ""},
        )
        assert result["success"] is False

    async def test_wait_for_response_timeout(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Response bekleme zamani asimi."""
        mock_page = _make_mock_page()

        mock_expect_cm = AsyncMock()
        mock_expect_cm.__aenter__ = AsyncMock(
            side_effect=Exception("Timeout 30000ms exceeded waiting for response"),
        )
        mock_expect_cm.__aexit__ = AsyncMock(return_value=False)

        mock_page.expect_response = MagicMock(return_value=mock_expect_cm)
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.execute(
                "wait_for_response",
                {
                    "url": "https://example.com",
                    "url_pattern": "**/api/**",
                    "timeout": 1,
                },
            )

        assert result["success"] is False
        assert "zamani asimi" in str(result.get("error", ""))
        assert "response_time_ms" in result

    async def test_wait_for_response_playwright_not_installed(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """Playwright yuklu degilse hata dondurur."""
        with patch.dict(sys.modules, {"playwright.async_api": None}):
            result = await playwright_runner.execute(
                "wait_for_response",
                {"url": "https://example.com", "url_pattern": "**/api/**"},
            )

        assert result["success"] is False


# --- BaseRunner integration Tests ---


class TestBaseRunnerIntegration:
    """BaseRunner.run() ile PlaywrightRunner entegrasyon testleri."""

    async def test_run_adds_execution_time(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """BaseRunner.run() execution_time_ms ekler."""
        mock_page = _make_mock_page()
        mock_module = _patch_playwright(mock_page)

        with patch.dict(sys.modules, {"playwright.async_api": mock_module}):
            result = await playwright_runner.run(
                "check_page_load",
                {"url": "https://example.com"},
            )

        assert "execution_time_ms" in result
        assert isinstance(result["execution_time_ms"], int)

    async def test_run_unknown_action_raises_error(
        self,
        playwright_runner: PlaywrightRunner,
    ) -> None:
        """BaseRunner.run() bilinmeyen aksiyonda hata firlatir."""
        with pytest.raises(ValueError, match="Bilinmeyen Playwright aksiyonu"):
            await playwright_runner.run(
                "nonexistent",
                {"url": "https://example.com"},
            )
