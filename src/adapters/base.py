from typing import Protocol, runtime_checkable
from src.core.schemas import TaskSpec, AgentResult

@runtime_checkable
class AgentAdapter(Protocol):
    """Protocol defining the standard interface for AI agent wrappers.
    
    Every agent framework under test (LangGraph, AutoGen, custom loop, etc.) 
    must be wrapped in an adapter implementing this protocol.
    """
    def run(self, task: TaskSpec) -> AgentResult:
        """Executes the wrapped agent against the given task specification.
        
        Args:
            task: TaskSpec object containing the input parameters.
            
        Returns:
            AgentResult: Normalized object containing the agent's output, execution costs, latency, and spans.
        """
        ...
