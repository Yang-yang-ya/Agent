# Phase 1 验收与蓝图差异

来源：用户提供的 `AI-Agent-Framework-Work-Orchestration.md`，以其中第 4、6、7、12、13、19 节为 Phase 1 约束。文档里的“可直接提交给 Work 模式的首个执行请求”是示例指引；本项目按用户当前请求启动构建，并未将文档中的对话语句当成新的用户授权。

| Phase 1 验收项 | 证据 | 结果 |
| --- | --- | --- |
| 七个版本化 Schema 与 JSON Schema | `core/schemas.py`、`schemas/*.schema.json` | 已实现，版本 1，严格字段 |
| 状态、错误与非法转换 | `core/state.py`、`tests/test_state.py` | 已实现纯状态转换与版本检查 |
| DAG Validator 与最小权限 | `core/planning.py`、`tests/test_plan.py` | 已实现静态校验；示例显示 T2/T3 可并行 |
| 外部入口不可自授权限 | `ContractRequest`、`build_contract`、`tests/test_schemas.py` | 已实现并测试 |
| 本地安装、运行与测试 | `pyproject.toml`、README、CLI、pytest | 已验证 |

相对蓝图的明示差异：当前机器只有 Python 3.11，因此 `requires-python` 暂允许 3.11；采用 Pydantic 2.13.5 并使用与 3.12 兼容的语法。尚未在 3.12 环境运行测试。`Task` 比蓝图最小字段多出 `allowed_tools`、`workspace_ref` 和 `state_version`，使工具交集、并行写入冲突与条件状态更新可测试。验收条件采用可映射到 Verifier 的稳定 ID，而不是自然语言短句。具体决策见 ADR-001。

当前只完成 Phase 1。以下 V0.1 Definition of Done 条目仍未完成：POST /runs 和查询 API、实际 Scheduler/Worker 并发执行、PostgreSQL/Redis/MinIO、Outbox/lease/Checkpoint 事务、Docker Sandbox、登录事故 fixture 的真实补丁和 pytest、故障注入、DLQ、SSE、CI/Compose。此前 `shmar` 演示版使用 SQLite 与受限算术函数，仅能作为概念验证，不能充当这些条目的验收证据。

下一步应按蓝图 Phase 2 建立 ResearchAgent 单任务纵切：可信 API 构造合同，PostgreSQL 保存 Run/Task/Event，Verifier PASS 后在同一事务提交 SUCCESS，提供创建与查询接口，并验证重启后状态仍可查询。Phase 3 再执行当前静态 DAG。真实代码执行必须等 Phase 5 的 Policy、Gateway、Docker Sandbox 验收后才启用。
