# No imports from backend.workflows or backend.services — this is the framework layer.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.lib.orchestrator import WorkflowOrchestrator


@dataclass
class WorkflowConfig:
    name: str
    orchestrator_class: type[WorkflowOrchestrator]
    description: str = ""


@dataclass
class WorkflowRegistry:
    _registry: dict[str, WorkflowConfig] = field(default_factory=dict)

    def register(self, config: WorkflowConfig) -> None:
        self._registry[config.name] = config

    def get(self, name: str) -> WorkflowConfig:
        if name not in self._registry:
            raise KeyError(
                f"Workflow '{name}' not registered. Available: {list(self._registry)}"
            )
        return self._registry[name]

    def list_workflows(self) -> list[str]:
        return list(self._registry.keys())


registry = WorkflowRegistry()
