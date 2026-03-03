"""Unit tests for agent.testing.visual_regression."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.testing.visual_regression import (
    ComparisonResult,
    VisualRegressionChecker,
    _byte_level_diff,
    _compute_hash,
    _pixel_diff_ratio,
)

# --- _compute_hash Tests ---


class TestComputeHash:
    """_compute_hash fonksiyon testleri."""

    def test_same_data_same_hash(self) -> None:
        """Ayni veri ayni hash uretir."""
        data = b"test data"
        assert _compute_hash(data) == _compute_hash(data)

    def test_different_data_different_hash(self) -> None:
        """Farkli veri farkli hash uretir."""
        assert _compute_hash(b"data1") != _compute_hash(b"data2")

    def test_hash_is_hex_string(self) -> None:
        """Hash hex string formatinda."""
        result = _compute_hash(b"test")
        assert len(result) == 64  # SHA-256 = 64 hex chars
        assert all(c in "0123456789abcdef" for c in result)

    def test_empty_data_produces_hash(self) -> None:
        """Bos veri icin de hash uretilir."""
        result = _compute_hash(b"")
        assert len(result) == 64


# --- _pixel_diff_ratio Tests ---


class TestPixelDiffRatio:
    """_pixel_diff_ratio fonksiyon testleri."""

    def test_identical_data_zero_diff(self) -> None:
        """Ayni veri 0.0 diff dondurur."""
        data = b"identical data"
        assert _pixel_diff_ratio(data, data) == 0.0

    def test_completely_different_data(self) -> None:
        """Tamamen farkli veri yuksek diff dondurur."""
        baseline = b"\x00" * 100
        current = b"\xff" * 100
        diff = _pixel_diff_ratio(baseline, current)
        assert diff > 0.0
        assert diff <= 1.0

    def test_different_lengths(self) -> None:
        """Farkli uzunluktaki veriler icin diff hesaplanir."""
        baseline = b"short"
        current = b"much longer data here"
        diff = _pixel_diff_ratio(baseline, current)
        assert diff > 0.0
        assert diff <= 1.0

    def test_empty_data_zero_diff(self) -> None:
        """Iki bos veri 0.0 diff dondurur."""
        assert _pixel_diff_ratio(b"", b"") == 0.0

    def test_one_empty_one_not(self) -> None:
        """Bir bos bir dolu veri icin farklilik hesaplanir."""
        diff = _pixel_diff_ratio(b"", b"data")
        assert diff > 0.0

    def test_png_data_detected(self) -> None:
        """PNG signature ile baslayan veri PNG olarak algilanir."""
        # Sahte PNG verisi (PNG signature + farkli icerik)
        png_sig = b"\x89PNG\r\n\x1a\n"
        baseline = png_sig + b"\x00" * 50
        current = png_sig + b"\x01" * 50
        diff = _pixel_diff_ratio(baseline, current)
        assert diff > 0.0


# --- _byte_level_diff Tests ---


class TestByteLevelDiff:
    """_byte_level_diff fonksiyon testleri."""

    def test_identical_zero(self) -> None:
        """Ayni veri 0.0 dondurur."""
        data = b"same"
        assert _byte_level_diff(data, data) == 0.0

    def test_empty_both_zero(self) -> None:
        """Iki bos veri 0.0 dondurur."""
        assert _byte_level_diff(b"", b"") == 0.0

    def test_one_byte_diff(self) -> None:
        """Tek byte farki dogru hesaplanir."""
        baseline = b"\x00\x00\x00\x00"
        current = b"\x00\x01\x00\x00"
        diff = _byte_level_diff(baseline, current)
        assert diff == pytest.approx(0.25)

    def test_all_different(self) -> None:
        """Tum byte'lar farkli ise 1.0 veya yakin."""
        baseline = b"\x00\x00"
        current = b"\xff\xff"
        diff = _byte_level_diff(baseline, current)
        assert diff == pytest.approx(1.0)


# --- VisualRegressionChecker Tests ---


class TestVisualRegressionChecker:
    """VisualRegressionChecker testleri."""

    @pytest.fixture
    def checker(self, tmp_path: Path) -> VisualRegressionChecker:
        """Gecici dizin ile checker olusturur."""
        baseline_dir = tmp_path / "baselines"
        baseline_dir.mkdir()
        return VisualRegressionChecker(baseline_dir=baseline_dir)

    def test_baseline_dir_property(self, checker: VisualRegressionChecker) -> None:
        """baseline_dir property dogru calisiyor."""
        assert checker.baseline_dir.exists()

    def test_compare_no_baseline_fails(
        self,
        checker: VisualRegressionChecker,
    ) -> None:
        """Baseline yoksa matched=False dondurur."""
        result = checker.compare(b"screenshot", "nonexistent.png")
        assert result.matched is False
        assert result.diff_ratio == 1.0
        assert "Baseline bulunamadi" in result.message

    def test_compare_identical_passes(
        self,
        checker: VisualRegressionChecker,
    ) -> None:
        """Birebir ayni screenshot matched=True dondurur."""
        screenshot = b"test screenshot data"
        checker.save_baseline(screenshot, "test.png")

        result = checker.compare(screenshot, "test.png")
        assert result.matched is True
        assert result.diff_ratio == 0.0
        assert result.baseline_hash == result.current_hash

    def test_compare_different_fails_without_tolerance(
        self,
        checker: VisualRegressionChecker,
    ) -> None:
        """Farkli screenshot tolerans olmadan matched=False dondurur."""
        baseline = b"baseline data"
        current = b"current data!"
        checker.save_baseline(baseline, "test.png")

        result = checker.compare(current, "test.png", tolerance=0.0)
        assert result.matched is False
        assert result.diff_ratio > 0.0

    def test_compare_with_tolerance_passes(
        self,
        checker: VisualRegressionChecker,
    ) -> None:
        """Kucuk fark tolerans icinde ise matched=True dondurur."""
        baseline = b"abcdefghij" * 10
        # Tek karakter farkli
        current = b"abcdefghij" * 9 + b"abcdefghiX"
        checker.save_baseline(baseline, "test.png")

        result = checker.compare(current, "test.png", tolerance=0.05)
        assert result.matched is True
        assert result.diff_ratio < 0.05

    def test_save_baseline_creates_file(
        self,
        checker: VisualRegressionChecker,
    ) -> None:
        """Baseline dosyasi olusturulur."""
        path = checker.save_baseline(b"data", "new_baseline.png")
        assert path.exists()
        assert path.read_bytes() == b"data"

    def test_save_baseline_creates_dirs(self, tmp_path: Path) -> None:
        """Baseline dizini yoksa olusturulur."""
        deep_dir = tmp_path / "deep" / "nested" / "dir"
        checker = VisualRegressionChecker(baseline_dir=deep_dir)

        path = checker.save_baseline(b"data", "test.png")
        assert path.exists()

    def test_list_baselines_empty(
        self,
        checker: VisualRegressionChecker,
    ) -> None:
        """Bos dizinde bos liste dondurur."""
        assert checker.list_baselines() == []

    def test_list_baselines_returns_png_files(
        self,
        checker: VisualRegressionChecker,
    ) -> None:
        """Sadece .png dosyalarini listeler."""
        checker.save_baseline(b"data1", "baseline1.png")
        checker.save_baseline(b"data2", "baseline2.png")
        # PNG olmayan dosya
        (checker.baseline_dir / "readme.txt").write_text("not a png")

        baselines = checker.list_baselines()
        assert len(baselines) == 2
        assert "baseline1.png" in baselines
        assert "baseline2.png" in baselines

    def test_list_baselines_nonexistent_dir(self, tmp_path: Path) -> None:
        """Var olmayan dizin icin bos liste dondurur."""
        checker = VisualRegressionChecker(baseline_dir=tmp_path / "nonexistent")
        assert checker.list_baselines() == []

    def test_has_baseline_true(
        self,
        checker: VisualRegressionChecker,
    ) -> None:
        """Mevcut baseline icin True dondurur."""
        checker.save_baseline(b"data", "exists.png")
        assert checker.has_baseline("exists.png") is True

    def test_has_baseline_false(
        self,
        checker: VisualRegressionChecker,
    ) -> None:
        """Mevcut olmayan baseline icin False dondurur."""
        assert checker.has_baseline("nonexistent.png") is False


# --- ComparisonResult Tests ---


class TestComparisonResult:
    """ComparisonResult dataclass testleri."""

    def test_create_result(self) -> None:
        """ComparisonResult olusturulur."""
        result = ComparisonResult(
            matched=True,
            diff_ratio=0.0,
            tolerance=0.05,
            baseline_hash="abc123",
            current_hash="abc123",
            message="Identical",
        )
        assert result.matched is True
        assert result.diff_ratio == 0.0

    def test_result_is_frozen(self) -> None:
        """ComparisonResult frozen dataclass."""
        result = ComparisonResult(
            matched=True,
            diff_ratio=0.0,
            tolerance=0.0,
            baseline_hash="a",
            current_hash="a",
            message="ok",
        )
        with pytest.raises(AttributeError):
            result.matched = False  # type: ignore[misc]
