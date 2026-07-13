"""Contract placeholders for direct GateRule migration.

The alpha.4 patch migrates the remaining legacy CollectorGateRule wrappers to
direct classes while preserving the public StageGateResult contract.
"""

from core.gates.rules import registered_rules


def test_remaining_stage_rules_are_direct_classes():
    rule_ids = {rule.rule_id for rule in registered_rules()}
    assert {
        "safety_finding",
        "stage1_evidence_gap",
        "stage2_policy_gap",
        "stage3_eval_failure",
        "stage4_final_governance",
    }.issubset(rule_ids)
    for rule in registered_rules():
        assert rule.__class__.__name__ != "CollectorGateRule"
