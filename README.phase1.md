# AI Agent Framework — Phase 1

本项目依据《Secure Hierarchical Multi-Agent Runtime Framework｜Work 项目执行蓝图》建立 **Phase 1：核心契约与状态规则**。它尚不是蓝图 Definition of Done 意义上的 V0.1 完整运行时。当前交付包括七个版本化 Schema、JSON Schema 导出、可信权限入口、任务与运行状态转换、静态 Task DAG 验证，以及对应自动测试。

## 本地运行

需要 Python 3.11 或更高版本。蓝图目标为 Python 3.12+；当前构建机仅有 3.11，差异和后续验证见 [ADR-001](docs/adr/001-phase1-baseline.md)。PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install wheel==0.45.1
.venv\Scripts\python.exe -m pip install --no-build-isolation -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m agent_runtime validate --contract examples\contract.json --plan examples\plan.json --manifests examples\manifests.json --environment examples\environment.json
.venv\Scripts\python.exe -m agent_runtime export-schemas --output schemas
```

`validate` 输出 DAG 顺序、可并行层、每个 Task 的有效工具权限和固定的 Agent Manifest 版本；无效计划返回非零退出码。七份已导出的 JSON Schema 在 [schemas](schemas) 目录。`examples/request.json` 是不可信用户请求格式，**没有权限字段**；`examples/contract.json` 是经可信入口授予权限后的合同示例。Phase 2 的 API 必须调用 `build_contract` 构造合同，不能接受用户自行声明的 `permissions`。

## 当前实现边界

- `TaskContract`、`Task`、`AgentManifest`、`RunState`、`ActionProposal`、`ResultEnvelope`、`Event` 均为 Pydantic v2 严格模型，`schema_version=1`，禁止未知字段。
- 任务状态转换需要匹配预期状态和版本；`READY` 需要所有依赖为 `SUCCESS`。只有 `commit_verified_success` 接受 Verifier PASS，并共同返回 Task 与 RunState 的新快照。数据库事务将在 Phase 2 实现。
- `PlanValidator` 拒绝环、悬挂或跨运行依赖、未注册 Agent、能力或工具越权、风险超限、未映射验收标准、超预算深度，以及同一工作区的并行写入冲突。示例计划为 `T1 → {T2,T3} → T4`。
- 本阶段只验证静态计划，尚不执行 Agent、调用模型、运行补丁、启动 API 或连接 PostgreSQL/Redis/MinIO。蓝图第 12 节规定这些能力按后续 Phase 引入；完整差异见 [Phase 1 验收与差异](docs/phase1-report.md)。

核心规则与字段见 [契约说明](docs/contracts.md)。该项目目录独立于此前的 `shmar` 演示版；此前演示版可作运行链路参考，其字段与安全隔离并不满足此蓝图的 V0.1 验收标准。

[实施任务清单](docs/tasks.md)记录当前验收与下一阶段的阻塞项。
