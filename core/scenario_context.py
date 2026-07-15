from __future__ import annotations

from typing import Any

from core.config import settings
from core.models import ProjectContext
from scenarios import get_scenario


def current_domain_profile(ctx: ProjectContext | None = None) -> str:
    if ctx and ctx.scenario_config.get("domain_profile"):
        return str(ctx.scenario_config["domain_profile"])
    if ctx and ctx.selected_scenario_id:
        try:
            return get_scenario(ctx.selected_scenario_id).domain_profile
        except KeyError:
            pass
    return settings.domain_profile


def current_mock_fixture(ctx: ProjectContext | None = None) -> str:
    if ctx and ctx.scenario_config.get("mock_fixture"):
        return str(ctx.scenario_config["mock_fixture"])
    if ctx and ctx.selected_scenario_id:
        try:
            return get_scenario(ctx.selected_scenario_id).mock_fixture
        except KeyError:
            pass
    return current_domain_profile(ctx)


def attach_scenario_to_context(ctx: ProjectContext, scenario_id: str | None) -> ProjectContext:
    if not scenario_id:
        return ctx
    scenario = get_scenario(scenario_id)
    ctx.selected_scenario_id = scenario.scenario_id
    ctx.scenario_name = scenario.name
    ctx.scenario_description = scenario.description
    merged_config: dict[str, Any] = dict(scenario.default_config)
    merged_config["domain_profile"] = scenario.domain_profile
    merged_config["mock_fixture"] = scenario.mock_fixture
    merged_config["input_sample_path"] = scenario.input_sample_path
    merged_config["applicable_stages"] = list(scenario.applicable_stages)
    ctx.scenario_config = merged_config
    return ctx
