# Phase 1 契约、状态与计划规则

七个顶层 Schema 在 `src/agent_runtime/core/schemas.py` 中定义，均固定 `schema_version=1`、拒绝未知字段，并可导出 JSON Schema。时间字段必须是带 UTC 时区的 ISO 8601 时间。`Identifier` 为最长 64 位的字母、数字、下划线或连字符组成的稳定 ID。JSON Schema 文件由代码生成，修改模型后运行 `python -m agent_runtime export-schemas --output schemas` 并提交生成结果。

| Schema | 关键字段与约束 |
| --- | --- |
| TaskContract | `run_id, goal, constraints, acceptance_criteria, permissions, context_refs, budget, created_at`；权限只能由可信 `build_contract` 入口注入。 |
| Task | `task_id, run_id, capability, depends_on, status, priority, attempt, max_attempts, agent_id, input_refs, output_refs, idempotency_scope, created_at`；增加 `allowed_tools, workspace_ref, state_version` 以支持明确的最小授权、写入冲突检测和条件状态更新。 |
| AgentManifest | 固定 `agent_id, version, capabilities, allowed_tools, forbidden_tools, model_profile, risk_ceiling, timeout_seconds, max_steps`。同一工具不得同时允许和禁止。 |
| RunState | `status, plan_version, task_ids, completed_task_ids, budget_used, checkpoint_ref, final_result_ref, updated_at`；增加 `last_consistent_checkpoint, state_version`。完成态必须有全部已完成 Task 和最终结果引用。 |
| ActionProposal | `action_id, run_id, task_id, agent_id, tool, operation, arguments, reason, risk_level, idempotency_key, created_at`；参数限 64 KiB、必须是有限 JSON；L2/L3 必须提供幂等键。 |
| ResultEnvelope | `status, summary, data, artifacts, evidence, verifier, error, metrics, completed_at`；`SUCCESS` 必须伴随 Verifier PASS；Artifact 有 URI、SHA-256、所有者和版本。 |
| Event | `event_id, run_id, task_id, sequence, type, actor, trace_id, payload, occurred_at`；序号为正，Payload 限 8 KiB，拒绝明显包含密钥字段的结构。Phase 2 才提供 append-only 存储和事件链。 |

`Budget` 含蓝图必需的 `max_steps, max_llm_calls, max_tool_calls, timeout_seconds`，另加 `max_tasks, max_depth, max_concurrency` 作为 Phase 1 计划上限。`BudgetUsed` 单独记录消耗。`acceptance_criteria` 使用已注册的机器可检验 ID：`root_cause_with_evidence`、`pytest_login_passes`、`patch_reproducible`。其实际业务 Verifier 将在后续 Phase 实现；当前校验只确认映射存在。

入口信任边界：`ContractRequest` 没有 `permissions` 字段且禁止额外字段。可信 API 层使用 `build_contract(request, run_id=..., trusted_permissions=..., created_at=...)` 授予权限。`examples/contract.json` 模拟已构造的内部合同，不能作为直接接受外部权限声明的 API 实现。

`PlanValidator` 的有效工具集合为 `Task.allowed_tools ∩ AgentManifest.allowed_tools`，还需排除 Manifest 禁用工具，并满足 `TaskContract.permissions ∩ environment_permissions` 对该工具的全部要求。未知工具默认拒绝。Phase 1 策略表只含受控只读工具与 Sandbox L1 工具；L2/L3 不进入当前计划。版本固定的 Manifest 与有效工具会写入校验报告。

Task 的合法状态边参见 `TASK_TRANSITIONS`；Run 的合法状态边参见 `RUN_TRANSITIONS`。`transition_task` 和 `transition_run` 必须给出 `expected_status` 与 `expected_version`。`READY` 另检查全部依赖成功。`Task.SUCCESS` 只能通过 `commit_verified_success`，它要求候选结果身份一致、Verifier PASS、非重复完成和 Checkpoint 引用。该函数返回两个应在同一数据库事务持久化的新快照；Phase 2 将补上事务、条件更新和事件。`Run.COMPLETED` 另要求全部 Task 成功、最终结果引用和验收检查通过。终态没有离开路径。

版本策略：版本 1 的未知字段和版本 2 输入均拒绝。后续新增字段或状态含义时，先发布新的 Schema、迁移规则及兼容测试；不能悄悄改变版本 1 的解释。`AgentManifest.version` 为独立的语义版本，在计划校验结果中固定。
