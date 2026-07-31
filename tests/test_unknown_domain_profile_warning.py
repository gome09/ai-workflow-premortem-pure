# tests/test_unknown_domain_profile_warning.py
"""
Unknown domain profile names must not fail silently.

`get_stage_prompts` / `get_json_prompts` dispatch on a hardcoded profile list.
An unregistered profile name falls back to the default bundle, which previously
happened without any signal — a new `stages/domain_profiles/<name>.py` file would
be created and simply never used.

Coverage:
  - Unknown profile still falls back to default (behaviour unchanged)
  - Unknown profile emits a WARNING naming the profile
  - Registered profiles and the explicit "default" stay silent
"""

from __future__ import annotations

import logging

import pytest

REGISTERED_PROFILES = ("default", "university_ai", "medical_ai")


# ── get_stage_prompts ─────────────────────────────────────────────────────────


class TestGetStagePromptsUnknownProfile:
    def test_unknown_profile_falls_back_to_default_bundle(self):
        from stages.prompts import get_stage_prompts

        assert get_stage_prompts("finance_ai") == get_stage_prompts("default")

    def test_unknown_profile_emits_warning_naming_the_profile(self, caplog):
        from stages.prompts import get_stage_prompts

        with caplog.at_level(logging.WARNING, logger="stages.prompts"):
            get_stage_prompts("finance_ai")

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings, "unknown profile produced no WARNING"
        assert "finance_ai" in warnings[0].getMessage()

    @pytest.mark.parametrize("profile", REGISTERED_PROFILES)
    def test_registered_profiles_do_not_warn(self, profile, caplog):
        from stages.prompts import get_stage_prompts

        with caplog.at_level(logging.WARNING, logger="stages.prompts"):
            get_stage_prompts(profile)

        assert not [r for r in caplog.records if r.levelno == logging.WARNING]


# ── get_json_prompts ──────────────────────────────────────────────────────────


class TestGetJsonPromptsUnknownProfile:
    def test_unknown_profile_falls_back_to_default_bundle(self):
        from stages.json_prompts import get_json_prompts

        assert get_json_prompts("finance_ai") == get_json_prompts("default")

    def test_unknown_profile_emits_warning_naming_the_profile(self, caplog):
        from stages.json_prompts import get_json_prompts

        with caplog.at_level(logging.WARNING, logger="stages.json_prompts"):
            get_json_prompts("finance_ai")

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings, "unknown profile produced no WARNING"
        assert "finance_ai" in warnings[0].getMessage()

    @pytest.mark.parametrize("profile", REGISTERED_PROFILES)
    def test_registered_profiles_do_not_warn(self, profile, caplog):
        from stages.json_prompts import get_json_prompts

        with caplog.at_level(logging.WARNING, logger="stages.json_prompts"):
            get_json_prompts(profile)

        assert not [r for r in caplog.records if r.levelno == logging.WARNING]
