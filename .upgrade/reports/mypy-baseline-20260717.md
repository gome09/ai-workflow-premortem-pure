# mypy 基线报告（Wave B（父计划 Task 7–8））

- 日期：2026-07-17；mypy 版本：mypy 2.3.0 (compiled: yes)
- 宽松档基线：108 errors / 27 files / 153 checked（干跑与正式首跑一致）
- 按包：storage 46（postgres.py 44）· core 29 · stages 15 · graph 13 · tools 3 · api 2 · auth 0
- 按 code（top）：arg-type 33 · call-overload 24 · assignment 20 · unused-ignore 12 · attr-defined 9
- 近 strict 干跑（core/gates+graph）：25 errors / 9 files（no-untyped-def 10 + 真类型问题 15）
- 原始输出：`.upgrade/tmp/mypy-dryrun-lenient-20260717.txt` / `.upgrade/tmp/mypy-dryrun-strict-gates-graph-20260717.txt`（gitignored，仅本地留存；错误分布摘要见上两行）

## 欠账登记（豁免类 override，随修复任务追加）

（B2–B5 中若登记临时豁免，逐条列在此处：module / disable_error_code / 原因 / 清偿条件）

## 终态（Wave B 完成，2026-07-17）

- 宽松档 + core.gates/graph 近 strict：`Success: no issues found in 153 source files`
- 修复分片：storage 46→0（57aec07，postgres 行类型根因修复，DictConnection 别名，零豁免零 ignore）/ core+stages 44→0（6a1fe93，含一处真实 bug：create_redteam_dataset/create_dataset_from_failed_traces 的不存在 note= 关键字）/ graph+tools+api 18→0（cbc1193，含 SourceType 单一定义化）/ 近 strict 13→0（d8ba8b4 + 0f64dd8）
- 防漂移钉子：mypy>=1.14,<3（基线 2.3.0 测得）；langgraph>=1.1,<2（add_node overload ignore 依赖 1.1.10 行为，旧版会触发 unused-ignore）
- CI：`Type check (non-blocking)` 已接入 ci.yml，观察一轮后移除 continue-on-error 转强制（转正评估归 Wave E Task 16）
- 遗留欠账：无 mypy 豁免类 override。跟进型债务（非豁免）：`get_stage_prompts`（stages/prompts.py）返回 `dict[str, str | dict[int, str]]` 导致 4 处 `cast(str, ...)`（stages/stage_1..4），TypedDict 化可一并消除；`core/stage_advancement_contract.py` 的 `operation_contract_for` 返回 `dict[str, object]` 同型（core/stage_resolution_service.py:164 一处 cast）。均为可选重构，不阻塞。
