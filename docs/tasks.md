# 实施任务清单

本清单对应用户提供蓝图第 12 节的开发顺序，不把 Phase 1～7 解释成七个独立平台。

## Phase 1：已完成

- [x] 创建可安装的 Python 项目骨架、README 和 ADR-001。
- [x] 定义七个版本 1 的核心 Schema，并导出 JSON Schema。
- [x] 实现可信权限入口、状态转换、版本检查与成功提交规则。
- [x] 实现 DAG、Manifest、工具权限、风险和写入冲突校验。
- [x] 提供 `T1 → {T2,T3} → T4` 示例计划及 17 个自动测试。
- [x] 记录 Python 3.11 环境差异和蓝图尚未满足的项目。

## Phase 2：下一步

- [ ] 用可信 API 入口构造合同，提供 `POST /runs` 和查询接口。
- [ ] PostgreSQL 迁移与 Repository：Run、Task、Event 的条件更新和原子成功提交。
- [ ] 实现单 Task 的 Scheduler、Worker、ResearchAgent、ResultEnvelope 和 Verifier。
- [ ] 运行只读 Demo，验证 API 重启后状态与事件仍可查询。
- [ ] 在 Python 3.12 环境运行测试，再决定上调最低版本。

## Phase 3 之后

按蓝图依次增加 DAG 执行与并发、恢复与 Outbox/队列、Policy/Tool Gateway/Docker Sandbox、最小 Context/Experience，以及评测和 Compose。Phase 5 的隔离执行验收前，CodingAgent 只能形成补丁草稿，不运行生成代码或写宿主仓库。

## 可视化平台与跨界面一致性

详细架构门槛见 [终端与 Web 协同治理基线](terminal-web-sync-governance.md)。

- [ ] P0：统一草案格式、受信合同与外部请求的导入规则；让 CLI 和 Web 对同一计划得到一致校验结果。
- [ ] P0：为校验错误提供稳定错误码、字段路径和相关 Task ID，并定义目录与预检 API。
- [ ] Phase 2：持久 Run 命令共用 API/服务层；状态与事件同事务提交，支持版本冲突和幂等键；Phase 4 接入队列时将 Outbox 纳入同一事务。
- [ ] 运行详情上线前：页面快照带事件游标；SSE 可回放、去重和断线重同步。
- [ ] Phase 4–5：验证 Redis 丢失、Worker 重启、工作区哈希不一致和外部副作用不确定时的恢复与审计。
