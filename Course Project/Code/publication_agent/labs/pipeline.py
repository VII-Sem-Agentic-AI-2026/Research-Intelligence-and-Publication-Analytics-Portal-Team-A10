"""Sequential Chapter 14 lab pipeline with explicit artifact handoffs."""

from .contracts import LabExecution
from . import (
    lab01_agent_loop, lab02_typed_tools, lab03_reusable_skills,
    lab04_memory_retrieval, lab05_connector, lab06_runtime,
    lab07_node_graph, lab08_parallel_swarm, lab09_grounding,
    lab10_resilience, lab11_sdlc_factory, lab12_governance,
    lab13_specialists, lab14_capstone,
)


class LabPipeline:
    MODULES = (
        lab01_agent_loop, lab02_typed_tools, lab03_reusable_skills,
        lab04_memory_retrieval, lab05_connector, lab06_runtime,
        lab07_node_graph, lab08_parallel_swarm, lab09_grounding,
        lab10_resilience, lab11_sdlc_factory, lab12_governance,
        lab13_specialists, lab14_capstone,
    )
    DEPENDENCIES = {
        1: set(), 2: {1}, 3: {1}, 4: {1}, 5: {2}, 6: {5}, 7: {6},
        8: {3, 5, 7}, 9: {8}, 10: {9}, 11: {10}, 12: {11},
        13: {12}, 14: set(range(1, 14)),
    }

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator

    @classmethod
    def resolve(cls, selected_labs=None):
        requested = list(range(1, 15)) if selected_labs is None else sorted({int(str(x).lower().replace("lab", "")) for x in selected_labs})
        if not requested:raise ValueError('Select at least one lab; use None for the full pipeline')
        if any(x < 1 or x > 14 for x in requested):
            raise ValueError("Labs must be numbered from 1 to 14")
        resolved = set()
        def include(number):
            for dependency in cls.DEPENDENCIES[number]: include(dependency)
            resolved.add(number)
        for number in requested: include(number)
        return requested, sorted(resolved)

    def execute(self, run, inject_fault=None, selected_labs=None):
        requested, resolved = self.resolve(selected_labs)
        run.requested_labs = [f"lab{x:02d}" for x in requested]
        run.executed_labs = [f"lab{x:02d}" for x in resolved]
        execution = LabExecution(self.orchestrator, run, inject_fault)
        from copy import deepcopy
        execution.artifacts.update(deepcopy(run.artifacts))
        if 'lab03' in execution.artifacts:
            from ..core import ReportFormattingSkill
            execution.artifacts['lab03']['_formatter'] = ReportFormattingSkill()
        for number in resolved:
            if f'lab{number:02d}' in execution.artifacts:
                continue
            self.MODULES[number - 1].execute(execution)
        if 12 not in resolved:
            run.status = "SELECTED_LABS_COMPLETED"
            self.orchestrator.runtime.checkpoint(run)
        return run
