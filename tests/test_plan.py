import pytest

from agent_runtime.core.planning import PlanError, PlanValidator


def validated(sample):
    return PlanValidator().validate(*sample[:3], environment_permissions=sample[3])


def test_sample_dag_and_effective_tools(sample):
    report = validated(sample)
    assert report.parallel_levels == (("t1_research",), ("t2_rag", "t3_patch_draft"), ("t4_patch_verify",))
    assert report.maximum_depth == 3
    assert report.effective_tools["t4_patch_verify"] == ("sandbox.apply_patch", "sandbox.pytest")
    assert report.manifest_versions["coding_agent"] == "0.1.0"


@pytest.mark.parametrize("change", [
    lambda tasks: tasks.__setitem__(0, tasks[0].model_copy(update={"depends_on": ["t4_patch_verify"]})),
    lambda tasks: tasks.__setitem__(1, tasks[1].model_copy(update={"depends_on": ["missing"]})),
    lambda tasks: tasks.__setitem__(1, tasks[1].model_copy(update={"task_id": "t1_research"})),
    lambda tasks: tasks.__setitem__(1, tasks[1].model_copy(update={"capability": "coding.patch.verify"})),
])
def test_invalid_plan_graph_or_agent_is_rejected(sample, change):
    contract, originals, manifests, environment = sample
    tasks = list(originals)
    change(tasks)
    with pytest.raises(PlanError):
        PlanValidator().validate(contract, tasks, manifests, environment_permissions=environment)


def test_contract_and_environment_permission_intersection(sample):
    contract, tasks, manifests, environment = sample
    with pytest.raises(PlanError, match="permission denied"):
        PlanValidator().validate(contract.model_copy(update={"permissions": ["repo.read", "rag.search.local"]}),
                                 tasks, manifests, environment_permissions=environment)
    with pytest.raises(PlanError, match="permission denied"):
        PlanValidator().validate(contract, tasks, manifests,
                                 environment_permissions=frozenset({"repo.read", "rag.search.local"}))


def test_unmapped_acceptance_and_depth_limit(sample):
    contract, tasks, manifests, environment = sample
    with pytest.raises(PlanError, match="registered verifier"):
        PlanValidator().validate(contract.model_copy(update={"acceptance_criteria": ["wishful_thinking"]}),
                                 tasks, manifests, environment_permissions=environment)
    shallow = contract.model_copy(update={"budget": contract.budget.model_copy(update={"max_depth": 2})})
    with pytest.raises(PlanError, match="depth"):
        PlanValidator().validate(shallow, tasks, manifests, environment_permissions=environment)


def test_parallel_write_to_same_workspace_rejected(sample):
    contract, originals, manifests, environment = sample
    tasks = list(originals)
    tasks[2] = tasks[2].model_copy(update={"allowed_tools": ["sandbox.apply_patch"]})
    with pytest.raises(PlanError, match="parallel workspace conflict"):
        PlanValidator().validate(contract, tasks, manifests, environment_permissions=environment)
