import pytest
import threading
import time
from src.core.schemas import TaskSpec, AgentResult
from src.adapters.base import AgentAdapter
from src.adapters.mock_agent import MockAgentAdapter
from src.tracing.tracer import TraceCollector, trace_span

def test_adapter_protocol_compliance():
    """Verify that MockAgentAdapter implements the AgentAdapter protocol."""
    adapter: AgentAdapter = MockAgentAdapter()
    assert isinstance(adapter, AgentAdapter) or hasattr(adapter, "run")

def test_tracer_collection_and_nesting():
    """Verify nesting traces and parent-child span associations."""
    with TraceCollector() as tc:
        trace_id = tc.trace_id
        assert TraceCollector.get_trace_id() == trace_id

        with trace_span("parent_node", "agent_step") as parent_span:
            parent_span["output_summary"] = "parent start"
            time.sleep(0.005)

            with trace_span("child_node", "tool_call", tool_name="my_tool", tool_args={"x": 1}) as child_span:
                child_span["output_summary"] = "child output"
                child_span["cost_usd"] = 0.001

    events = TraceCollector.get_events()
    assert len(events) == 2

    # Events are appended when their trace_span context exits (innermost first)
    child_event = events[0]
    parent_event = events[1]

    # Verify fields
    assert child_event.node == "child_node"
    assert child_event.type == "tool_call"
    assert child_event.tool_name == "my_tool"
    assert child_event.tool_args == {"x": 1}
    assert child_event.cost_usd == 0.001
    assert child_event.parent_span_id == parent_event.span_id

    assert parent_event.node == "parent_node"
    assert parent_event.type == "agent_step"
    assert parent_event.parent_span_id is None

def test_tracer_error_capture():
    """Verify that exceptions inside trace_span are logged to the span and then re-raised."""
    with TraceCollector():
        with pytest.raises(ValueError) as exc_info:
            with trace_span("error_node", "llm_call") as span:
                raise ValueError("Oops, out of memory!")
        
    events = TraceCollector.get_events()
    assert len(events) == 1
    error_event = events[0]
    assert error_event.node == "error_node"
    assert "ValueError: Oops, out of memory!" in error_event.error

def test_tracer_thread_safety():
    """Verify that TraceCollector storage is thread-safe and doesn't bleed across threads."""
    def worker(name: str, delay: float, results_list: list):
        with TraceCollector(trace_id=f"trace_{name}"):
            time.sleep(delay)
            with trace_span(f"node_{name}", "step") as span:
                span["output_summary"] = f"done_{name}"
            results_list.extend(TraceCollector.get_events())

    results_t1 = []
    results_t2 = []

    t1 = threading.Thread(target=worker, args=("A", 0.02, results_t1))
    t2 = threading.Thread(target=worker, args=("B", 0.01, results_t2))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Thread A should only have trace A events, Thread B only trace B
    assert len(results_t1) == 1
    assert results_t1[0].trace_id == "trace_A"
    assert results_t1[0].node == "node_A"

    assert len(results_t2) == 1
    assert results_t2[0].trace_id == "trace_B"
    assert results_t2[0].node == "node_B"

def test_mock_agent_trajectories():
    """Verify the different simulated execution paths of the MockAgentAdapter."""
    adapter = MockAgentAdapter()
    
    # 1. Test "success" run
    task_success = TaskSpec(
        task_id="t_success",
        agent_target="mock",
        input={"topic": "Model Context Protocol", "required_sections": ["Intro", "Use Cases"]},
        expected={},
        grading_strategy=[]
    )
    res_success: AgentResult = adapter.run(task_success)
    assert "Draft: Model Context Protocol" in res_success.final_output
    assert len(res_success.trace) == 3  # planner, search, writer
    assert res_success.total_cost_usd > 0.0
    assert res_success.total_latency_ms >= 0

    # 2. Test "infinite_loop" run
    task_loop = TaskSpec(
        task_id="t_loop",
        agent_target="mock",
        input={"topic": "Model Context Protocol", "mock_behavior": "infinite_loop"},
        expected={},
        grading_strategy=[]
    )
    res_loop = adapter.run(task_loop)
    assert res_loop.final_output == "Search timed out."
    assert len(res_loop.trace) == 5  # planner + 4 search tool calls

    # 3. Test "fail_tool" run
    task_fail = TaskSpec(
        task_id="t_fail",
        agent_target="mock",
        input={"mock_behavior": "fail_tool"},
        expected={},
        grading_strategy=[]
    )
    res_fail = adapter.run(task_fail)
    assert res_fail.final_output == "Failed due to internal lookup error."
    assert len(res_fail.trace) == 2  # planner, failed db_lookup
    failed_span = res_fail.trace[1]  # db_lookup exits second, so it is index 1
    assert failed_span.node == "db_lookup"
    assert failed_span.error is not None
    assert "ConnectionResetError" in failed_span.error
