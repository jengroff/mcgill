# No imports from backend.workflows or backend.services — this is the framework layer.

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Callable

from langgraph.graph.state import CompiledStateGraph

from backend.services.lib.state import BaseWorkflowState

logger = logging.getLogger(__name__)


class WorkflowOrchestrator(ABC):
    """Abstract base for all workflow orchestrators."""

    @abstractmethod
    def build_graph(self) -> CompiledStateGraph: ...

    @abstractmethod
    def build_initial_state(self, **kwargs) -> BaseWorkflowState: ...

    async def run(self, **kwargs) -> BaseWorkflowState:
        """Compile the graph and invoke with initial state."""
        graph = self.build_graph()
        initial_state = self.build_initial_state(**kwargs)
        result = await graph.ainvoke(initial_state)
        return result  # type: ignore[return-value]

    async def stream(
        self,
        on_event: Callable[[dict], None],
        **kwargs,
    ) -> BaseWorkflowState:
        """Compile the graph and stream events, calling on_event for each node completion."""
        graph = self.build_graph()
        initial_state = self.build_initial_state(**kwargs)

        final_state = initial_state
        async for event in graph.astream_events(initial_state, version="v2"):
            if (
                event["event"] == "on_chain_end"
                and event.get("name") in self._node_names()
            ):
                on_event(
                    {
                        "type": "step_update",
                        "phase": event["name"],
                        "node": event["name"],
                        "status": "done",
                    }
                )
            # Capture final state from the last chain end
            if event["event"] == "on_chain_end" and event.get("data", {}).get("output"):
                output = event["data"]["output"]
                if isinstance(output, dict):
                    final_state = {**final_state, **output}

        return final_state  # type: ignore[return-value]

    def _node_names(self) -> set[str]:
        """Return the set of node names for filtering stream events.

        Override this if your graph uses non-standard node names.
        """
        graph = self.build_graph()
        return set(graph.get_graph().nodes.keys()) - {"__start__", "__end__"}
