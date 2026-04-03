"""Workflow registration — importing this module registers all workflows."""

# Each graph module auto-registers its orchestrator with the registry on import.
from backend.workflows.ingest.graph import IngestOrchestrator  # noqa: F401
from backend.workflows.retrieval.graph import RetrievalOrchestrator  # noqa: F401
from backend.workflows.ingestion.graph import IngestionOrchestrator  # noqa: F401
from backend.workflows.synthesis.graph import SynthesisOrchestrator  # noqa: F401
from backend.workflows.synthesis.curriculum_graph import CurriculumOrchestrator  # noqa: F401
from backend.workflows.planner.graph import PlannerOrchestrator  # noqa: F401
