import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow,
  useNodesState, type Connection, type Edge, type Node, type NodeProps, type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { Budget, Catalog, DraftTask, PlanDraft, ValidationIssue, ValidationResult } from './types'

type TaskData = { task: DraftTask; invalid: boolean; selected: boolean; level: number | null }
type TaskNode = Node<TaskData, 'task'>

const issueNames: Record<string, string> = {
  DAG_CYCLE: '存在循环依赖', INVALID_DEPENDENCY: '依赖无效', DUPLICATE_TASK_ID: '任务 ID 重复',
  CAPABILITY_MISMATCH: 'Agent 能力不匹配', TOOL_NOT_ALLOWED: '工具不可用',
  PERMISSION_DENIED: '预览权限不足', PARALLEL_WORKSPACE_CONFLICT: '并行工作区冲突',
  TASK_BUDGET_EXCEEDED: '任务超出预算', DAG_DEPTH_EXCEEDED: '计划深度超限',
  UNKNOWN_ACCEPTANCE_CRITERION: '验收条件未注册', SCHEMA_INVALID: '输入格式错误',
}

function TaskCard({ data }: NodeProps<TaskNode>) {
  const { task, invalid, selected, level } = data
  return <div className={`task-node ${selected ? 'selected' : ''} ${invalid ? 'invalid' : ''}`}>
    <Handle type="target" position={Position.Left} />
    <div className="node-top"><span className="node-id">{task.task_id}</span><span className="node-state">草案</span></div>
    <strong>{task.goal || '未命名任务'}</strong>
    <div className="node-capability">{task.capability || '选择能力'}</div>
    <div className="node-foot"><span>{task.agent_id || '未选择 Agent'}</span><span>{level ? `第 ${level} 层` : `${task.allowed_tools.length} 个工具`}</span></div>
    <Handle type="source" position={Position.Right} />
  </div>
}

const nodeTypes = { task: TaskCard }

function listText(values: string[]) { return values.join('\n') }
function lines(value: string) { return value.split(/\r?\n/).map(v => v.trim()).filter(Boolean) }

function layout(tasks: DraftTask[]) {
  const depth = new Map<string, number>()
  const visiting = new Set<string>()
  const byId = new Map(tasks.map(task => [task.task_id, task]))
  const getDepth = (id: string): number => {
    if (depth.has(id)) return depth.get(id)!
    if (visiting.has(id)) return 0
    visiting.add(id)
    const task = byId.get(id)
    const value = task ? Math.min(8, Math.max(0, ...task.depends_on.map(dep => getDepth(dep) + 1))) : 0
    visiting.delete(id)
    depth.set(id, value)
    return value
  }
  tasks.forEach(task => getDepth(task.task_id))
  const rows = new Map<number, number>()
  return new Map(tasks.map(task => {
    const column = depth.get(task.task_id) || 0
    const row = rows.get(column) || 0
    rows.set(column, row + 1)
    return [task.task_id, { x: column * 340 + 40, y: row * 190 + 70 }] as const
  }))
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return <label className="field"><span className="field-label">{label}</span>{children}{hint && <small>{hint}</small>}</label>
}

function App() {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [draft, setDraft] = useState<PlanDraft | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [result, setResult] = useState<ValidationResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [focusCanvas, setFocusCanvas] = useState(false)
  const [nodes, setNodes, onNodesChange] = useNodesState<TaskNode>([])
  const fileRef = useRef<HTMLInputElement>(null)
  const flowRef = useRef<ReactFlowInstance<TaskNode, Edge> | null>(null)

  useEffect(() => {
    const frame = requestAnimationFrame(() => { void flowRef.current?.fitView({ padding: 0.18, duration: 180 }) })
    return () => cancelAnimationFrame(frame)
  }, [focusCanvas])

  const loadExample = useCallback(async () => {
    setBusy(true)
    try {
      const [catalogResponse, exampleResponse] = await Promise.all([
        fetch('/api/catalog'), fetch('/api/plans/example'),
      ])
      if (!catalogResponse.ok || !exampleResponse.ok) throw new Error('API 未就绪，请先启动 Python 服务')
      const nextCatalog = await catalogResponse.json() as Catalog
      const nextDraft = await exampleResponse.json() as PlanDraft
      setCatalog(nextCatalog)
      setDraft(nextDraft)
      setSelectedId(nextDraft.tasks[0]?.task_id || null)
      setResult(null)
      setNotice('已载入登录异常分析示例。此页面只预览计划，不执行 Agent。')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '载入失败')
    } finally { setBusy(false) }
  }, [])

  useEffect(() => { void loadExample() }, [loadExample])

  const updateDraft = (updater: (current: PlanDraft) => PlanDraft) => {
    setDraft(current => current ? updater(current) : current)
    setResult(null)
    setNotice('草案已修改，请重新校验。')
  }
  const updateRequest = (patch: Partial<PlanDraft['request']>) =>
    updateDraft(current => ({ ...current, request: { ...current.request, ...patch } }))
  const updateBudget = (key: keyof Budget, value: number) =>
    updateDraft(current => ({ ...current, request: { ...current.request,
      budget: { ...current.request.budget, [key]: value } } }))
  const updateTask = (id: string, patch: Partial<DraftTask>) =>
    updateDraft(current => ({ ...current, tasks: current.tasks.map(task => task.task_id === id ? { ...task, ...patch } : task) }))

  const selectedTask = draft?.tasks.find(task => task.task_id === selectedId) || null
  const selectedAgent = catalog?.agents.find(agent => agent.agent_id === selectedTask?.agent_id)
  const issueIds = useMemo(() => new Set(result?.errors.flatMap(error => error.task_ids) || []), [result])
  const layerById = useMemo(() => new Map(result?.report?.parallel_levels.flatMap((ids, index) =>
    ids.map(id => [id, index + 1] as const)) || []), [result])

  useEffect(() => {
    if (!draft) { setNodes([]); return }
    setNodes(previous => {
      const old = new Map(previous.map(node => [node.id, node.position]))
      const initial = layout(draft.tasks)
      return draft.tasks.map((task): TaskNode => ({
        id: task.task_id, type: 'task', position: old.get(task.task_id) || initial.get(task.task_id) || { x: 0, y: 0 },
        data: { task, invalid: issueIds.has(task.task_id), selected: selectedId === task.task_id,
          level: layerById.get(task.task_id) || null },
      }))
    })
  }, [draft, issueIds, layerById, selectedId, setNodes])

  const edges = useMemo<Edge[]>(() => draft?.tasks.flatMap(task => task.depends_on.map(dep => ({
    id: `${dep}--${task.task_id}`, source: dep, target: task.task_id, type: 'smoothstep',
    markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: '#8495b7', strokeWidth: 2 },
  }))) || [], [draft])

  const onConnect = useCallback((connection: Connection) => {
    if (!connection.source || !connection.target || connection.source === connection.target) return
    updateDraft(current => ({ ...current, tasks: current.tasks.map(task =>
      task.task_id === connection.target && !task.depends_on.includes(connection.source!)
        ? { ...task, depends_on: [...task.depends_on, connection.source!] } : task) }))
  }, [])

  const addTask = () => {
    if (!draft || !catalog) return
    const agent = catalog.agents[0]
    const id = `task_${Date.now().toString(36)}`
    const task: DraftTask = { task_id: id, goal: '新任务', capability: agent.capabilities[0],
      depends_on: [], priority: 0, agent_id: agent.agent_id, input_refs: [],
      allowed_tools: agent.allowed_tools.slice(0, 1), workspace_ref: draft.request.context_refs[0] || null,
      max_attempts: 3 }
    updateDraft(current => ({ ...current, tasks: [...current.tasks, task] }))
    setSelectedId(id)
  }

  const removeTask = (id: string) => {
    updateDraft(current => ({ ...current, tasks: current.tasks.filter(task => task.task_id !== id)
      .map(task => ({ ...task, depends_on: task.depends_on.filter(dep => dep !== id) })) }))
    setSelectedId(null)
  }

  const autoLayout = () => {
    if (!draft) return
    const positions = layout(draft.tasks)
    setNodes(current => current.map(node => ({ ...node, position: positions.get(node.id) || node.position })))
  }

  const validate = async () => {
    if (!draft) return
    setBusy(true)
    try {
      const response = await fetch('/api/plans/validate', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(draft) })
      const body = await response.json() as ValidationResult
      if (!Array.isArray(body.errors)) throw new Error('服务端响应格式不正确')
      setResult(body)
      setNotice(body.valid ? '计划校验通过。这仍是静态预览，尚未启动 Run。' : '请根据下方问题修正草案。')
    } catch (error) { setNotice(error instanceof Error ? error.message : '校验失败') }
    finally { setBusy(false) }
  }

  const exportDraft = () => {
    if (!draft) return
    const blob = new Blob([JSON.stringify(draft, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url; link.download = 'agent-plan-draft.json'; link.click()
    URL.revokeObjectURL(url)
  }

  const importDraft = async (file: File) => {
    try {
      const parsed = JSON.parse(await file.text()) as PlanDraft
      if (!parsed || typeof parsed !== 'object' || !parsed.request || !Array.isArray(parsed.tasks)
        || typeof parsed.request.goal !== 'string' || !parsed.request.budget
        || 'permissions' in parsed.request || 'permissions' in parsed) {
        throw new Error('文件必须是草案格式，且不能包含权限声明')
      }
      if (parsed.tasks.some(task => !task || typeof task.task_id !== 'string' || !Array.isArray(task.depends_on)))
        throw new Error('任务字段不完整')
      const response = await fetch('/api/plans/validate', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(parsed) })
      const validation = await response.json() as ValidationResult
      if (response.status === 422) throw new Error(validation.errors?.[0]?.message || '草案格式无效')
      if (!response.ok) throw new Error('服务端无法校验导入文件')
      setDraft(parsed)
      setSelectedId(parsed.tasks[0]?.task_id || null)
      setNodes([])
      setResult(validation)
      setNotice(validation.valid ? '草案已导入并通过服务端校验。' : '草案已导入，请修正检查结果。')
    } catch (error) { setNotice(error instanceof Error ? error.message : '导入失败') }
    if (fileRef.current) fileRef.current.value = ''
  }

  const agentOptions = catalog?.agents || []
  const allowedTools = catalog?.tools.filter(tool => selectedAgent?.allowed_tools.includes(tool.name)
    && !selectedAgent.forbidden_tools.includes(tool.name)) || []

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand-mark">◎</div>
      <div className="brand-copy"><strong>AGENT PLAN STUDIO</strong><span>可视化工作平台 · P0</span></div>
      <div className="top-spacer" />
      <span className="phase-pill"><span className="phase-dot" /> 静态计划预览</span>
      <button className="top-help" onClick={() => window.open('/docs', '_blank')}>API 文档 ↗</button>
    </header>

    <main className={`workspace ${focusCanvas ? 'focus-canvas' : ''}`}>
      <aside className="left-panel">
        <div className="section-kicker">01 / TASK CONTRACT</div>
        <h1>定义工作目标</h1>
        <p className="muted-intro">描述目标与验收标准，再把工作拆成可验证的任务。</p>
        {!draft ? <div className="empty-side">{busy ? '正在载入示例…' : '无法连接 API，请启动 Python 服务。'}</div> : <>
          <Field label="工作目标"><textarea className="goal-input" value={draft.request.goal}
            onChange={event => updateRequest({ goal: event.target.value })} /></Field>
          <Field label="约束条件" hint="每行一项"><textarea rows={3} value={listText(draft.request.constraints)}
            onChange={event => updateRequest({ constraints: lines(event.target.value) })} /></Field>
          <Field label="上下文引用" hint="每行一个受控引用"><textarea rows={2} value={listText(draft.request.context_refs)}
            onChange={event => updateRequest({ context_refs: lines(event.target.value) })} /></Field>
          <div className="field"><span className="field-label">验收条件</span><div className="check-list">
            {catalog?.acceptance_criteria.map(criterion => <label className="check-row" key={criterion}>
              <input type="checkbox" checked={draft.request.acceptance_criteria.includes(criterion)}
                onChange={event => updateRequest({ acceptance_criteria: event.target.checked
                  ? [...draft.request.acceptance_criteria, criterion]
                  : draft.request.acceptance_criteria.filter(item => item !== criterion) })} />
              <span>{criterion}</span></label>)}
          </div></div>
          <div className="budget-head"><span className="field-label">执行预算</span><span>预览规则</span></div>
          <div className="budget-grid">
            {([['max_tasks', '任务上限'], ['max_depth', '最大深度'], ['max_concurrency', '并发上限'],
              ['max_steps', '步骤上限'], ['max_llm_calls', '模型调用'], ['max_tool_calls', '工具调用'],
              ['timeout_seconds', '超时（秒）']] as [keyof Budget, string][]).map(([key, label]) =>
              <label className="budget-item" key={key}><span>{label}</span><input type="number" min="0"
                value={draft.request.budget[key]} onChange={event => updateBudget(key, Number(event.target.value))} /></label>)}
          </div>
          <div className="policy-note"><span>◇</span><div><strong>权限由服务端决定</strong><p>页面只能选择注册工具，不能自行授予权限或执行任务。</p></div></div>
        </>}
      </aside>

      <section className="center-panel">
        <div className="canvas-header">
          <div><div className="section-kicker">02 / WORKFLOW CANVAS</div><h2>任务编排画布</h2>
            <p>{draft ? `${draft.tasks.length} 个任务 · ${edges.length} 条依赖 · 拖动节点，连接左右端口` : '等待示例数据'}</p></div>
          <div className="canvas-actions">
            <button className="button subtle" onClick={loadExample} disabled={busy}>↺ 示例</button>
            <button className="button subtle" onClick={() => fileRef.current?.click()}>↓ 导入</button>
            <input ref={fileRef} type="file" accept="application/json,.json" hidden
              onChange={event => { const file = event.target.files?.[0]; if (file) void importDraft(file) }} />
            <button className="button subtle" onClick={exportDraft} disabled={!draft}>↑ 导出</button>
          </div>
        </div>
        <div className="canvas-toolbar"><span className="toolbar-title">PLAN GRAPH</span><span className="toolbar-divider" />
          <button onClick={addTask} disabled={!draft}>＋ 添加任务</button>
          <button onClick={autoLayout} disabled={!draft}>▦ 自动布局</button>
          <button onClick={() => setFocusCanvas(value => !value)}>{focusCanvas ? '◧ 显示侧栏' : '▣ 专注画布'}</button>
          <span className="toolbar-spacer" /><span className="canvas-hint">仅草案 · 不会执行 Agent</span></div>
        <div className="graph-wrap">
          {draft && <ReactFlow<TaskNode, Edge> nodes={nodes} edges={edges} nodeTypes={nodeTypes}
            onInit={instance => { flowRef.current = instance }}
            onNodesChange={onNodesChange} onConnect={onConnect} onNodeClick={(_, node) => setSelectedId(node.id)}
            nodesDraggable nodesConnectable edgesReconnectable={false} deleteKeyCode={null}
            fitView fitViewOptions={{ padding: 0.18 }} minZoom={0.3} maxZoom={1.5}
            proOptions={{ hideAttribution: true }}>
            <Background gap={22} size={1} color="#e1e7f0" />
            <Controls showInteractive={false} /><MiniMap pannable zoomable style={{ width: 120, height: 82 }} nodeColor={node =>
              issueIds.has(node.id) ? '#ed796f' : '#6175dd'} />
          </ReactFlow>}
        </div>
        <div className="validation-panel">
          <div className="validation-head"><div><span className="section-kicker">03 / VALIDATION</span>
            <h3>计划检查</h3></div><button className="button primary" onClick={validate} disabled={!draft || busy}>
              {busy ? '检查中…' : '运行校验 →'}</button></div>
          {notice && <div className={`notice ${result?.valid ? 'success' : ''}`}>{notice}</div>}
          {!result ? <p className="muted-message">编辑草案后，点击“运行校验”查看依赖、权限和预算检查。</p>
            : result.valid && result.report ? <div className="report-row">
              <div className="report-ok">✓ <span>校验通过</span></div>
              <div className="report-metric"><strong>{result.report.parallel_levels.length}</strong><span>并行层</span></div>
              <div className="report-metric"><strong>{result.report.maximum_depth}</strong><span>最大深度</span></div>
              <div className="level-list">{result.report.parallel_levels.map((level, index) =>
                <span key={index}>L{index + 1}: {level.join(' · ')}</span>)}</div>
            </div> : <div className="issues">{result.errors.map((issue: ValidationIssue, index) =>
              <button className="issue" key={`${issue.code}-${index}`} onClick={() => {
                const id = issue.task_ids[0] || (issue.field?.match(/^tasks\.(\d+)/)
                  ? draft?.tasks[Number(issue.field.match(/^tasks\.(\d+)/)?.[1])]?.task_id : undefined)
                if (id) setSelectedId(id)
              }}><span className="issue-icon">!</span><span><strong>{issueNames[issue.code] || issue.code}</strong>
                <small>{issue.message}{issue.task_ids.length ? ` · ${issue.task_ids.join(', ')}` : ''}</small></span></button>)}</div>}
        </div>
      </section>

      <aside className="right-panel">
        <div className="section-kicker">04 / TASK INSPECTOR</div>
        {selectedTask ? <>
          <div className="inspector-title"><div><h2>任务详情</h2><p>{selectedTask.task_id}</p></div>
            <button className="icon-button" title="删除任务" onClick={() => removeTask(selectedTask.task_id)}>×</button></div>
          <div className="inspector-status"><span className="status-dot" /> 草案节点 <span>·</span> 优先级 {selectedTask.priority}</div>
          <Field label="任务说明"><textarea rows={3} value={selectedTask.goal}
            onChange={event => updateTask(selectedTask.task_id, { goal: event.target.value })} /></Field>
          <Field label="负责 Agent"><select value={selectedTask.agent_id} onChange={event => {
            const agent = agentOptions.find(item => item.agent_id === event.target.value)
            if (agent) updateTask(selectedTask.task_id, { agent_id: agent.agent_id,
              capability: agent.capabilities[0], allowed_tools: agent.allowed_tools.slice(0, 1) })
          }}>{agentOptions.map(agent => <option key={agent.agent_id} value={agent.agent_id}>{agent.agent_id} · v{agent.version}</option>)}</select></Field>
          <Field label="能力"><select value={selectedTask.capability} onChange={event =>
            updateTask(selectedTask.task_id, { capability: event.target.value })}>
            {selectedAgent?.capabilities.map(capability => <option key={capability}>{capability}</option>)}</select></Field>
          <div className="inspector-split"><Field label="优先级"><input type="number" min="0" max="100" value={selectedTask.priority}
            onChange={event => updateTask(selectedTask.task_id, { priority: Number(event.target.value) })} /></Field>
            <Field label="最多尝试"><input type="number" min="1" max="3" value={selectedTask.max_attempts}
              onChange={event => updateTask(selectedTask.task_id, { max_attempts: Number(event.target.value) })} /></Field></div>
          <div className="field"><span className="field-label">依赖任务</span><div className="check-list">
            {draft?.tasks.filter(task => task.task_id !== selectedTask.task_id).map(task =>
              <label className="check-row" key={task.task_id}><input type="checkbox"
                checked={selectedTask.depends_on.includes(task.task_id)} onChange={event =>
                  updateTask(selectedTask.task_id, { depends_on: event.target.checked
                    ? [...selectedTask.depends_on, task.task_id]
                    : selectedTask.depends_on.filter(id => id !== task.task_id) })} />
                <span>{task.task_id}</span></label>)}
          </div></div>
          <div className="field"><span className="field-label">允许工具子集</span><div className="check-list">
            {allowedTools.map(tool => <label className="check-row" key={tool.name}>
              <input type="checkbox" checked={selectedTask.allowed_tools.includes(tool.name)} onChange={event =>
                updateTask(selectedTask.task_id, { allowed_tools: event.target.checked
                  ? [...selectedTask.allowed_tools, tool.name]
                  : selectedTask.allowed_tools.filter(name => name !== tool.name) })} />
              <span>{tool.name}<em>{tool.risk_level}</em></span></label>)}
          </div></div>
          <Field label="工作区引用"><select value={selectedTask.workspace_ref || ''} onChange={event =>
            updateTask(selectedTask.task_id, { workspace_ref: event.target.value || null })}>
            <option value="">无工作区</option>{draft?.request.context_refs.map(ref =>
              <option value={ref} key={ref}>{ref}</option>)}</select></Field>
          <Field label="输入引用" hint="每行一项"><textarea rows={2} value={listText(selectedTask.input_refs)}
            onChange={event => updateTask(selectedTask.task_id, { input_refs: lines(event.target.value) })} /></Field>
          <div className="manifest-card"><span>AGENT MANIFEST</span><strong>{selectedAgent?.agent_id}</strong>
            <small>风险上限 {selectedAgent?.risk_ceiling} · {selectedAgent?.model_profile}</small></div>
        </> : <div className="empty-inspector"><div>◇</div><strong>选择一个任务节点</strong><p>查看 Agent、能力、工具和依赖设置。</p></div>}
      </aside>
    </main>
  </div>
}

export default App
