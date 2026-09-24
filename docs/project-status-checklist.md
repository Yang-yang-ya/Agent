# 项目功能与内容清单

> 核对日期：2026-09-24。依据当前工作区的代码、测试、示例与文档。`[x]` 表示已有可运行实现或已形成文档；`[ ]` 表示尚无对应可运行实现。**数据模型存在，不等于服务或 Agent 已运行。**

## 当前结论

项目处于 **Phase 1 已实现、Phase 2 尚未启动实现** 的阶段。现在可以在终端安装项目、导出 Schema、校验一份静态 Task DAG，并运行 17 项自动测试。现在还不能启动真实 Agent Run、连接 Web 工作台或实时查看任务执行。平台需求和终端/Web 协同方案已有初稿，属于规划内容。

## A. 已实现：可运行代码与可验证内容

| 状态 | 内容 | 实现或证据 | 当前边界 |
| --- | --- | --- | --- |
| [x] | Python 项目骨架与可编辑安装 | `pyproject.toml`、`src/agent_runtime/` | Python 要求暂为 3.11+；尚无服务部署配置。 |
| [x] | 七个版本 1 的严格数据模型 | `src/agent_runtime/core/schemas.py`、`schemas/*.schema.json` | 定义 `TaskContract`、`Task`、`AgentManifest`、`RunState`、`ActionProposal`、`ResultEnvelope`、`Event`；尚无数据库表或 API。 |
| [x] | JSON Schema 导出 | `python -m agent_runtime export-schemas --output schemas` | 输出上述七份 Schema；模型变更后需重新导出。 |
| [x] | 不可信请求与可信权限入口 | `ContractRequest`、`build_contract`，见 `core/planning.py` | 外部请求不能自授权限；真正的认证和授权 API 尚未实现。 |
| [x] | Task/Run 纯状态转换与版本检查 | `core/state.py` | 检查预期状态和 `state_version`、依赖完成、尝试次数；转换结果尚未持久化。 |
| [x] | Verifier PASS 才可形成任务成功快照 | `commit_verified_success`，见 `core/state.py` | 只实现提交前规则；Verifier 服务和数据库原子事务尚未实现。 |
| [x] | 静态 Task DAG 与权限校验 | `PlanValidator`，见 `core/planning.py` | 覆盖环、缺失/跨 Run 依赖、Agent/能力/工具不匹配、预算/风险上限、并行写入冲突；不执行计划。 |
| [x] | CLI 静态校验 | `python -m agent_runtime validate ...`，见 `cli.py` | 返回任务顺序、并行层、有效工具和 Manifest 版本；不是 Run 启动命令。 |
| [x] | 五份示例输入及七份导出 Schema | `examples/`、`schemas/` | 示例合同模拟可信入口的结果，不能直接作为外部授权请求。 |
| [x] | 自动测试 | `tests/` | 本次核对运行 `17 passed`；仅覆盖 Phase 1 的模型、状态规则与静态计划。 |

## B. 已形成文档：可指导开发，但不代表功能上线

| 状态 | 内容 | 文件 | 用途 |
| --- | --- | --- | --- |
| [x] | Runtime 总体目标、七阶段路线和 V0.1 完成标准 | `AI-Agent-Framework-Work-Orchestration.md` | 总体执行蓝图。 |
| [x] | Phase 1 运行说明、合同规则、差异与任务清单 | `README.phase1.md`、`docs/contracts.md`、`docs/phase1-report.md`、`docs/tasks.md` | 解释当前实现与后续阻塞项。 |
| [x] | 可视化平台需求初稿 | `docs/visual-agent-platform-requirements.md` | 定义页面、用户流程、P0–P3 交付范围与验收方向。 |
| [x] | 终端与 Web 协同治理基线 | `docs/terminal-web-sync-governance.md` | 定义权威数据、连接拓扑、断线回放、并发、幂等和项目门槛。 |

上述两份平台文档是**设计约束**；其中的接口路径、SSE 和页面均未在代码中实现。前端框架、页面视觉稿、具体 API 请求/响应和部署参数还需定稿。

## C. 尚未实现：下一步最小闭环

### C1. 可视化平台 P0：静态计划工作台

- [ ] Web 前端工程、目标表单、DAG 画布、节点详情与校验面板。
- [ ] 草案 JSON 格式、导入/导出、受信合同与外部请求的明确区分。
- [ ] Agent/能力/工具/验收条件目录接口 `GET /catalog`。
- [ ] 计划校验接口 `POST /plans/validate`，复用现有 `PlanValidator`。
- [ ] 稳定错误码、字段路径和相关 Task ID，供画布定位错误；目前只有异常文字。
- [ ] CLI 与 Web 对同一示例计划输出等价结果的端到端验收。

P0 完成后，Web 可以**编辑和校验计划**，仍不能展示真实运行。

### C2. Runtime Phase 2：单 Agent 可运行纵切

- [ ] FastAPI 可信入口：`POST /runs`、Run/Task/Event 查询与取消 API。
- [ ] PostgreSQL 表、迁移、Repository、状态与事件原子提交、版本冲突和命令幂等。
- [ ] 最小 Scheduler、Worker、Agent Registry、ResearchAgent 只读执行。
- [ ] Model Gateway 的确定性替身、真实 `ResultEnvelope` 产出和 Verifier 检查。
- [ ] API 重启后仍能查询 Run、Task、事件；失败不会被误报成功。
- [ ] Python 3.12 环境的测试验证，并据结果决定是否上调最低版本。

Phase 2 完成后才可声称“创建一个真实 Run 并查询结果”。

## D. 尚在规划：后续能力与阶段依赖

| 阶段 | 规划内容 | 必须有的验收结果 |
| --- | --- | --- |
| Runtime Phase 3 / 平台 P2 | MainAgent 计划、Research/RAG/Coding 多 Agent、DAG 调度与结果聚合；Web 实时任务图 | `T1 → {T2,T3} → T4` 的并发和依赖正确；失败不推进下游；结果引用已验证证据。 |
| 平台 P1–P2 的实时连接 | 一致的 Run 页面快照、事件游标、SSE 回放、断线重连与去重 | 刷新/断网后页面追上数据库；CLI 与 Web 不产生两套 Run 状态。 |
| Runtime Phase 4 / 平台 P3 | Redis 投递、Outbox、Worker lease、Checkpoint、MinIO Artifact/Snapshot、DLQ、取消与恢复 | Worker 宕机、重复投递、Redis 清空和对象缺失的故障演练通过。 |
| Runtime Phase 5 / 平台 P3 | Policy、Tool Gateway、Docker Sandbox、审批和工具审计 | 越权、路径逃逸和禁网测试被拒绝；CodingAgent 仅在隔离工作区执行。 |
| Runtime Phase 6 | Context 选择、经验证 Experience Memory、受限重规划 | 未验证经验不进入可信记忆；重规划保留已成功任务和旧轨迹。 |
| Runtime Phase 7 | 评测、CI/CD、Docker Compose、部署与恢复手册 | 新环境可复现 Demo、故障演练、审计链及版本追踪。 |

### 尚需产品或技术决策

- [ ] 定稿 P0 主要交互：用户手工编排优先，还是审阅 MainAgent 生成的草案优先。
- [ ] 选择并记录前端技术栈、画布组件、样式方案与浏览器支持范围；此前讨论的 Web 优先架构是建议，仓库尚无前端工程。
- [ ] 定稿草案存储方式、认证方式、部署域名/端口、事件保留期限与备份策略。
- [ ] 定稿 API 的请求/响应、错误模型、分页、游标和版本兼容规则。
- [ ] 用首个可运行版本的实测结果固定性能、恢复时间和可用性验收阈值。

## E. 阶段完成判据

- **现在**：只能称为“可验证静态计划的核心契约原型”。
- **P0 完成**：可称为“可视化计划编辑与校验工作台”，不能称为 Agent 运行平台。
- **Phase 2 完成**：可称为“单 Agent 可运行原型”，前提是持久状态、事件和验证链可查。
- **V0.1 完成**：必须逐条满足总体蓝图第 19 节的 Definition of Done，尤其是多 Agent Demo、可恢复执行、安全工具边界及审计。

每次更新本清单时，以代码、自动测试或可复现演练为准；需求文档里的“应支持”不自动改成 `[x]`。
