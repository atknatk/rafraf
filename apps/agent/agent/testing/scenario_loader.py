"""Senaryo yukleyici - YAML ve JSON formatindaki test dosyalarini parse eder.

Test senaryolari su formatlarda tanimlanabilir:
- JSON dosyalari (.json)
- YAML dosyalari (.yaml, .yml)

Her dosya tek bir senaryo veya birden fazla senaryodan olusan bir suite icerebilir.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from agent.testing.models import TestScenario

logger = structlog.get_logger()

# Desteklenen dosya uzantilari
_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".json", ".yaml", ".yml"})


class ScenarioLoadError(Exception):
    """Senaryo yukleme hatalarini temsil eder."""


def _parse_yaml(content: str) -> object:
    """YAML icerigini parse eder.

    Args:
        content: YAML string.

    Returns:
        Parse edilmis veri.

    Raises:
        ScenarioLoadError: PyYAML yuklu degil veya parse hatasi.
    """
    try:
        import yaml
    except ImportError as exc:
        msg = "PyYAML yuklu degil. 'pip install pyyaml' ile yukleyin."
        raise ScenarioLoadError(msg) from exc

    try:
        result: object = yaml.safe_load(content)
        return result
    except yaml.YAMLError as exc:
        msg = f"YAML parse hatasi: {exc}"
        raise ScenarioLoadError(msg) from exc


class ScenarioLoader:
    """Test senaryo dosyalarini yukler ve parse eder.

    JSON ve YAML formatlarini destekler. Tek dosya veya dizin bazli
    yukleme yapabilir.
    """

    def load_file(self, file_path: Path | str) -> list[TestScenario]:
        """Tek bir senaryo dosyasini yukler.

        Args:
            file_path: Senaryo dosyasi yolu (.json, .yaml, .yml).

        Returns:
            Parse edilen senaryo listesi.

        Raises:
            ScenarioLoadError: Dosya bulunamadi, desteklenmeyen format, parse hatasi.
        """
        path = Path(file_path)

        if not path.exists():
            msg = f"Senaryo dosyasi bulunamadi: {path}"
            raise ScenarioLoadError(msg)

        if not path.is_file():
            msg = f"Yol bir dosya degil: {path}"
            raise ScenarioLoadError(msg)

        if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            msg = (
                f"Desteklenmeyen dosya formati: '{path.suffix}'. "
                f"Desteklenen formatlar: {sorted(_SUPPORTED_EXTENSIONS)}"
            )
            raise ScenarioLoadError(msg)

        content = path.read_text(encoding="utf-8")

        if path.suffix.lower() == ".json":
            data = self._parse_json(content, path)
        else:
            data = self._parse_yaml_file(content, path)

        return self._build_scenarios(data, path)

    def load_directory(self, dir_path: Path | str) -> list[TestScenario]:
        """Bir dizindeki tum senaryo dosyalarini yukler.

        Args:
            dir_path: Senaryo dosyalarinin bulundugu dizin.

        Returns:
            Tum senaryolarin birlesmis listesi.

        Raises:
            ScenarioLoadError: Dizin bulunamadi.
        """
        path = Path(dir_path)

        if not path.exists():
            msg = f"Dizin bulunamadi: {path}"
            raise ScenarioLoadError(msg)

        if not path.is_dir():
            msg = f"Yol bir dizin degil: {path}"
            raise ScenarioLoadError(msg)

        scenarios: list[TestScenario] = []
        files = sorted(f for f in path.iterdir() if f.suffix.lower() in _SUPPORTED_EXTENSIONS)

        for file_path in files:
            try:
                file_scenarios = self.load_file(file_path)
                scenarios.extend(file_scenarios)
            except ScenarioLoadError:
                # Hatayi logla ama diger dosyalara devam et
                structlog.get_logger().warning(
                    "Senaryo dosyasi yuklenemedi, atlaniyor",
                    file=str(file_path),
                )

        return scenarios

    def load_from_dict(self, data: dict[str, object]) -> TestScenario:
        """Dictionary'den tek bir senaryo olusturur.

        Args:
            data: Senaryo verisi (dict).

        Returns:
            TestScenario instance.

        Raises:
            ScenarioLoadError: Gecersiz veri formati.
        """
        try:
            return TestScenario.model_validate(data)
        except Exception as exc:
            msg = f"Senaryo parse hatasi: {exc}"
            raise ScenarioLoadError(msg) from exc

    def _parse_json(self, content: str, path: Path) -> object:
        """JSON dosyasini parse eder.

        Args:
            content: JSON string.
            path: Dosya yolu (hata mesaji icin).

        Returns:
            Parse edilmis veri.

        Raises:
            ScenarioLoadError: JSON parse hatasi.
        """
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            msg = f"JSON parse hatasi ({path}): {exc}"
            raise ScenarioLoadError(msg) from exc

    def _parse_yaml_file(self, content: str, path: Path) -> object:
        """YAML dosyasini parse eder.

        Args:
            content: YAML string.
            path: Dosya yolu (hata mesaji icin).

        Returns:
            Parse edilmis veri.

        Raises:
            ScenarioLoadError: YAML parse hatasi.
        """
        try:
            return _parse_yaml(content)
        except ScenarioLoadError:
            raise
        except Exception as exc:
            msg = f"YAML parse hatasi ({path}): {exc}"
            raise ScenarioLoadError(msg) from exc

    def _build_scenarios(
        self,
        data: object,
        source_path: Path,
    ) -> list[TestScenario]:
        """Ham veriyi TestScenario listesine donusturur.

        Desteklenen formatlar:
        - Tek senaryo: {"name": "...", "steps": [...]}
        - Suite: {"scenarios": [...]}
        - Liste: [{"name": "...", ...}, ...]

        Args:
            data: Parse edilmis ham veri.
            source_path: Kaynak dosya yolu (hata mesaji icin).

        Returns:
            TestScenario listesi.

        Raises:
            ScenarioLoadError: Gecersiz veri formati.
        """
        if isinstance(data, dict):
            # Suite formati: {"scenarios": [...]}
            if "scenarios" in data:
                scenario_list = data["scenarios"]
                if not isinstance(scenario_list, list):
                    msg = f"'scenarios' bir liste olmali ({source_path})"
                    raise ScenarioLoadError(msg)
                return [
                    self._validate_scenario(item, source_path)
                    for item in scenario_list
                    if isinstance(item, dict)
                ]

            # Tek senaryo formati: {"name": "...", "steps": [...]}
            if "name" in data:
                return [self._validate_scenario(data, source_path)]

            msg = (
                f"Gecersiz senaryo formati: 'name' veya 'scenarios' "
                f"anahtari gerekli ({source_path})"
            )
            raise ScenarioLoadError(msg)

        if isinstance(data, list):
            return [
                self._validate_scenario(item, source_path)
                for item in data
                if isinstance(item, dict)
            ]

        msg = f"Gecersiz senaryo veri tipi: {type(data).__name__} ({source_path})"
        raise ScenarioLoadError(msg)

    def _validate_scenario(
        self,
        data: dict[str, object],
        source_path: Path,
    ) -> TestScenario:
        """Senaryo verisini dogrular ve model olusturur.

        Args:
            data: Senaryo dictionary'si.
            source_path: Kaynak dosya yolu (hata mesaji icin).

        Returns:
            TestScenario instance.

        Raises:
            ScenarioLoadError: Dogrulama hatasi.
        """
        try:
            return TestScenario.model_validate(data)
        except Exception as exc:
            name = data.get("name", "<isimsiz>")
            msg = f"Senaryo dogrulama hatasi '{name}' ({source_path}): {exc}"
            raise ScenarioLoadError(msg) from exc
