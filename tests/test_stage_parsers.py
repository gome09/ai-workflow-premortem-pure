# tests/test_stage_parsers.py
from __future__ import annotations

from core.config import settings
from core.models import Stage2Output, WorkflowNode
from stages.stage_1_failure_mode import Stage1Executor
from stages.stage_2_workflow_design import Stage2Executor
from stages.stage_4_trigger import Stage4Executor


class TestStage1Parser:
    def setup_method(self):
        self.executor = Stage1Executor()

    def test_parse_standard_table(self, base_ctx):
        raw_text = """
## 失败模式分析

| 失败模式ID | 类别 | 具体描述 | 严重程度 | 依据来源 |
|-----------|------|----------|----------|----------|
| FM-001 | 幻觉 | 虚构法律条文编号 | high | 多份评测报告 |
| FM-002 | 推理断链 | 在复杂条件判断中跳步 | medium | 内部测试 |
| FM-003 | 格式不稳定 | 输出格式随机变化【需核验】 | low | 用户反馈 |

## 直接结论：
GPT-4o 在法律文书领域最核心风险是幻觉，需要强制人工核验机制。
        """
        updated_ctx = self.executor.parse_output(raw_text, base_ctx)

        assert updated_ctx.stage_1_output is not None
        assert len(updated_ctx.stage_1_output.failure_modes) == 3
        assert updated_ctx.stage_1_output.failure_modes[0].id == "FM-001"
        assert updated_ctx.stage_1_output.failure_modes[0].severity == "high"
        assert updated_ctx.stage_1_output.failure_modes[2].needs_verification is True
        assert "幻觉" in updated_ctx.stage_1_output.direct_conclusion

    def test_parse_preserves_existing_sources(self, base_ctx):
        """解析不应清空已有的搜索来源"""
        from core.models import Stage1Output

        base_ctx.stage_1_output = Stage1Output(search_sources=["https://existing-source.com"])
        raw_text = "| FM-001 | 幻觉 | 描述 | high | 来源 |"
        updated_ctx = self.executor.parse_output(raw_text, base_ctx)
        assert "https://existing-source.com" in updated_ctx.stage_1_output.search_sources

    def test_parse_empty_output_gracefully(self, base_ctx):
        """AI 输出格式异常时，不应抛出异常"""
        raw_text = "抱歉，我无法分析这个请求。"
        updated_ctx = self.executor.parse_output(raw_text, base_ctx)
        # 不应抛出，failure_modes 应为空列表
        assert updated_ctx.stage_1_output is not None
        assert updated_ctx.stage_1_output.failure_modes == []


class TestStage2Parser:
    def setup_method(self):
        self.executor = Stage2Executor()

    def test_parse_workflow_table(self, ctx_with_stage1):
        raw_text = """
## 工作流设计

| 节点ID | 阶段名称 | 分配模型/模式 | 人工动作 | 检查标准 | 覆盖的失败模式ID |
|--------|----------|--------------|----------|----------|----------------|
| N-01 | 文书初稿生成 | GPT-4o | 逐条核对法律条文编号 | 所有引用条文可在官方数据库验证 | FM-001 |
| N-02 | 逻辑一致性检查 | Claude | 对比前后条款逻辑 | 无矛盾条款，条件判断完整 | FM-002 |

```prompt
你是一位法律文书起草助手...
        """
        updated_ctx = self.executor.parse_output(raw_text, ctx_with_stage1)

        assert updated_ctx.stage_2_output is not None
        assert len(updated_ctx.stage_2_output.workflow_nodes) == 2
        assert updated_ctx.stage_2_output.workflow_nodes[0].node_id == "N-01"
        assert "FM-001" in updated_ctx.stage_2_output.workflow_nodes[0].failure_modes_addressed
        assert updated_ctx.stage_2_output.total_stages == 2


class TestStage4Prompt:
    def setup_method(self):
        self.executor = Stage4Executor()

    def _ctx_with_stage2(self, ctx_with_stage1):
        ctx_with_stage1.stage_2_output = Stage2Output(
            workflow_nodes=[
                WorkflowNode(
                    node_id="N-01",
                    stage_name="文书初稿生成",
                    model_assigned="GPT-4o",
                    human_action="核验法律条文",
                    check_criteria="引用条文可验证",
                    failure_modes_addressed=["FM-001"],
                    prompt_template="请生成文书初稿",
                )
            ],
            total_stages=1,
        )
        return ctx_with_stage1

    def test_build_system_prompt_uses_json_first_schema_by_default(self, ctx_with_stage1):
        ctx = self._ctx_with_stage2(ctx_with_stage1)

        prompt = self.executor.build_system_prompt(ctx)

        assert '"trigger_methods"' in prompt
        assert '"node_id"' in prompt
        assert "节点 <节点ID>：<阶段名称>" not in prompt
        assert "{node_id}" not in prompt
        assert "N-01" in prompt

    def test_build_system_prompt_keeps_markdown_legacy_fallback(self, ctx_with_stage1, monkeypatch):
        ctx = self._ctx_with_stage2(ctx_with_stage1)
        monkeypatch.setattr(settings, "stage_output_mode", "markdown_legacy")

        prompt = self.executor.build_system_prompt(ctx)

        assert "节点 <节点ID>：<阶段名称>" in prompt
        assert "{node_id}" not in prompt
        assert "N-01" in prompt
