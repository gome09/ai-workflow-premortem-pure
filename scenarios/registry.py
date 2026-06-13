from __future__ import annotations

import importlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MANIFEST_DIR = Path(__file__).resolve().parent / "manifests"


class ScenarioDefinition(BaseModel):
    scenario_id: str
    name: str
    description: str
    input_sample_path: str
    domain_profile: str = "default"
    mock_fixture: str = "default"
    default_config: dict[str, Any] = Field(default_factory=dict)
    applicable_stages: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "ScenarioDefinition":
        input_path = _REPO_ROOT / self.input_sample_path
        if not input_path.exists():
            raise ValueError(f"Scenario input sample not found: {self.input_sample_path}")
        _import_profile_module(self.domain_profile)
        _import_mock_fixture_module(self.mock_fixture)
        return self

    @property
    def absolute_input_sample_path(self) -> Path:
        return (_REPO_ROOT / self.input_sample_path).resolve()

    def to_api_dict(self, *, include_input_sample: bool = False) -> dict[str, Any]:
        payload = {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "input_sample_path": self.input_sample_path,
            "domain_profile": self.domain_profile,
            "mock_fixture": self.mock_fixture,
            "default_config": self.default_config,
            "applicable_stages": self.applicable_stages,
        }
        if include_input_sample:
            payload["input_sample"] = read_scenario_input(self.scenario_id)
        return payload


def _load_manifest(path: Path) -> ScenarioDefinition:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "scenario_id" not in data:
        data["scenario_id"] = path.stem
    return ScenarioDefinition.model_validate(data)


def _import_profile_module(profile: str):
    if not profile or profile == "default":
        return None
    return importlib.import_module(f"stages.domain_profiles.{profile}")


def _import_mock_fixture_module(mock_fixture: str):
    fixture_name = (mock_fixture or "default").strip()
    if "." in fixture_name:
        return importlib.import_module(fixture_name)
    return importlib.import_module(f"core.llm.adapters.mock_fixtures.{fixture_name}")


@lru_cache(maxsize=1)
def list_scenarios() -> list[ScenarioDefinition]:
    manifests = sorted(_MANIFEST_DIR.glob("*.json"))
    return [_load_manifest(path) for path in manifests]


@lru_cache(maxsize=64)
def get_scenario(scenario_id: str) -> ScenarioDefinition:
    for scenario in list_scenarios():
        if scenario.scenario_id == scenario_id:
            return scenario
    raise KeyError(f"Unknown scenario_id: {scenario_id}")


def read_scenario_input(scenario_id: str) -> str:
    scenario = get_scenario(scenario_id)
    return scenario.absolute_input_sample_path.read_text(encoding="utf-8")
