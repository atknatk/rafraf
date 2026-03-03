"""Visual regression - screenshot karsilastirma modulu.

Baseline screenshot'lar ile yeni screenshot'lari piksel bazinda karsilastirir.
Tolerans destegi ile kucuk farkliliklari kabul eder.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger()


class VisualRegressionError(Exception):
    """Visual regression islemlerine ozel hata sinifi."""


@dataclass(frozen=True)
class ComparisonResult:
    """Screenshot karsilastirma sonucu.

    Attributes:
        matched: Eslesme basarili mi.
        diff_ratio: Farklilik orani (0.0 = tamamen ayni, 1.0 = tamamen farkli).
        tolerance: Kullanilan tolerans degeri.
        baseline_hash: Baseline screenshot hash'i.
        current_hash: Yeni screenshot hash'i.
        message: Detay mesaji.
    """

    matched: bool
    diff_ratio: float
    tolerance: float
    baseline_hash: str
    current_hash: str
    message: str


def _compute_hash(data: bytes) -> str:
    """Byte verisi icin SHA-256 hash hesaplar.

    Args:
        data: Hash'lenecek veri.

    Returns:
        Hex-encoded SHA-256 hash.
    """
    return hashlib.sha256(data).hexdigest()


def _pixel_diff_ratio(baseline: bytes, current: bytes) -> float:
    """Iki byte dizisi arasindaki farklilik oranini hesaplar.

    Piksel bazinda basit karsilastirma yapar. Eger PNG goruntu verisi
    ayristirilamiyorsa byte-level diff kullanir.

    Args:
        baseline: Referans screenshot byte verisi.
        current: Yeni screenshot byte verisi.

    Returns:
        Farklilik orani (0.0-1.0). 0.0 = tamamen ayni.
    """
    # Birebir ayni ise hizli cikis
    if baseline == current:
        return 0.0

    # PNG goruntu verisi icin piksel bazinda karsilastirma
    try:
        baseline_pixels = _extract_raw_pixels(baseline)
        current_pixels = _extract_raw_pixels(current)

        if baseline_pixels is not None and current_pixels is not None:
            return _compare_pixel_data(baseline_pixels, current_pixels)
    except Exception:
        pass

    # Fallback: byte-level karsilastirma
    return _byte_level_diff(baseline, current)


def _extract_raw_pixels(png_data: bytes) -> bytes | None:
    """PNG verisinden ham piksel verisini cikarir.

    Basit PNG parser - IDAT chunk'larini ayristirmaz, sadece
    tum veriyi ham olarak dondurur. Gercek piksel karsilastirma
    icin PIL gibi kutuphane gerekir ama dependency eklemek
    istemedigimiz icin basit yaklasim kullaniyoruz.

    Args:
        png_data: PNG dosya verisi.

    Returns:
        Ham veri veya None (PNG degilse).
    """
    # PNG signature kontrolu
    if not png_data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None

    # PNG header'dan sonraki veriyi dondur (basit yaklasim)
    return png_data[8:]


def _compare_pixel_data(baseline: bytes, current: bytes) -> float:
    """Iki piksel verisi arasindaki farklilik oranini hesaplar.

    Args:
        baseline: Referans piksel verisi.
        current: Yeni piksel verisi.

    Returns:
        Farklilik orani (0.0-1.0).
    """
    # Uzunluk farki varsa, en buyuk uzunlugu baz al
    max_len = max(len(baseline), len(current))
    if max_len == 0:
        return 0.0

    # Farkli byte sayisini hesapla
    diff_count = 0
    min_len = min(len(baseline), len(current))

    for i in range(min_len):
        if baseline[i] != current[i]:
            diff_count += 1

    # Uzunluk farki da diff sayilir
    diff_count += abs(len(baseline) - len(current))

    return diff_count / max_len


def _byte_level_diff(baseline: bytes, current: bytes) -> float:
    """Byte seviyesinde farklilik orani hesaplar (fallback).

    Args:
        baseline: Referans veri.
        current: Yeni veri.

    Returns:
        Farklilik orani (0.0-1.0).
    """
    max_len = max(len(baseline), len(current))
    if max_len == 0:
        return 0.0

    diff_count = 0
    min_len = min(len(baseline), len(current))

    for i in range(min_len):
        if baseline[i] != current[i]:
            diff_count += 1

    diff_count += abs(len(baseline) - len(current))
    return diff_count / max_len


class VisualRegressionChecker:
    """Screenshot karsilastirma islemlerini yoneten sinif.

    Baseline dizinindeki referans screenshot'larla yeni alinan
    screenshot'lari karsilastirir.

    Args:
        baseline_dir: Referans screenshot'larin bulundugu dizin.
    """

    def __init__(self, baseline_dir: Path | str) -> None:
        self._baseline_dir = Path(baseline_dir)

    @property
    def baseline_dir(self) -> Path:
        """Baseline dizin yolunu dondurur."""
        return self._baseline_dir

    def compare(
        self,
        screenshot_data: bytes,
        baseline_name: str,
        tolerance: float = 0.0,
    ) -> ComparisonResult:
        """Yeni screenshot'i baseline ile karsilastirir.

        Args:
            screenshot_data: Yeni screenshot byte verisi.
            baseline_name: Baseline dosya adi (ornek: "homepage.png").
            tolerance: Kabul edilebilir farklilik orani (0.0-1.0).

        Returns:
            Karsilastirma sonucu.
        """
        baseline_path = self._baseline_dir / baseline_name
        current_hash = _compute_hash(screenshot_data)

        if not baseline_path.exists():
            return ComparisonResult(
                matched=False,
                diff_ratio=1.0,
                tolerance=tolerance,
                baseline_hash="",
                current_hash=current_hash,
                message=f"Baseline bulunamadi: {baseline_name}. "
                f"Ilk calistirmada save_baseline() ile kaydedin.",
            )

        baseline_data = baseline_path.read_bytes()
        baseline_hash = _compute_hash(baseline_data)

        # Hash eslesiyorsa birebir ayni
        if baseline_hash == current_hash:
            return ComparisonResult(
                matched=True,
                diff_ratio=0.0,
                tolerance=tolerance,
                baseline_hash=baseline_hash,
                current_hash=current_hash,
                message="Screenshot baseline ile birebir ayni.",
            )

        # Piksel bazinda karsilastirma
        diff_ratio = _pixel_diff_ratio(baseline_data, screenshot_data)
        matched = diff_ratio <= tolerance

        if matched:
            message = (
                f"Farklilik orani ({diff_ratio:.4f}) tolerans siniri icinde ({tolerance:.4f})."
            )
        else:
            message = (
                f"Farklilik orani ({diff_ratio:.4f}) tolerans sinirini asiyor ({tolerance:.4f})."
            )

        return ComparisonResult(
            matched=matched,
            diff_ratio=diff_ratio,
            tolerance=tolerance,
            baseline_hash=baseline_hash,
            current_hash=current_hash,
            message=message,
        )

    def save_baseline(self, screenshot_data: bytes, baseline_name: str) -> Path:
        """Yeni baseline screenshot kaydeder.

        Args:
            screenshot_data: Screenshot byte verisi.
            baseline_name: Baseline dosya adi.

        Returns:
            Kaydedilen dosyanin yolu.

        Raises:
            VisualRegressionError: Kaydetme hatasi.
        """
        try:
            self._baseline_dir.mkdir(parents=True, exist_ok=True)
            baseline_path = self._baseline_dir / baseline_name
            baseline_path.write_bytes(screenshot_data)
            return baseline_path
        except OSError as exc:
            msg = f"Baseline kaydetme hatasi ({baseline_name}): {exc}"
            raise VisualRegressionError(msg) from exc

    def list_baselines(self) -> list[str]:
        """Mevcut baseline dosyalarinin listesini dondurur.

        Returns:
            Baseline dosya adlari listesi.
        """
        if not self._baseline_dir.exists():
            return []

        return sorted(
            f.name
            for f in self._baseline_dir.iterdir()
            if f.is_file() and f.suffix.lower() == ".png"
        )

    def has_baseline(self, baseline_name: str) -> bool:
        """Belirtilen baseline'in var olup olmadigini kontrol eder.

        Args:
            baseline_name: Baseline dosya adi.

        Returns:
            True = baseline var, False = yok.
        """
        return (self._baseline_dir / baseline_name).exists()
