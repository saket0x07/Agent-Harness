import pytest
from src.core.schemas import TaskSpec, AgentResult, TraceEvent
from src.grading.grader import GraderEngine
from src.grading.llm_judge import evaluate_subjective_quality, JudgeScore

def test_deterministic_keyword_matches():
    """Verify that GraderEngine detects presence and absence of required keywords."""
    task = TaskSpec(
        task_id="t_keywords",
        agent_target="mock",
        input={},
        expected={"required_keywords": ["mcp", "agent", "python"]},
        grading_strategy=["deterministic_keyword_match"]
    )
    
    # 1. Matching case
    res_pass = AgentResult(
        task_id="t_keywords",
        final_output="MCP is an agentic framework implemented in Python.",
        trace=[],
        total_latency_ms=100,
        total_cost_usd=0.0
    )
    grader_pass = GraderEngine(task)
    grading_res_pass = grader_pass.grade(res_pass)
    assert grading_res_pass.deterministic["required_keywords_pass"] is True
    assert grading_res_pass.is_pass is True

    # 2. Failing case (missing "python")
    res_fail = AgentResult(
        task_id="t_keywords",
        final_output="MCP is an agentic framework.",
        trace=[],
        total_latency_ms=100,
        total_cost_usd=0.0
    )
    grader_fail = GraderEngine(task)
    grading_res_fail = grader_fail.grade(res_fail)
    assert grading_res_fail.deterministic["required_keywords_pass"] is False
    assert grading_res_fail.is_pass is False

def test_deterministic_sections_count():
    """Verify that GraderEngine counts markdown headings correctly."""
    task = TaskSpec(
        task_id="t_sections",
        agent_target="mock",
        input={},
        expected={"min_sections": 3},
        grading_strategy=[]
    )
    
    # 3 headings -> pass
    res_pass = AgentResult(
        task_id="t_sections",
        final_output="# Header 1\nContent\n## Header 2\nContent\n### Header 3\nContent",
        trace=[],
        total_latency_ms=100,
        total_cost_usd=0.0
    )
    grading_res_pass = GraderEngine(task).grade(res_pass)
    assert grading_res_pass.deterministic["min_sections_pass"] is True
    assert grading_res_pass.deterministic["sections_count"] == 3

    # 2 headings -> fail
    res_fail = AgentResult(
        task_id="t_sections",
        final_output="# Header 1\nContent\nSome details",
        trace=[],
        total_latency_ms=100,
        total_cost_usd=0.0
    )
    grading_res_fail = GraderEngine(task).grade(res_fail)
    assert grading_res_fail.deterministic["min_sections_pass"] is False
    assert grading_res_fail.deterministic["sections_count"] == 1

def test_deterministic_citations_checking():
    """Verify that GraderEngine checks for footnote tags or hyperlink resources."""
    task = TaskSpec(
        task_id="t_citations",
        agent_target="mock",
        input={},
        expected={"must_have_citations": True},
        grading_strategy=[]
    )
    
    # Footnote citation -> pass
    res_footnote = AgentResult(
        task_id="t_citations",
        final_output="This is standard MCP [1].",
        trace=[],
        total_latency_ms=100,
        total_cost_usd=0.0
    )
    assert GraderEngine(task).grade(res_footnote).deterministic["citations_pass"] is True

    # URL citation -> pass
    res_url = AgentResult(
        task_id="t_citations",
        final_output="Details at https://modelcontextprotocol.org/.",
        trace=[],
        total_latency_ms=100,
        total_cost_usd=0.0
    )
    assert GraderEngine(task).grade(res_url).deterministic["citations_pass"] is True

    # No citations -> fail
    res_none = AgentResult(
        task_id="t_citations",
        final_output="No links or brackets here.",
        trace=[],
        total_latency_ms=100,
        total_cost_usd=0.0
    )
    assert GraderEngine(task).grade(res_none).deterministic["citations_pass"] is False

def test_trajectory_infinite_loop_detection():
    """Verify that calling the identical tool name and args 3+ times consecutively is flagged as infinite_loop."""
    task = TaskSpec(
        task_id="t_loop",
        agent_target="mock",
        input={},
        expected={},
        grading_strategy=[]
    )
    
    # 3 consecutive identical search calls -> loop detected
    trace_loop = [
        TraceEvent(trace_id="tr_1", span_id="s1", node="n1", type="tool_call", tool_name="google_search", tool_args={"query": "mcp"}, start_ts=100, end_ts=200),
        TraceEvent(trace_id="tr_1", span_id="s2", node="n2", type="tool_call", tool_name="google_search", tool_args={"query": "mcp"}, start_ts=200, end_ts=300),
        TraceEvent(trace_id="tr_1", span_id="s3", node="n3", type="tool_call", tool_name="google_search", tool_args={"query": "mcp"}, start_ts=300, end_ts=400)
    ]
    res_loop = AgentResult(
        task_id="t_loop",
        final_output="Timed out.",
        trace=trace_loop,
        total_latency_ms=100,
        total_cost_usd=0.0
    )
    grading_res_loop = GraderEngine(task).grade(res_loop)
    assert grading_res_loop.trajectory["infinite_loop"] is True
    assert grading_res_loop.trajectory["failure_mode"] == "infinite_loop"
    assert grading_res_loop.is_pass is False

    # 3 search calls but with different queries -> no loop
    trace_no_loop = [
        TraceEvent(trace_id="tr_2", span_id="s1", node="n1", type="tool_call", tool_name="google_search", tool_args={"query": "mcp"}, start_ts=100, end_ts=200),
        TraceEvent(trace_id="tr_2", span_id="s2", node="n2", type="tool_call", tool_name="google_search", tool_args={"query": "claude"}, start_ts=200, end_ts=300),
        TraceEvent(trace_id="tr_2", span_id="s3", node="n3", type="tool_call", tool_name="google_search", tool_args={"query": "mcp"}, start_ts=300, end_ts=400)
    ]
    res_no_loop = AgentResult(
        task_id="t_loop",
        final_output="Outcome",
        trace=trace_no_loop,
        total_latency_ms=100,
        total_cost_usd=0.0
    )
    grading_res_no_loop = GraderEngine(task).grade(res_no_loop)
    assert grading_res_no_loop.trajectory["infinite_loop"] is False
    assert grading_res_no_loop.is_pass is True

def test_trajectory_premature_termination():
    """Verify that ending with empty outputs and no execution steps is flagged as premature_termination."""
    task = TaskSpec(
        task_id="t_term",
        agent_target="mock",
        input={},
        expected={},
        grading_strategy=[]
    )
    
    # Empty output and no tool spans -> premature termination
    res_empty = AgentResult(
        task_id="t_term",
        final_output="Failed",
        trace=[],
        total_latency_ms=100,
        total_cost_usd=0.0
    )
    grading_res = GraderEngine(task).grade(res_empty)
    assert grading_res.trajectory["premature_termination"] is True
    assert grading_res.trajectory["failure_mode"] == "premature_termination"
    assert grading_res.is_pass is False

def test_llm_judge_offline_fallback(monkeypatch):
    """Verify that evaluate_subjective_quality returns placeholder values when API key is missing."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    
    task = TaskSpec(
        task_id="t_fallback",
        agent_target="mock",
        input={},
        expected={},
        grading_strategy=[]
    )
    res = AgentResult(
        task_id="t_fallback",
        final_output="Draft content",
        trace=[],
        total_latency_ms=100,
        total_cost_usd=0.0
    )
    
    score = evaluate_subjective_quality(task, res)
    assert isinstance(score, JudgeScore)
    assert score.clarity == 4
    assert score.accuracy == 4
    assert "[Offline Fallback Mode]" in score.critique
