# 标准动态跟踪记录

> 注：本文件现位于 `.upgrade/reports/`（2026-07-17 Mode 3 自 gitignored 的 `.upgrade/logs/`
> 移入，纳入版本控制）。2026-07-17 依据
> `docs/plan/phase-2-design.md` T2.6 的初始记录规格重建（原始文件在本地工作区丢失），
> 内容为 2026-07-14 基线核对记录原文。

## 2026-07-14（Phase 2 启动时基线核对）

### 《网络安全技术 人工智能技术涉及未成年人应用安全指南》
- 状态：征求意见中（截止 2026-08-16）
- 影响：university_mental_health 场景的未成年人数据处理逻辑
- 行动：定稿后核对，暂无变化

### TC260 分行业指导性技术文件（金融/广电/卫生健康/政务）
- 状态：2026-07 起密集征集参编单位
- 影响：可能新增 stages/domain_profiles/
- 行动：定稿后评估，暂无变化

### NIST AI RMF 修订版 / AI Agent Interoperability Profile
- 状态：AI RMF 1.0 修订中（无版本号/日期）；Agent Interoperability Profile 预告 2026 Q4
- 影响：nist_ai_600_1.py 条款号可能变更
- 行动：发布后更新 T2.2 条款号，暂无变化

### OWASP ASI 2026 正式定义
- 状态：已发布（genai.owasp.org）
- 影响：T2.3 映射初稿需逐条复核
- 行动：T2.3 落地时由 subagent 复核
