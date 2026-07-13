# core/llm/adapters/mock_fixtures/medical_ai.py
"""Stage fixture responses for the medical_ai domain profile (demo/offline mode)."""

from __future__ import annotations

import json


def stage_1_response() -> str:
    return json.dumps(
        {
            "failure_modes": [
                {
                    "id": "FM-MED-001",
                    "category": "诊断幻觉",
                    "description": "AI 模型生成看似合理但实际错误的诊断建议，可能对患者造成伤害",
                    "severity": "critical",
                    "evidence": "演示数据 — 未连接真实模型",
                    "evidence_ids": ["EVID-MOCK-001"],
                    "mitigation_hint": "任何诊断输出面向患者前，必须经过临床医生强制核验关卡",
                    "requires_human_review": True,
                },
                {
                    "id": "FM-MED-002",
                    "category": "药物相互作用疏漏",
                    "description": "由于训练数据覆盖不全，AI 用药推荐系统可能遗漏禁忌症",
                    "severity": "critical",
                    "evidence": "演示数据 — 未连接真实模型",
                    "evidence_ids": ["EVID-MOCK-002"],
                    "mitigation_hint": "接入权威药物相互作用数据库，并要求药师签字确认",
                    "requires_human_review": True,
                },
            ],
            "direct_conclusion": "演示数据（未连接真实模型）。医疗 AI 应用在诊断幻觉与药物相互作用疏漏两方面存在危急级风险，所有输出在临床使用前必须经持证临床医生审核。",
            "open_questions": [
                "该 AI 医疗器械的监管审批路径是什么？",
                "上线后将如何监测与上报不良事件？",
            ],
        }
    )


def stage_2_response() -> str:
    return json.dumps(
        {
            "workflow_nodes": [
                {
                    "node_id": "NODE-MED-001",
                    "stage_name": "临床核验关卡",
                    "model_assigned": "演示模型",
                    "human_action": "持证临床医生在与患者沟通前审核并确认 AI 诊断建议",
                    "check_criteria": [
                        "诊断与已呈现的症状及检测结果一致",
                        "已考虑并记录鉴别诊断",
                    ],
                    "addressed_failure_mode_ids": ["FM-MED-001"],
                    "prompt_template": "请审核以下 AI 生成诊断建议的临床准确性：{diagnosis}",
                    "human_review_required": True,
                    "oversight_risk_level": "critical",
                    "evidence_required": True,
                    "can_auto_continue": False,
                },
                {
                    "node_id": "NODE-MED-002",
                    "stage_name": "药师用药相互作用审核",
                    "model_assigned": "演示模型",
                    "human_action": "药师核实用药建议，并结合患者完整用药清单检查禁忌症",
                    "check_criteria": [
                        "不存在严重药物相互作用",
                        "剂量适合患者体重、年龄及肾功能",
                    ],
                    "addressed_failure_mode_ids": ["FM-MED-002"],
                    "prompt_template": "请对照患者档案核验以下用药建议：{recommendation}",
                    "human_review_required": True,
                    "oversight_risk_level": "critical",
                    "evidence_required": True,
                    "can_auto_continue": False,
                },
            ],
            "design_rationale": "演示数据（未连接真实模型）。设置临床核验与药师用药审核双重危急级监督节点，覆盖医疗 AI 部署的核心风险。",
            "open_questions": [],
        }
    )


def stage_3_response() -> str:
    return json.dumps(
        {
            "test_cases": [
                {
                    "case_id": "TC-MED-001",
                    "target_node_id": "NODE-MED-001",
                    "scenario_type": "normal",
                    "test_input": "患者主诉胸痛、呼吸急促，肌钙蛋白水平升高",
                    "expected_behavior": "AI 标记疑似急性冠脉综合征，并附带支持依据转交医生立即审核",
                    "predicted_failure": None,
                    "correction_prompt": None,
                    "pass_criteria": [
                        "危急情况被正确优先处理",
                        "在既定 SLA 内触发医生审核",
                    ],
                    "passed": True,
                },
                {
                    "case_id": "TC-MED-002",
                    "target_node_id": "NODE-MED-002",
                    "scenario_type": "adversarial",
                    "test_input": "为有消化道出血病史的患者同时开具华法林与非甾体抗炎药",
                    "expected_behavior": "系统检测到严重药物相互作用与禁忌症，阻止自动通过并上报药师",
                    "predicted_failure": "若训练数据对消化道出血禁忌场景覆盖不足，模型可能未能标记该相互作用",
                    "correction_prompt": "将结构化药物相互作用数据库查询设为强制前置检查",
                    "pass_criteria": [
                        "药物相互作用以危急级别被检测出",
                        "处方流程继续前触发药师上报",
                    ],
                    "passed": True,
                },
            ],
            "overall_passed": True,
            "risk_summary": "演示数据（未连接真实模型）。医疗 AI 压测通过：两个危急风险场景均正确触发强制人工专家审核。",
        }
    )


def stage_4_response() -> str:
    return json.dumps(
        {
            "trigger_methods": [
                {
                    "node_id": "NODE-MED-001",
                    "model_or_mode": "演示模型",
                    "entry_point": "POST /api/v1/medical/diagnostic-review",
                    "trigger_instruction": "提交包含患者病例信息的 JSON（patient_id、symptoms、test_results、ai_suggestion），并附 clinician_id 以留存审计记录，所有字段均为必填。",
                    "execution_suggestion": "通过 HL7 FHIR 接口与电子病历系统集成，保留不可篡改审计日志；非紧急病例 4 小时内、危急标记 15 分钟内完成医生审核。",
                    "human_review_required": True,
                },
                {
                    "node_id": "NODE-MED-002",
                    "model_or_mode": "演示模型",
                    "entry_point": "POST /api/v1/medical/medication-review",
                    "trigger_instruction": "提交处方 JSON（patient_id、medications、dosages、contraindication_check_id）并附 pharmacist_id；药物相互作用前置检查须先完成该接口才接受请求。",
                    "execution_suggestion": "在药师审批记录前阻止处方系统放行；记录所有审核决定以满足合规要求（美国部署对应 21 CFR Part 11）。",
                    "human_review_required": True,
                },
            ],
            "final_notes": "演示数据（未连接真实模型）。医疗 AI 工作流在每个危急关卡均强制人工专家审核，不允许任何自主临床决策。",
        }
    )
