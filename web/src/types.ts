export type Budget = {
  max_steps: number
  max_llm_calls: number
  max_tool_calls: number
  timeout_seconds: number
  max_tasks: number
  max_depth: number
  max_concurrency: number
}

export type ContractRequest = {
  goal: string
  constraints: string[]
  acceptance_criteria: string[]
  context_refs: string[]
  budget: Budget
}

export type DraftTask = {
  task_id: string
  goal: string
  capability: string
  depends_on: string[]
  priority: number
  agent_id: string
  input_refs: string[]
  allowed_tools: string[]
  workspace_ref: string | null
  max_attempts: number
}

export type PlanDraft = { request: ContractRequest; tasks: DraftTask[] }

export type Agent = {
  agent_id: string
  version: string
  capabilities: string[]
  allowed_tools: string[]
  forbidden_tools: string[]
  risk_ceiling: string
  model_profile: string
}

export type Tool = {
  name: string
  permissions: string[]
  risk_level: string
  writes_workspace: boolean
}

export type Catalog = {
  mode: 'plan_preview'
  agents: Agent[]
  tools: Tool[]
  acceptance_criteria: string[]
  preview_permissions: string[]
}

export type ValidationIssue = {
  code: string
  message: string
  field: string | null
  task_ids: string[]
}

export type PlanReport = {
  task_order: string[]
  parallel_levels: string[][]
  maximum_depth: number
  effective_tools: Record<string, string[]>
  manifest_versions: Record<string, string>
}

export type ValidationResult = {
  valid: boolean
  report?: PlanReport
  errors: ValidationIssue[]
}
