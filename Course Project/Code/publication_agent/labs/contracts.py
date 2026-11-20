from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LabExecution:
    orchestrator: Any
    run: Any
    inject_fault: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)

    def require(self, lab_key: str, artifact: str | None = None):
        if lab_key not in self.artifacts:
            raise RuntimeError(f"Required lab outcome is missing: {lab_key}")
        value = self.artifacts[lab_key]
        if artifact is not None:
            if artifact not in value:
                raise RuntimeError(f"Required artifact is missing: {lab_key}.{artifact}")
            return value[artifact]
        return value

    def save(self, lab_key: str, outcome: dict[str, Any]):
        serializable = {k: v for k, v in outcome.items() if not k.startswith("_")}
        self.artifacts[lab_key] = outcome
        self.run.lab_results[lab_key] = serializable
        self.run.artifacts[lab_key] = {k: v for k, v in outcome.items() if k != '_formatter'}
        self.orchestrator.runtime.audit(f"{lab_key}.complete", {}, serializable)
        self.orchestrator.runtime.checkpoint(self.run)
        return outcome

