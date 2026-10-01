"""Mock-workflow scenarios for the SDK (see plans/sdk.md §9)."""

from .chroma.scenarios import SCENARIOS as CHROMA_SCENARIOS
from .langchain.scenarios import SCENARIOS as LANGCHAIN_SCENARIOS
from .langgraph.scenarios import SCENARIOS as LANGGRAPH_SCENARIOS
from .llamaindex.scenarios import SCENARIOS as LLAMAINDEX_SCENARIOS
from .ollama.scenarios import SCENARIOS as OLLAMA_SCENARIOS
from .runner import SCENARIOS, run_all, run_scenario
from .scenario import Scenario, ScenarioResult

__all__ = [
    "CHROMA_SCENARIOS",
    "LANGCHAIN_SCENARIOS",
    "LANGGRAPH_SCENARIOS",
    "LLAMAINDEX_SCENARIOS",
    "OLLAMA_SCENARIOS",
    "SCENARIOS",
    "Scenario",
    "ScenarioResult",
    "run_all",
    "run_scenario",
]