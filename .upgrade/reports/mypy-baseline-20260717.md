# mypy 基线报告（Wave B Task 7）

- 日期：2026-07-17；mypy 版本：mypy 2.3.0 (compiled: yes)
- 宽松档基线：108 errors / 27 files / 153 checked（正式首跑实际值：108 errors / 27 files / 153 checked）
- 按包：storage 46（postgres.py 44）· core 29 · stages 15 · graph 13 · tools 3 · api 2 · auth 0
- 按 code（top）：arg-type 33 · call-overload 24 · assignment 20 · unused-ignore 12 · attr-defined 9
- 近 strict 干跑（core/gates+graph）：25 errors / 9 files（no-untyped-def 10 + 真类型问题 15）
- 原始输出：`.upgrade/tmp/mypy-dryrun-lenient-20260717.txt` / `.upgrade/tmp/mypy-dryrun-strict-gates-graph-20260717.txt`

## 欠账登记（豁免类 override，随修复任务追加）

（B2–B5 中若登记临时豁免，逐条列在此处：module / disable_error_code / 原因 / 清偿条件）
