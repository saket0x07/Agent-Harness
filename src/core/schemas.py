from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class TraceEvent(BaseModel):
    """Represents a single span/event in the execution hierarchy of an agent run."""
    trace_id: str = Field(..., description="Unique ID for the full execution trajectory")
    span_id: str = Field(..., description="Unique ID for this specific span/event")
    parent_span_id: Optional[str] = Field(None, description="Span ID of the parent caller, if any")
    node: str = Field(..., description="Name of the agent node or component executing this step")
    type: str = Field(..., description="Type of event: e.g., tool_call, llm_call, state_transition")
    start_ts: int = Field(..., description="Start timestamp in milliseconds")
    end_ts: Optional[int] = Field(None, description="End timestamp in milliseconds")
    tokens_in: Optional[int] = Field(None, description="Number of input tokens (for LLM calls)")
    tokens_out: Optional[int] = Field(None, description="Number of output tokens (for LLM calls)")
    cost_usd: Optional[float] = Field(None, description="Estimated USD cost of the call")
    tool_name: Optional[str] = Field(None, description="Name of the tool called, if applicable")
    tool_args: Optional[Dict[str, Any]] = Field(None, description="Arguments passed to the tool, if applicable")
    output_summary: Optional[str] = Field(None, description="Summary or snippet of the output")
    error: Optional[str] = Field(None, description="Error message if the span execution failed")

class TaskSpec(BaseModel):
    """Specification of a task in an evaluation suite."""
    task_id: str = Field(..., description="Unique task identifier")
    agent_target: str = Field(..., description="Name of the target agent to execute this task")
    input: Dict[str, Any] = Field(..., description="Input parameters/data for the agent run")
    expected: Dict[str, Any] = Field(..., description="Ground truth or expectations for grading")
    grading_strategy: List[str] = Field(..., description="List of grading strategies to apply (e.g. deterministic, llm_judge)")
    difficulty: str = Field("medium", description="Difficulty level: easy, medium, hard")
    tags: List[str] = Field(default_factory=list, description="Categorization tags for filtering task suites")

class AgentResult(BaseModel):
    """Output contract returned by the Agent Adapter Layer after running a task."""
    task_id: str = Field(..., description="Task ID this result corresponds to")
    final_output: Any = Field(..., description="The final text or data output returned by the agent")
    trace: List[TraceEvent] = Field(..., description="List of trace events captured during the execution")
    total_cost_usd: float = Field(0.0, description="Sum of cost across all trace spans")
    total_latency_ms: int = Field(..., description="Total execution time of the agent run in milliseconds")

class GradingResult(BaseModel):
    """Evaluation result for a single agent execution run."""
    task_id: str = Field(..., description="Task ID evaluated")
    trace_id: str = Field(..., description="Trace ID evaluated")
    deterministic: Dict[str, Any] = Field(default_factory=dict, description="Results of deterministic checks")
    llm_judge: Optional[Dict[str, Any]] = Field(None, description="Results of LLM rubric grading (scores and critique)")
    trajectory: Dict[str, Any] = Field(default_factory=dict, description="Trajectory and failure classification analysis")
    is_pass: bool = Field(..., description="Overall pass/fail outcome for the task")

class MetricsReport(BaseModel):
    """Consolidated metrics summary for a suite execution run."""
    agent_name: str = Field(..., description="Name of the agent under evaluation")
    agent_version: str = Field(..., description="Version identifier of the agent under evaluation")
    run_id: str = Field(..., description="Unique ID for this suite run")
    timestamp: str = Field(..., description="ISO timestamp of when the report was generated")
    total_tasks: int = Field(..., description="Total tasks in the run")
    success_rate: float = Field(..., description="Percentage of passed tasks (0.0 to 1.0)")
    average_cost_usd: float = Field(..., description="Average USD cost per task run")
    average_latency_ms: float = Field(..., description="Average latency in milliseconds per task run")
    failure_mode_counts: Dict[str, int] = Field(default_factory=dict, description="Frequencies of failure classifications")
    detailed_results: List[GradingResult] = Field(..., description="Individual task grading records")

class RegressionAlert(BaseModel):
    """Defines a regression signal compared against a baseline run."""
    agent: str = Field(..., description="Target agent name")
    baseline_version: str = Field(..., description="Agent version used as reference baseline")
    current_version: str = Field(..., description="Agent version evaluated in current run")
    metric: str = Field(..., description="Metric that regressed (e.g. success_rate, cost)")
    baseline_value: float = Field(..., description="Value in baseline run")
    current_value: float = Field(..., description="Value in current run")
    delta: float = Field(..., description="Current value minus baseline value")
    threshold: float = Field(..., description="Tolerance threshold (e.g. -0.05)")
    triggered: bool = Field(..., description="True if the regression exceeds the threshold")
    likely_component: Optional[str] = Field(None, description="Component identified as the likely cause of degradation")
