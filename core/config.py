# core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.execution_mode import WorkflowExecutionMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # LLM
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"

    # 不同阶段使用不同模型
    # DeepSeek 官方 V4 API 模型名：deepseek-v4-pro / deepseek-v4-flash。
    # 旧 deepseek-chat / deepseek-reasoner 已变为兼容别名，并计划退役。
    # 阶段一：V4 Pro + thinking，用于失败模式分析
    model_stage_1: str = "deepseek-v4-pro"
    # 阶段二：V4 Flash + non-thinking，用于工作流设计，速度和成本更优
    model_stage_2: str = "deepseek-v4-flash"
    # 阶段三：V4 Pro + thinking，用于压力测试 / EvalCase 生成
    model_stage_3: str = "deepseek-v4-pro"
    # 阶段四：V4 Flash + non-thinking，用于触发策略和规则性输出
    model_stage_4: str = "deepseek-v4-flash"

    # DeepSeek V4 thinking mode 控制。
    # 可选值：enabled / disabled / default。default 表示不显式传参，由服务端默认决定。
    model_stage_1_thinking: str = "enabled"
    model_stage_2_thinking: str = "disabled"
    model_stage_3_thinking: str = "enabled"
    model_stage_4_thinking: str = "disabled"
    # DeepSeek V4 thinking mode 推理强度：high / max。仅在 thinking=enabled 时传递。
    deepseek_reasoning_effort: str = "high"

    # 搜索
    tavily_api_key: str

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ai_workflow"
    postgres_user: str = "postgres"
    postgres_password: str

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    # 应用
    app_env: str = "development"
    log_level: str = "INFO"
    session_ttl_hours: int = 72
    api_base: str = "http://localhost:8000"
    # json_first: 优先要求并解析 JSON；markdown_legacy: 保持旧版 Markdown 输出
    stage_output_mode: str = "json_first"
    # 当前生产路径固定为 single_step；langgraph_interrupt 仅保留为未来适配开关。
    workflow_execution_mode: WorkflowExecutionMode = WorkflowExecutionMode.SINGLE_STEP

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:"
            f"{self.postgres_password}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_dsn_sync(self) -> str:
        """LangGraph checkpointer 使用同步 DSN"""
        return (
            f"postgresql://{self.postgres_user}:"
            f"{self.postgres_password}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


# 全局单例
settings = Settings()
