# core/config.py
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.execution_mode import WorkflowExecutionMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        secrets_dir="/run/secrets",
        # `.env` 由 compose、`make demo-*` 与 CI 多服务共享，除后端字段外还包含
        # 前端专用键（DEMO_USER_*）与容器键（SQLITE_PATH）。未知键必须忽略，
        # 否则 `cp .env.demo .env` 会在导入时触发 extra_forbidden。
        extra="ignore",
    )

    # LLM
    deepseek_api_key: str = ""
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
    model_stage_1_thinking: Literal["enabled", "disabled", "default"] = "enabled"
    model_stage_2_thinking: Literal["enabled", "disabled", "default"] = "disabled"
    model_stage_3_thinking: Literal["enabled", "disabled", "default"] = "enabled"
    model_stage_4_thinking: Literal["enabled", "disabled", "default"] = "disabled"
    # DeepSeek V4 thinking mode 推理强度：high / max。仅在 thinking=enabled 时传递。
    deepseek_reasoning_effort: Literal["high", "max"] = "high"

    # 真实模型调用的显式超时与 SDK 重试上限。此前依赖 SDK 默认值，
    # 挂起请求会长期占用线程且重试次数不可验收。
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 1

    # 搜索
    tavily_api_key: str = ""

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ai_workflow"
    postgres_user: str = "postgres"
    postgres_password: str = ""
    # Connection pool (psycopg_pool); the pool is created lazily on first query.
    # max_size 默认对齐 FastAPI 同步端点的线程并发；pool timeout 防止请求在
    # 池排队时无上限等待（psycopg_pool 默认 30s，过长会拖垮前端超时）。
    db_pool_min_size: int = 2
    db_pool_max_size: int = 20
    db_pool_timeout_seconds: float = 5.0
    # Per-statement server-side timeout; 0 disables the timeout.
    db_statement_timeout_ms: int = 5000

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    # 应用
    app_env: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    session_ttl_hours: int = 72
    api_base: str = "http://localhost:8000"
    # json_first: 优先要求并解析 JSON；markdown_legacy: 保持旧版 Markdown 输出
    stage_output_mode: Literal["json_first", "markdown_legacy"] = "json_first"
    # Domain profile: "default" uses existing general-purpose prompts;
    # "university_ai" loads university AI application risk assessment prompts;
    # "medical_ai" loads clinical AI governance prompts (HIPAA/FDA SaMD/ISO 14971).
    domain_profile: str = "default"
    # LLM mode: "real" uses live DeepSeek + Tavily; "mock" returns fixture JSON (no network).
    llm_mode: Literal["real", "mock"] = "real"
    # Storage backend: "postgres" uses PostgreSQL; "sqlite" for lightweight local use (E1).
    storage_backend: Literal["postgres", "sqlite"] = "postgres"
    # single_step remains the stable default; langgraph_interrupt is an explicit opt-in.
    workflow_execution_mode: WorkflowExecutionMode = WorkflowExecutionMode.SINGLE_STEP
    # Durable interrupt resume outbox: periodic retry after startup reconciliation.
    # The manager reclaims abandoned "processing" rows after 5 minutes, so keep the
    # default interval above that threshold for long-running resumes.
    interrupt_resume_retry_interval_seconds: int = 600
    interrupt_resume_retry_batch_size: int = 100
    # LangGraph checkpoint backend. Memory is non-persistent and limited to local SQLite/dev use.
    checkpoint_backend: Literal["postgres", "memory"] = "postgres"
    # Independent Fernet key for encrypting checkpoint payloads (do not reuse DATA_ENCRYPTION_KEY).
    checkpoint_encryption_key: str = ""

    # Auth
    jwt_secret: str = ""
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7
    frontend_service_token: str = ""
    # 前端演示自动认证开关。后端仅在 production 启动校验时读取，
    # 用于阻止演示凭据登录路径随生产部署启用。
    demo_auto_auth: bool = False

    # Data encryption (T1.3) — Fernet key, base64-encoded 32 bytes
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    data_encryption_key: str = ""

    # PII masking before sending to LLM (T1.4)
    # Default false: 先让检测跑起来积累误报数据，再决定是否默认开启。
    pii_mask_before_llm: bool = False

    # Data lifecycle (T1.6) — retention in days
    audit_retention_days: int = 183  # 6 months, aligns with 等保
    session_retention_days: int = 0  # 0 = forever

    # Retention executor: enabled by default, but dry-run unless explicitly disabled.
    retention_enabled: bool = True
    retention_dry_run: bool = True
    retention_sweep_interval_seconds: int = 86_400
    retention_batch_size: int = 1_000

    # LLM10 Unbounded Consumption thresholds (T2.1)
    # 单会话累计调用次数 / token 估算告警阈值；命中产出 medium finding（不阻断）
    llm_call_count_threshold: int = 200
    llm_token_estimate_threshold: int = 500_000

    # T3.3 门禁规则禁用治理：显式禁用规则需配置；安全底线规则不可禁用（配置也忽略+告警）
    gate_rules_disabled: str = ""  # 逗号分隔 rule_id

    # Milestone 2 风险驱动 Stage 3 coverage policy。
    # LOW/MEDIUM 才允许预算型抽样；HIGH/CRITICAL 的高风险节点必须全覆盖。
    stage3_low_risk_sample_nodes: int = 3
    stage3_medium_risk_sample_nodes: int = 5
    stage3_high_risk_sample_nodes: int = 5
    stage3_min_coverage_ratio: float = 0.2
    stage3_min_cases_per_high_risk_node: int = 1

    # 真实目标系统测试（target_http）。空 allowlist = 拒绝所有外部目标调用。
    target_system_allowed_hosts: str = ""
    target_system_token: str = ""
    target_system_timeout_seconds: float = 10.0
    target_system_max_response_chars: int = 4000

    # T3.6 LLM Judge（spec governance-platform §5）：LLM 仅建议判分，不终裁。
    # eval_llm_judge=on 时对规则层 needs_review 的 run 生成结构化建议
    eval_llm_judge: bool = False
    # LOW/MEDIUM 会话允许采纳 LLM 建议为终值（HIGH/CRITICAL 永远待人工）；
    # 开启属于显式治理决策（与 gate_rules_disabled 同级）
    eval_llm_judge_autofinal: bool = False

    # CORS
    cors_allow_origins: str = "https://localhost"

    # Uvicorn (runtime-only, read by Dockerfile CMD substitution)
    uvicorn_workers: int = 2

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        if not self.jwt_secret or len(self.jwt_secret) < 32:
            raise ValueError(
                "JWT_SECRET must be set and at least 32 characters. "
                "Generate one with: openssl rand -hex 32"
            )
        if self.llm_mode == "real":
            if not self.deepseek_api_key:
                raise ValueError("DEEPSEEK_API_KEY must be set when LLM_MODE=real")
            if not self.tavily_api_key:
                raise ValueError("TAVILY_API_KEY must be set when LLM_MODE=real")
        if self.storage_backend != "sqlite" and not self.postgres_password:
            raise ValueError("POSTGRES_PASSWORD must be set when STORAGE_BACKEND is not sqlite")
        if self.db_pool_min_size < 0:
            raise ValueError("DB_POOL_MIN_SIZE must be >= 0")
        if self.db_pool_max_size < 1 or self.db_pool_max_size < self.db_pool_min_size:
            raise ValueError("DB_POOL_MAX_SIZE must be >= 1 and >= DB_POOL_MIN_SIZE")
        if self.db_pool_timeout_seconds < 0:
            raise ValueError("DB_POOL_TIMEOUT_SECONDS must be >= 0")
        if self.db_statement_timeout_ms < 0:
            raise ValueError("DB_STATEMENT_TIMEOUT_MS must be >= 0")
        if self.retention_sweep_interval_seconds < 0:
            raise ValueError("RETENTION_SWEEP_INTERVAL_SECONDS must be >= 0")
        if self.retention_batch_size < 1:
            raise ValueError("RETENTION_BATCH_SIZE must be >= 1")
        if self.interrupt_resume_retry_interval_seconds < 0:
            raise ValueError("INTERRUPT_RESUME_RETRY_INTERVAL_SECONDS must be >= 0")
        if self.interrupt_resume_retry_batch_size < 1:
            raise ValueError("INTERRUPT_RESUME_RETRY_BATCH_SIZE must be >= 1")
        if self.session_retention_days < 0:
            raise ValueError("SESSION_RETENTION_DAYS must be >= 0")
        if self.audit_retention_days < 0:
            raise ValueError("AUDIT_RETENTION_DAYS must be >= 0")
        if self.stage3_low_risk_sample_nodes < 0:
            raise ValueError("STAGE3_LOW_RISK_SAMPLE_NODES must be >= 0")
        if self.stage3_medium_risk_sample_nodes < 0:
            raise ValueError("STAGE3_MEDIUM_RISK_SAMPLE_NODES must be >= 0")
        if self.stage3_high_risk_sample_nodes < 0:
            raise ValueError("STAGE3_HIGH_RISK_SAMPLE_NODES must be >= 0")
        if not 0.0 <= self.stage3_min_coverage_ratio <= 1.0:
            raise ValueError("STAGE3_MIN_COVERAGE_RATIO must be between 0 and 1")
        if self.stage3_min_cases_per_high_risk_node < 1:
            raise ValueError("STAGE3_MIN_CASES_PER_HIGH_RISK_NODE must be >= 1")
        if self.llm_timeout_seconds <= 0:
            raise ValueError("LLM_TIMEOUT_SECONDS must be > 0")
        if self.llm_max_retries < 0:
            raise ValueError("LLM_MAX_RETRIES must be >= 0")
        if self.target_system_timeout_seconds <= 0:
            raise ValueError("TARGET_SYSTEM_TIMEOUT_SECONDS must be > 0")
        if self.target_system_max_response_chars < 1:
            raise ValueError("TARGET_SYSTEM_MAX_RESPONSE_CHARS must be >= 1")

        if self.app_env.lower() == "production":
            # 生产启动 fail-closed：拒绝演示/开发配置与缺失的字段加密 key。
            if self.llm_mode != "real":
                raise ValueError("LLM_MODE must be real in production")
            if self.storage_backend != "postgres":
                raise ValueError("STORAGE_BACKEND must be postgres in production")
            if self.demo_auto_auth:
                raise ValueError("DEMO_AUTO_AUTH must be false in production")
            if not self.data_encryption_key:
                raise ValueError("DATA_ENCRYPTION_KEY must be set in production")
            from cryptography.fernet import Fernet

            try:
                Fernet(self.data_encryption_key)
            except Exception as exc:  # noqa: BLE001 - startup validation
                raise ValueError("DATA_ENCRYPTION_KEY must be a valid Fernet key") from exc

        execution_mode = WorkflowExecutionMode.normalize(self.workflow_execution_mode)
        if execution_mode == WorkflowExecutionMode.LANGGRAPH_INTERRUPT:
            if self.uvicorn_workers != 1:
                raise ValueError(
                    "UVICORN_WORKERS must be 1 when WORKFLOW_EXECUTION_MODE=langgraph_interrupt"
                )
            if self.app_env.lower() == "production" and self.checkpoint_backend != "postgres":
                raise ValueError(
                    "CHECKPOINT_BACKEND must be postgres for langgraph_interrupt in production"
                )
            if self.storage_backend == "postgres" and self.checkpoint_backend != "postgres":
                raise ValueError(
                    "CHECKPOINT_BACKEND must be postgres when langgraph_interrupt uses "
                    "STORAGE_BACKEND=postgres"
                )
            if self.storage_backend == "sqlite" and self.checkpoint_backend != "memory":
                raise ValueError(
                    "CHECKPOINT_BACKEND must be memory when langgraph_interrupt uses "
                    "STORAGE_BACKEND=sqlite"
                )
            if self.checkpoint_backend == "postgres" and not self.checkpoint_encryption_key:
                raise ValueError(
                    "CHECKPOINT_ENCRYPTION_KEY must be set when langgraph_interrupt uses "
                    "CHECKPOINT_BACKEND=postgres"
                )
            if (
                self.checkpoint_encryption_key
                and self.data_encryption_key
                and self.checkpoint_encryption_key == self.data_encryption_key
            ):
                raise ValueError("CHECKPOINT_ENCRYPTION_KEY must not reuse DATA_ENCRYPTION_KEY")
        return self

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

    @property
    def gate_rules_disabled_set(self) -> set[str]:
        return {s.strip() for s in self.gate_rules_disabled.split(",") if s.strip()}


# 全局单例
settings = Settings()
