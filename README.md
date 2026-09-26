# Agent
一个自主搭建的Agent框架，还在完善中

Phase 1 代码与运行说明：[README.phase1.md](README.phase1.md)

可视化 Agent 工作平台需求：[docs/visual-agent-platform-requirements.md](docs/visual-agent-platform-requirements.md)

终端与 Web 协同治理：[docs/terminal-web-sync-governance.md](docs/terminal-web-sync-governance.md)

当前功能与待办总览：[docs/project-status-checklist.md](docs/project-status-checklist.md)

## 可视化计划工作台（P0）

当前 Web 页面支持编辑任务图、导入/导出草案和调用服务端静态校验。它不会启动或执行 Agent。可行性与实施边界见 [ADR-002](docs/adr/002-p0-web-workbench-feasibility.md)。

首次安装及启动（PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install wheel==0.45.1
.\.venv\Scripts\python.exe -m pip install --no-build-isolation -e '.[dev]'
Set-Location web
pnpm install
pnpm build
Set-Location ..
.\.venv\Scripts\python.exe -m uvicorn agent_runtime.api.app:app --host 127.0.0.1 --port 8000
```

服务保持运行时，打开 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)；`/docs` 为 API 文档。修改前端后重新运行 `pnpm build` 并刷新页面。开发时可在第二个终端进入 `web` 运行 `pnpm dev`，打开 `http://127.0.0.1:5173/` 使用热更新；API 仍需在 8000 端口运行。当前工作台不需要 PostgreSQL、Redis 或 MinIO。
