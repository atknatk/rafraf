"""Unit tests for agent.testing.scenario_loader."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from agent.testing.models import StepType
from agent.testing.scenario_loader import ScenarioLoader, ScenarioLoadError


@pytest.fixture
def loader() -> ScenarioLoader:
    """ScenarioLoader instance olusturur."""
    return ScenarioLoader()


@pytest.fixture
def sample_scenario_dict() -> dict[str, object]:
    """Ornek senaryo dictionary'si."""
    return {
        "name": "Homepage Test",
        "description": "Anasayfa kontrolleri",
        "base_url": "https://example.com",
        "tags": ["smoke"],
        "steps": [
            {
                "name": "Sayfa Yukleme",
                "type": "page_load",
                "url": "/",
                "assertions": [
                    {"type": "status_code", "expected": 200},
                    {"type": "title_contains", "expected": "Example"},
                ],
            },
        ],
    }


@pytest.fixture
def sample_suite_dict(sample_scenario_dict: dict[str, object]) -> dict[str, object]:
    """Ornek suite dictionary'si."""
    return {
        "scenarios": [
            sample_scenario_dict,
            {
                "name": "About Page Test",
                "steps": [
                    {
                        "name": "About Yukleme",
                        "type": "page_load",
                        "url": "https://example.com/about",
                    },
                ],
            },
        ],
    }


# --- load_from_dict Tests ---


class TestLoadFromDict:
    """ScenarioLoader.load_from_dict() testleri."""

    def test_load_valid_scenario(
        self,
        loader: ScenarioLoader,
        sample_scenario_dict: dict[str, object],
    ) -> None:
        """Gecerli dictionary'den senaryo olusturulur."""
        scenario = loader.load_from_dict(sample_scenario_dict)
        assert scenario.name == "Homepage Test"
        assert scenario.description == "Anasayfa kontrolleri"
        assert scenario.base_url == "https://example.com"
        assert len(scenario.steps) == 1
        assert scenario.steps[0].type == StepType.PAGE_LOAD

    def test_load_minimal_scenario(self, loader: ScenarioLoader) -> None:
        """Minimum parametrelerle senaryo olusturulur."""
        scenario = loader.load_from_dict({"name": "Minimal"})
        assert scenario.name == "Minimal"
        assert scenario.steps == []

    def test_load_invalid_data_raises_error(self, loader: ScenarioLoader) -> None:
        """Gecersiz veri ile hata firlatir."""
        with pytest.raises(ScenarioLoadError, match="parse hatasi"):
            loader.load_from_dict({"invalid": "data"})

    def test_load_with_assertions(self, loader: ScenarioLoader) -> None:
        """Assertion'li senaryo olusturulur."""
        scenario = loader.load_from_dict(
            {
                "name": "Assertion Test",
                "steps": [
                    {
                        "name": "Check Element",
                        "type": "check_element",
                        "url": "https://example.com",
                        "params": {"selector": "#main"},
                        "assertions": [
                            {"type": "element_exists", "expected": True},
                            {"type": "element_visible", "expected": True},
                        ],
                    },
                ],
            },
        )
        assert len(scenario.steps[0].assertions) == 2


# --- load_file Tests (JSON) ---


class TestLoadFileJson:
    """ScenarioLoader.load_file() JSON dosya testleri."""

    def test_load_single_scenario_json(
        self,
        loader: ScenarioLoader,
        sample_scenario_dict: dict[str, object],
        tmp_path: Path,
    ) -> None:
        """Tek senaryolu JSON dosyasi yukler."""
        file_path = tmp_path / "test.json"
        file_path.write_text(json.dumps(sample_scenario_dict), encoding="utf-8")

        scenarios = loader.load_file(file_path)
        assert len(scenarios) == 1
        assert scenarios[0].name == "Homepage Test"

    def test_load_suite_json(
        self,
        loader: ScenarioLoader,
        sample_suite_dict: dict[str, object],
        tmp_path: Path,
    ) -> None:
        """Suite formatli JSON dosyasi yukler."""
        file_path = tmp_path / "suite.json"
        file_path.write_text(json.dumps(sample_suite_dict), encoding="utf-8")

        scenarios = loader.load_file(file_path)
        assert len(scenarios) == 2
        assert scenarios[0].name == "Homepage Test"
        assert scenarios[1].name == "About Page Test"

    def test_load_list_json(
        self,
        loader: ScenarioLoader,
        tmp_path: Path,
    ) -> None:
        """Liste formatli JSON dosyasi yukler."""
        data = [
            {"name": "Scenario 1", "steps": []},
            {"name": "Scenario 2", "steps": []},
        ]
        file_path = tmp_path / "list.json"
        file_path.write_text(json.dumps(data), encoding="utf-8")

        scenarios = loader.load_file(file_path)
        assert len(scenarios) == 2

    def test_load_invalid_json_raises_error(
        self,
        loader: ScenarioLoader,
        tmp_path: Path,
    ) -> None:
        """Gecersiz JSON dosyasi hata firlatir."""
        file_path = tmp_path / "invalid.json"
        file_path.write_text("{invalid json}", encoding="utf-8")

        with pytest.raises(ScenarioLoadError, match="JSON parse hatasi"):
            loader.load_file(file_path)


# --- load_file Tests (YAML) ---


class TestLoadFileYaml:
    """ScenarioLoader.load_file() YAML dosya testleri."""

    def test_load_single_scenario_yaml(
        self,
        loader: ScenarioLoader,
        tmp_path: Path,
    ) -> None:
        """Tek senaryolu YAML dosyasi yukler."""
        yaml_content = textwrap.dedent("""\
            name: Homepage Test
            description: Anasayfa kontrolleri
            base_url: https://example.com
            steps:
              - name: Sayfa Yukleme
                type: page_load
                url: /
                assertions:
                  - type: status_code
                    expected: 200
        """)
        file_path = tmp_path / "test.yaml"
        file_path.write_text(yaml_content, encoding="utf-8")

        scenarios = loader.load_file(file_path)
        assert len(scenarios) == 1
        assert scenarios[0].name == "Homepage Test"
        assert len(scenarios[0].steps) == 1

    def test_load_suite_yaml(
        self,
        loader: ScenarioLoader,
        tmp_path: Path,
    ) -> None:
        """Suite formatli YAML dosyasi yukler."""
        yaml_content = textwrap.dedent("""\
            scenarios:
              - name: Scenario 1
                steps:
                  - name: Step 1
                    type: page_load
                    url: https://example.com
              - name: Scenario 2
                steps:
                  - name: Step 2
                    type: check_element
                    url: https://example.com
                    params:
                      selector: "#main"
        """)
        file_path = tmp_path / "suite.yml"
        file_path.write_text(yaml_content, encoding="utf-8")

        scenarios = loader.load_file(file_path)
        assert len(scenarios) == 2

    def test_load_yml_extension(
        self,
        loader: ScenarioLoader,
        tmp_path: Path,
    ) -> None:
        """.yml uzantisi da desteklenir."""
        yaml_content = "name: YML Test\nsteps: []\n"
        file_path = tmp_path / "test.yml"
        file_path.write_text(yaml_content, encoding="utf-8")

        scenarios = loader.load_file(file_path)
        assert len(scenarios) == 1
        assert scenarios[0].name == "YML Test"


# --- load_file Error Tests ---


class TestLoadFileErrors:
    """ScenarioLoader.load_file() hata testleri."""

    def test_file_not_found_raises_error(self, loader: ScenarioLoader) -> None:
        """Var olmayan dosya hata firlatir."""
        with pytest.raises(ScenarioLoadError, match="bulunamadi"):
            loader.load_file(Path("/nonexistent/file.json"))

    def test_not_a_file_raises_error(
        self,
        loader: ScenarioLoader,
        tmp_path: Path,
    ) -> None:
        """Dizin yolu hata firlatir."""
        with pytest.raises(ScenarioLoadError, match="dosya degil"):
            loader.load_file(tmp_path)

    def test_unsupported_extension_raises_error(
        self,
        loader: ScenarioLoader,
        tmp_path: Path,
    ) -> None:
        """Desteklenmeyen uzanti hata firlatir."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("data", encoding="utf-8")

        with pytest.raises(ScenarioLoadError, match="Desteklenmeyen dosya formati"):
            loader.load_file(file_path)

    def test_invalid_format_no_name_raises_error(
        self,
        loader: ScenarioLoader,
        tmp_path: Path,
    ) -> None:
        """name veya scenarios anahtari olmayan dict hata firlatir."""
        file_path = tmp_path / "bad.json"
        file_path.write_text('{"key": "value"}', encoding="utf-8")

        with pytest.raises(ScenarioLoadError, match="Gecersiz senaryo formati"):
            loader.load_file(file_path)

    def test_invalid_data_type_raises_error(
        self,
        loader: ScenarioLoader,
        tmp_path: Path,
    ) -> None:
        """String veri tipi hata firlatir."""
        file_path = tmp_path / "string.json"
        file_path.write_text('"just a string"', encoding="utf-8")

        with pytest.raises(ScenarioLoadError, match="Gecersiz senaryo veri tipi"):
            loader.load_file(file_path)

    def test_invalid_scenarios_field_raises_error(
        self,
        loader: ScenarioLoader,
        tmp_path: Path,
    ) -> None:
        """scenarios alani liste degilse hata firlatir."""
        file_path = tmp_path / "bad_suite.json"
        file_path.write_text('{"scenarios": "not a list"}', encoding="utf-8")

        with pytest.raises(ScenarioLoadError, match="bir liste olmali"):
            loader.load_file(file_path)


# --- load_directory Tests ---


class TestLoadDirectory:
    """ScenarioLoader.load_directory() testleri."""

    def test_load_directory_multiple_files(
        self,
        loader: ScenarioLoader,
        tmp_path: Path,
    ) -> None:
        """Dizindeki tum senaryo dosyalarini yukler."""
        # JSON dosyasi
        json_data = {"name": "JSON Scenario", "steps": []}
        (tmp_path / "test1.json").write_text(
            json.dumps(json_data),
            encoding="utf-8",
        )

        # YAML dosyasi
        yaml_content = "name: YAML Scenario\nsteps: []\n"
        (tmp_path / "test2.yaml").write_text(yaml_content, encoding="utf-8")

        scenarios = loader.load_directory(tmp_path)
        assert len(scenarios) == 2

    def test_load_directory_skips_unsupported(
        self,
        loader: ScenarioLoader,
        tmp_path: Path,
    ) -> None:
        """Desteklenmeyen dosyalari atlar."""
        json_data = {"name": "Valid", "steps": []}
        (tmp_path / "valid.json").write_text(
            json.dumps(json_data),
            encoding="utf-8",
        )
        (tmp_path / "readme.txt").write_text("not a scenario", encoding="utf-8")

        scenarios = loader.load_directory(tmp_path)
        assert len(scenarios) == 1

    def test_load_directory_empty(
        self,
        loader: ScenarioLoader,
        tmp_path: Path,
    ) -> None:
        """Bos dizin bos liste dondurur."""
        scenarios = loader.load_directory(tmp_path)
        assert scenarios == []

    def test_load_directory_not_found_raises_error(
        self,
        loader: ScenarioLoader,
    ) -> None:
        """Var olmayan dizin hata firlatir."""
        with pytest.raises(ScenarioLoadError, match="Dizin bulunamadi"):
            loader.load_directory(Path("/nonexistent/dir"))

    def test_load_directory_not_a_dir_raises_error(
        self,
        loader: ScenarioLoader,
        tmp_path: Path,
    ) -> None:
        """Dosya yolu dizin olarak hata firlatir."""
        file_path = tmp_path / "file.json"
        file_path.write_text("{}", encoding="utf-8")

        with pytest.raises(ScenarioLoadError, match="dizin degil"):
            loader.load_directory(file_path)

    def test_load_directory_skips_invalid_files(
        self,
        loader: ScenarioLoader,
        tmp_path: Path,
    ) -> None:
        """Gecersiz dosyalari atlayip digerleriyle devam eder."""
        # Gecerli dosya
        valid_data = {"name": "Valid", "steps": []}
        (tmp_path / "a_valid.json").write_text(
            json.dumps(valid_data),
            encoding="utf-8",
        )

        # Gecersiz JSON
        (tmp_path / "b_invalid.json").write_text("{bad json}", encoding="utf-8")

        scenarios = loader.load_directory(tmp_path)
        assert len(scenarios) == 1
        assert scenarios[0].name == "Valid"
