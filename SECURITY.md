# 安全策略

## 报告漏洞

我们高度重视本项目安全问题。如发现漏洞，请通过以下**私有**渠道报告，勿在公开 Issue 中提交漏洞细节：

- **唯一渠道**：GitHub Security Advisories（仓库 Security 标签页 → Report a vulnerability）。该渠道端到端私有，支持协作修复与 CVE 申请。
- 本项目不提供邮箱报告渠道；如无法使用 GitHub 私密报告，可开一个**不含漏洞细节**的公开 Issue 请求维护者联系。

## 支持的版本范围

| 版本 | 是否支持 |
|---|---|
| 最新 minor（当前 v1.3.x） | ✅ |
| 更早版本 | ❌（请升级到最新版） |

## 响应承诺

- 收到报告后 **7 个自然日内**确认接收。
- 评估期间保持与报告者沟通，修复后发布安全公告与致谢（如报告者同意）。

## 不在范围内

- 通过 DeepSeek / Tavily 等第三方 API 触发的问题，请直报对应厂商。
- 本项目在 `LLM_MODE=mock` 演示模式下的非生产路径问题。
- 已在最新版本修复且已发布的问题。

## 应急响应

发生或疑似发生数据泄露事件时，按 [docs/compliance/incident-response.md](docs/compliance/incident-response.md) 的 checklist 处置。
