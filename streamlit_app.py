import streamlit as st
import sqlite3
import json
import uuid
import time
import os
import pandas as pd
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Set up page configurations
st.set_page_config(
    page_title="Agent Evaluation Harness",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling for Premium Feel
st.markdown("""
<style>
    .reportview-container {
        background: #0e1117;
    }
    .metric-card {
        background-color: #1f2937;
        border: 1px solid #374151;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 15px;
    }
    .metric-value {
        font-size: 28px;
        font-weight: bold;
        color: #10b981;
    }
    .metric-label {
        font-size: 14px;
        color: #9ca3af;
    }
    .pass-badge {
        background-color: #065f46;
        color: #34d399;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: bold;
        font-size: 12px;
    }
    .fail-badge {
        background-color: #7f1d1d;
        color: #f87171;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: bold;
        font-size: 12px;
    }
    .tree-node-tool {
        border-left: 3px solid #3b82f6;
        background-color: #1e3a8a22;
        padding: 10px;
        margin: 5px 0 5px 15px;
        border-radius: 0 6px 6px 0;
    }
    .tree-node-llm {
        border-left: 3px solid #10b981;
        background-color: #065f4622;
        padding: 10px;
        margin: 5px 0 5px 15px;
        border-radius: 0 6px 6px 0;
    }
    .tree-node-node {
        border-left: 3px solid #8b5cf6;
        background-color: #4c1d9522;
        padding: 10px;
        margin: 5px 0;
        border-radius: 0 6px 6px 0;
    }
</style>
""", unsafe_allow_html=True)

# Imports from src
from src.storage.db import (
    DEFAULT_DB_PATH,
    get_all_runs,
    get_run_by_id,
    get_grading_results_for_run,
    get_traces_for_run,
    save_task,
    save_run,
    save_trace_events,
    save_grading_result,
    init_db
)
from src.runner import ADAPTER_REGISTRY
from src.grading.grader import GraderEngine
from src.grading.llm_judge import evaluate_subjective_quality, JudgeScore
from src.core.schemas import TaskSpec, AgentResult

# Automatically init db if needed
init_db(DEFAULT_DB_PATH)

# Main Title & Sidebar
st.sidebar.title("🤖 Agent Eval Harness")
st.sidebar.markdown("---")

navigation = st.sidebar.radio(
    "Navigation Views",
    [
        "📊 Dashboard & Trend Analysis",
        "📋 Runs & Detailed Reports",
        "🏃 Suite Runner & Comparison",
        "🔍 Trace & Token Visualizer",
        "🤖 Interactive Adapter Testing",
        "⚠️ Failure Mode Analysis",
        "🎯 Judge Calibration"
    ]
)

st.sidebar.markdown("---")
st.sidebar.info(
    "This interface visualizes and executes tests for the Agent Evaluation Harness."
)

# ----------------------------------------------------
# View 1: Dashboard & Trend Analysis
# ----------------------------------------------------
if navigation == "📊 Dashboard & Trend Analysis":
    st.title("📊 Dashboard & Trend Analysis")
    st.write("Overview metrics and performance trends across different runs and agent versions.")
    
    runs = get_all_runs(DEFAULT_DB_PATH)
    
    if not runs:
        st.warning("No runs found in the database. Run a suite first via CLI or the Interactive tab.")
    else:
        # High-level statistics
        col1, col2, col3, col4 = st.columns(4)
        
        total_runs = len(runs)
        avg_success = sum(r["metrics"].get("success_rate", 0.0) for r in runs) / total_runs
        avg_cost = sum(r["metrics"].get("average_cost_usd", 0.0) for r in runs) / total_runs
        avg_latency = sum(r["metrics"].get("average_latency_ms", 0.0) for r in runs) / total_runs
        
        with col1:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Total Runs</div><div class="metric-value">{total_runs}</div></div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Average Success Rate</div><div class="metric-value">{avg_success*100:.1f}%</div></div>', unsafe_allow_html=True)
        with col3:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Average Cost (USD)</div><div class="metric-value">${avg_cost:.4f}</div></div>', unsafe_allow_html=True)
        with col4:
            st.markdown(f'<div class="metric-card"><div class="metric-label">Average Latency (ms)</div><div class="metric-value">{avg_latency:.0f}ms</div></div>', unsafe_allow_html=True)
            
        # Prepare data for plotting
        chart_data = []
        for r in reversed(runs):
            metrics = r["metrics"]
            chart_data.append({
                "Run ID": r["run_id"],
                "Timestamp": r["timestamp"][:16].replace("T", " "),
                "Agent": f"{r['agent_name']} ({r['agent_version']})",
                "Success Rate (%)": metrics.get("success_rate", 0.0) * 100,
                "Avg Latency (ms)": metrics.get("average_latency_ms", 0.0),
                "Avg Cost ($)": metrics.get("average_cost_usd", 0.0)
            })
        
        df = pd.DataFrame(chart_data)
        
        st.subheader("📈 Performance Over Time")
        
        # Plot Success Rate
        st.markdown("**Success Rate Trend (%)**")
        st.line_chart(df.set_index("Timestamp")[["Success Rate (%)"]])
        
        # Plot Latency and Cost
        col_l, col_c = st.columns(2)
        with col_l:
            st.markdown("**Average Latency Trend (ms)**")
            st.line_chart(df.set_index("Timestamp")[["Avg Latency (ms)"]])
        with col_c:
            st.markdown("**Average Cost Trend ($)**")
            st.line_chart(df.set_index("Timestamp")[["Avg Cost ($)"]])
            
        st.subheader("📜 Run History Table")
        st.dataframe(df, use_container_width=True)

# ----------------------------------------------------
# View 2: Runs & Detailed Reports
# ----------------------------------------------------
elif navigation == "📋 Runs & Detailed Reports":
    st.title("📋 Runs & Detailed Reports")
    st.write("Inspect details, success metrics, and individual task outputs of a specific evaluation run.")
    
    runs = get_all_runs(DEFAULT_DB_PATH)
    
    if not runs:
        st.warning("No runs found in the database.")
    else:
        run_options = {f"{r['run_id']} - {r['agent_name']} ({r['agent_version']})": r["run_id"] for r in runs}
        selected_run_label = st.selectbox("Select Evaluation Run", list(run_options.keys()))
        selected_run_id = run_options[selected_run_label]
        
        run_data = get_run_by_id(selected_run_id, DEFAULT_DB_PATH)
        
        if run_data:
            metrics = run_data["metrics"]
            
            # Show parameters
            st.subheader("Run Metadata")
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.metric("Agent Name", run_data["agent_name"])
            m_col2.metric("Agent Version", run_data["agent_version"])
            m_col3.metric("Timestamp", run_data["timestamp"])
            m_col4.metric("Run ID", run_data["run_id"])
            
            # Show Detailed results
            st.subheader("Task Results in this Run")
            results = get_grading_results_for_run(selected_run_id, DEFAULT_DB_PATH)
            
            if not results:
                st.info("No task evaluations registered for this run.")
            else:
                grid_data = []
                for res in results:
                    grid_data.append({
                        "Task ID": res["task_id"],
                        "Trace ID": res["trace_id"],
                        "Passed": "✅ Yes" if res["is_pass"] else "❌ No",
                        "Difficulty": res["difficulty"],
                        "Failure Mode": res["trajectory"].get("failure_mode") or "None"
                    })
                st.table(pd.DataFrame(grid_data))
                
                # Drilldown into a specific task
                st.markdown("---")
                st.subheader("🔍 Inspect Task Output & Details")
                selected_task_id = st.selectbox("Select Task to View Output", [r["task_id"] for r in results])
                
                selected_result = next((r for r in results if r["task_id"] == selected_task_id), None)
                if selected_result:
                    t_col1, t_col2 = st.columns([2, 1])
                    
                    with t_col1:
                        # Fetch the final output from traces or output summaries
                        spans = get_traces_for_run(selected_result["trace_id"], DEFAULT_DB_PATH)
                        final_span = spans[-1] if spans else None
                        final_out = final_span["output_summary"] if final_span else "N/A"
                        
                        st.markdown("**Final Agent Output**")
                        st.text_area("Output Content", final_out, height=300, disabled=True)
                        
                    with t_col2:
                        st.markdown("**Grading Details**")
                        is_pass_html = '<span class="pass-badge">PASSED</span>' if selected_result["is_pass"] else '<span class="fail-badge">FAILED</span>'
                        st.markdown(f"Status: {is_pass_html}", unsafe_allow_html=True)
                        st.markdown(f"**Difficulty:** {selected_result['difficulty']}")
                        st.markdown(f"**Failure Mode:** {selected_result['trajectory'].get('failure_mode') or 'None'}")
                        
                        st.markdown("**Deterministic Checks**")
                        st.json(selected_result["deterministic"])
                        
                        if selected_result["llm_judge"]:
                            st.markdown("**LLM Judge Feedback**")
                            st.json(selected_result["llm_judge"])

# ----------------------------------------------------
# View 3: Trace & Token Visualizer
# ----------------------------------------------------
elif navigation == "🔍 Trace & Token Visualizer":
    st.title("🔍 Trace & Token Visualizer")
    st.write("Inspect execution spans, nesting trees, and resource consumption (cost/tokens) for a trace run.")
    
    runs = get_all_runs(DEFAULT_DB_PATH)
    if not runs:
        st.warning("No runs found in the database.")
    else:
        # Load run
        run_options = {f"{r['run_id']} - {r['agent_name']} ({r['agent_version']})": r["run_id"] for r in runs}
        selected_run_label = st.selectbox("Select Run", list(run_options.keys()), key="trace_run_select")
        selected_run_id = run_options[selected_run_label]
        
        results = get_grading_results_for_run(selected_run_id, DEFAULT_DB_PATH)
        if not results:
            st.info("No task evaluations registered for this run.")
        else:
            # Load task
            task_options = {f"{r['task_id']} ({'Pass' if r['is_pass'] else 'Fail'})": r["trace_id"] for r in results}
            selected_task_label = st.selectbox("Select Task Execution Trace", list(task_options.keys()))
            selected_trace_id = task_options[selected_task_label]
            
            spans = get_traces_for_run(selected_trace_id, DEFAULT_DB_PATH)
            
            if not spans:
                st.warning("No execution spans found for this trace ID in database.")
            else:
                st.subheader("💵 Total Trace Telemetry")
                tot_latency = 0
                tot_cost = 0.0
                tot_tokens_in = 0
                tot_tokens_out = 0
                
                for s in spans:
                    duration = (s["end_ts"] - s["start_ts"]) if s["end_ts"] else 0
                    tot_latency += duration
                    tot_cost += s["cost_usd"] or 0.0
                    tot_tokens_in += s["tokens_in"] or 0
                    tot_tokens_out += s["tokens_out"] or 0
                    
                tel_col1, tel_col2, tel_col3, tel_col4 = st.columns(4)
                tel_col1.metric("Total Latency", f"{tot_latency} ms")
                tel_col2.metric("Total Cost (USD)", f"${tot_cost:.5f}")
                tel_col3.metric("Input Tokens", tot_tokens_in)
                tel_col4.metric("Output Tokens", tot_tokens_out)
                
                st.subheader("🌳 Step-by-Step Nesting Spans Hierarchy")
                
                # Map child spans to parent spans for tree rendering
                child_map: Dict[Optional[str], List[Dict[str, Any]]] = {}
                for s in spans:
                    p_id = s["parent_span_id"]
                    if p_id not in child_map:
                        child_map[p_id] = []
                    child_map[p_id].append(s)
                
                # Check root spans (parent span ID is None or parent is not present in trace)
                all_span_ids = {s["span_id"] for s in spans}
                roots = [s for s in spans if s["parent_span_id"] is None or s["parent_span_id"] not in all_span_ids]
                
                # Recursive render function
                def render_tree_node(span, depth=0):
                    span_id = span["span_id"]
                    node_name = span["node"]
                    stype = span["type"]
                    duration = (span["end_ts"] - span["start_ts"]) if span["end_ts"] else 0
                    cost = span["cost_usd"] or 0.0
                    tokens = f"{span['tokens_in'] or 0} In / {span['tokens_out'] or 0} Out" if (span["tokens_in"] or span["tokens_out"]) else "N/A"
                    
                    title = f"**{node_name}** | Type: `{stype}` | ⏱️ {duration}ms | 💳 ${cost:.5f} | 🪙 {tokens}"
                    
                    css_class = "tree-node-node"
                    if stype == "tool_call":
                        css_class = "tree-node-tool"
                    elif stype == "llm_call":
                        css_class = "tree-node-llm"
                        
                    # Custom box display
                    st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
                    
                    with st.expander(title, expanded=True):
                        # Display Details inside expander
                        if span["tool_name"]:
                            st.markdown(f"**Tool Called:** `{span['tool_name']}`")
                        if span["tool_args"]:
                            st.markdown("**Tool Arguments:**")
                            st.json(span["tool_args"])
                        if span["output_summary"]:
                            st.markdown("**Output Summary:**")
                            st.text(span["output_summary"])
                        if span["error"]:
                            st.error(f"**Error Details:**\n{span['error']}")
                            
                        # Recurse children
                        children = child_map.get(span_id, [])
                        for child in children:
                            render_tree_node(child, depth + 1)
                            
                    st.markdown('</div>', unsafe_allow_html=True)
                
                for r in roots:
                    render_tree_node(r)

# ----------------------------------------------------
# View 4: Interactive Adapter Testing
# ----------------------------------------------------
elif navigation == "🤖 Interactive Adapter Testing":
    st.title("🤖 Interactive Adapter Testing")
    st.write("Execute custom tasks on target adapters and trace the evaluation live in the UI.")
    
    agent_options = list(ADAPTER_REGISTRY.keys())
    selected_agent = st.selectbox("Select Target Agent Adapter", agent_options)
    
    st.markdown("### Task Specifications")
    
    # Render input forms dynamically based on selected agent
    if selected_agent in ["drs", "drs_agent"]:
        question = st.text_input("❓ Enter Question", "What is Model Context Protocol?")
        keywords_raw = st.text_input("🔑 Required Keywords (comma-separated)", "mcp, server, client")
        difficulty = st.selectbox("Level of Difficulty", ["easy", "medium", "hard"], index=1)
        
        submit_task = st.button("🚀 Run Agent Evaluation")
        
        if submit_task:
            keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
            
            task_id = f"interactive_drs_{uuid.uuid4().hex[:6]}"
            task = TaskSpec(
                task_id=task_id,
                agent_target=selected_agent,
                input={"question": question},
                expected={
                    "required_keywords": keywords,
                    "must_have_citations": False
                },
                grading_strategy=["deterministic_keyword_match", "llm_judge_technical_accuracy"],
                difficulty=difficulty,
                tags=["interactive", "streamlit"]
            )
    else:
        # Blog writer agents
        topic = st.text_input("✍️ Blog Topic / Title", "Building APIs with Next.js")
        audience = st.text_input("👥 Target Audience", "Software Developers")
        keywords_raw = st.text_input("🔑 Required Keywords (comma-separated)", "Next.js, API, Route Handlers")
        min_sections = st.number_input("📚 Minimum Headers (#)", min_value=1, value=1)
        difficulty = st.selectbox("Level of Difficulty", ["easy", "medium", "hard"], index=1)
        
        submit_task = st.button("🚀 Run Agent Evaluation")
        
        if submit_task:
            keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
            
            task_id = f"interactive_blog_{uuid.uuid4().hex[:6]}"
            task = TaskSpec(
                task_id=task_id,
                agent_target=selected_agent,
                input={
                    "topic": topic,
                    "target_audience": audience,
                    "required_sections": []
                },
                expected={
                    "required_keywords": keywords,
                    "min_sections": int(min_sections),
                    "must_have_citations": False
                },
                grading_strategy=["deterministic_keyword_match", "llm_judge_technical_accuracy"],
                difficulty=difficulty,
                tags=["interactive", "streamlit"]
            )
            
    # Execution Block
    if 'submit_task' in locals() and submit_task:
        with st.spinner(f"Running agent '{selected_agent}' adapter wrapper..."):
            # Setup database schemas and save task
            save_task(
                task_id=task.task_id,
                agent_target=task.agent_target,
                input_data=task.input,
                expected=task.expected,
                grading_strategy=task.grading_strategy,
                difficulty=task.difficulty,
                tags=task.tags,
                db_path=DEFAULT_DB_PATH
            )
            
            adapter_class = ADAPTER_REGISTRY.get(selected_agent)
            adapter = adapter_class()
            
            run_id = f"run_interactive_ui_{int(time.time())}"
            trace_id = f"trace_{task.task_id}_{uuid.uuid4().hex[:6]}"
            
            task_start = time.time()
            
            try:
                # Execute agent adapter
                result = adapter.run(task)
            except Exception as e:
                st.error(f"Critical execution failure: {e}")
                result = AgentResult(
                    task_id=task.task_id,
                    final_output=f"UI Execution Error: {str(e)}",
                    trace=[],
                    total_cost_usd=0.0,
                    total_latency_ms=int((time.time() - task_start) * 1000)
                )
                
            # Align trace IDs
            for event in result.trace:
                event.trace_id = trace_id
            
            # Save traces to database
            trace_dicts = [e.model_dump() for e in result.trace]
            save_trace_events(trace_dicts, db_path=DEFAULT_DB_PATH)
            
            # Grade outcome
            grader = GraderEngine(task)
            grading_res = grader.grade(result)
            grading_res.trace_id = trace_id
            
            # Save grading results
            save_grading_result(
                task_id=task.task_id,
                trace_id=trace_id,
                deterministic=grading_res.deterministic,
                llm_judge=grading_res.llm_judge,
                trajectory=grading_res.trajectory,
                is_pass=grading_res.is_pass,
                db_path=DEFAULT_DB_PATH
            )
            
            # Save run metrics
            from src.core.schemas import MetricsReport
            report = MetricsReport(
                agent_name=selected_agent,
                agent_version="v1.0-ui-interactive",
                run_id=run_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                total_tasks=1,
                success_rate=1.0 if grading_res.is_pass else 0.0,
                average_cost_usd=result.total_cost_usd,
                average_latency_ms=result.total_latency_ms,
                failure_mode_counts={grading_res.trajectory["failure_mode"]: 1} if (not grading_res.is_pass and grading_res.trajectory.get("failure_mode")) else {},
                detailed_results=[grading_res]
            )
            
            save_run(
                run_id=run_id,
                agent_name=selected_agent,
                agent_version="v1.0-ui-interactive",
                timestamp=report.timestamp,
                metrics=report.model_dump(),
                db_path=DEFAULT_DB_PATH
            )
            
        st.success("Execution Complete!")
        
        # Display results
        r_col1, r_col2 = st.columns([2, 1])
        
        with r_col1:
            st.markdown("### Agent Final Output")
            st.text_area("Agent Output", str(result.final_output), height=400, disabled=True)
            
        with r_col2:
            st.markdown("### Evaluation Summary")
            is_passed_html = '<span class="pass-badge">PASSED</span>' if grading_res.is_pass else '<span class="fail-badge">FAILED</span>'
            st.markdown(f"**Overall Outcome:** {is_passed_html}", unsafe_allow_html=True)
            st.metric("Total Latency", f"{result.total_latency_ms} ms")
            st.metric("Total Cost", f"${result.total_cost_usd:.5f}")
            
            st.markdown("#### Deterministic Validations")
            st.json(grading_res.deterministic)
            
            if grading_res.llm_judge:
                st.markdown("#### LLM Judge Scores & Critique")
                st.json(grading_res.llm_judge)
                
        # Show trace hierarchy directly
        st.markdown("---")
        st.subheader("🔍 Execution Spans Hierarchy")
        if not result.trace:
            st.info("No traces were captured during execution.")
        else:
            spans = get_traces_for_run(trace_id, DEFAULT_DB_PATH)
            
            child_map = {}
            for s in spans:
                p_id = s["parent_span_id"]
                if p_id not in child_map:
                    child_map[p_id] = []
                child_map[p_id].append(s)
            
            all_span_ids = {s["span_id"] for s in spans}
            roots = [s for s in spans if s["parent_span_id"] is None or s["parent_span_id"] not in all_span_ids]
            
            def render_node(s):
                stype = s["type"]
                duration = (s["end_ts"] - s["start_ts"]) if s["end_ts"] else 0
                title = f"**{s['node']}** ({stype}) | {duration}ms | cost: ${s['cost_usd'] or 0:.5f}"
                
                css_class = "tree-node-node"
                if stype == "tool_call":
                    css_class = "tree-node-tool"
                elif stype == "llm_call":
                    css_class = "tree-node-llm"
                    
                st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
                with st.expander(title, expanded=True):
                    if s["tool_name"]:
                        st.write(f"Tool: `{s['tool_name']}`")
                    if s["tool_args"]:
                        st.json(s["tool_args"])
                    if s["output_summary"]:
                        st.text(s["output_summary"])
                    if s["error"]:
                        st.error(s["error"])
                    for child in child_map.get(s["span_id"], []):
                        render_node(child)
                st.markdown('</div>', unsafe_allow_html=True)
                
            for r in roots:
                render_node(r)

# ----------------------------------------------------
# View Suite Runner & Comparison
# ----------------------------------------------------
elif navigation == "🏃 Suite Runner & Comparison":
    st.title("🏃 Suite Runner & Comparison")
    st.write("Execute benchmark task suites and perform side-by-side comparative analysis of different runs.")

    tab_run, tab_compare = st.tabs(["🚀 Execute Task Suite", "🔄 Compare Evaluation Runs"])

    with tab_run:
        st.subheader("Configure and Run Task Suite")
        
        col1, col2 = st.columns(2)
        with col1:
            selected_agent = st.selectbox("Select Target Agent Adapter", list(ADAPTER_REGISTRY.keys()), key="suite_run_agent")
            
            # Auto-detect suites in data/suites
            suite_dir = Path("data/suites")
            suite_files = []
            if suite_dir.exists() and suite_dir.is_dir():
                suite_files = sorted(list(suite_dir.glob("*.yaml")) + list(suite_dir.glob("*.yml")) + list(suite_dir.glob("*.json")))
            suite_options = [str(f.relative_to(Path(".").absolute())) if f.is_relative_to(Path(".").absolute()) else str(f) for f in suite_files]
            suite_options.append("Enter custom path...")
            
            selected_suite_opt = st.selectbox("Select Task Suite File", suite_options, key="suite_run_file")
            if selected_suite_opt == "Enter custom path...":
                selected_suite = st.text_input("Enter custom suite file/dir path", "data/suites/drs_suite.yaml", key="suite_run_custom_file")
            else:
                selected_suite = selected_suite_opt
                
        with col2:
            agent_version = st.text_input("Agent Version Tag", "v1.0", key="suite_run_version")
            limit_checkbox = st.checkbox("Limit number of tasks to execute?", value=False, key="suite_run_limit_check")
            if limit_checkbox:
                task_limit = st.number_input("Task Limit", min_value=1, value=5, step=1, key="suite_run_limit_val")
            else:
                task_limit = None

        st.markdown("---")
        if st.button("🚀 Execute Suite Run", use_container_width=True, key="btn_run_suite"):
            if not selected_suite:
                st.error("Please specify a valid suite path.")
            elif not Path(selected_suite).exists():
                st.error(f"Suite path does not exist: {selected_suite}")
            else:
                with st.spinner(f"Running suite '{selected_suite}' against agent '{selected_agent}'... This performs execution and grading."):
                    from src.runner import execute_suite
                    try:
                        report = execute_suite(
                            suite_path=selected_suite,
                            agent_name=selected_agent,
                            agent_version=agent_version,
                            db_path=DEFAULT_DB_PATH,
                            limit=task_limit
                        )
                        st.success(f"Suite Run Completed successfully! Run ID: {report.run_id}")
                        
                        # Summary statistics
                        st.markdown("### Run Metrics Summary")
                        sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
                        sum_col1.metric("Total Tasks", report.total_tasks)
                        sum_col2.metric("Success Rate", f"{report.success_rate * 100:.1f}%")
                        sum_col3.metric("Avg Latency", f"{report.average_latency_ms:.0f} ms")
                        sum_col4.metric("Avg Cost (USD)", f"${report.average_cost_usd:.5f}")
                        
                        # Detailed results table
                        st.markdown("### Detailed Task Results")
                        task_res_data = []
                        for res in report.detailed_results:
                            task_res_data.append({
                                "Task ID": res.task_id,
                                "Trace ID": res.trace_id,
                                "Passed": "✅ Yes" if res.is_pass else "❌ No",
                                "Failure Mode": res.trajectory.get("failure_mode") or "None"
                            })
                        st.dataframe(pd.DataFrame(task_res_data), use_container_width=True)
                    except Exception as e:
                        st.error(f"Suite execution error: {str(e)}")

    with tab_compare:
        st.subheader("Side-by-Side Comparison of Runs")
        runs = get_all_runs(DEFAULT_DB_PATH)
        if len(runs) < 2:
            st.warning("Please execute at least two runs to perform a comparison. You currently have fewer than two runs recorded.")
        else:
            # Format run options
            run_options = {
                f"{r['run_id']} - Agent: {r['agent_name']} ({r['agent_version']}) - {r['timestamp'][:16].replace('T', ' ')}": r
                for r in runs
            }
            run_keys = list(run_options.keys())
            
            c_col1, c_col2 = st.columns(2)
            with c_col1:
                run_a_label = st.selectbox("Base Run (A)", run_keys, index=min(1, len(run_keys) - 1), key="compare_run_a")
                run_a = run_options[run_a_label]
            with c_col2:
                run_b_label = st.selectbox("Target Run (B)", run_keys, index=0, key="compare_run_b")
                run_b = run_options[run_b_label]
                
            if run_a["run_id"] == run_b["run_id"]:
                st.warning("You have selected the same run for both Base and Target. Select different runs for comparison.")
            
            # High-level metrics comparison
            metrics_a = run_a["metrics"]
            metrics_b = run_b["metrics"]
            
            st.markdown("---")
            st.subheader("📊 Comparison Summary")
            
            sr_a = metrics_a.get("success_rate", 0.0)
            sr_b = metrics_b.get("success_rate", 0.0)
            delta_sr = (sr_b - sr_a) * 100
            
            lat_a = metrics_a.get("average_latency_ms", 0.0)
            lat_b = metrics_b.get("average_latency_ms", 0.0)
            delta_lat = lat_b - lat_a
            
            cost_a = metrics_a.get("average_cost_usd", 0.0)
            cost_b = metrics_b.get("average_cost_usd", 0.0)
            delta_cost = cost_b - cost_a
            
            tasks_a = metrics_a.get("total_tasks", 0)
            tasks_b = metrics_b.get("total_tasks", 0)
            delta_tasks = tasks_b - tasks_a
            
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            m_col1.metric(
                label="Success Rate",
                value=f"{sr_b * 100:.1f}%",
                delta=f"{delta_sr:+.1f}%",
                delta_color="normal"
            )
            m_col2.metric(
                label="Avg Latency",
                value=f"{lat_b:.0f} ms",
                delta=f"{delta_lat:+.0f} ms",
                delta_color="inverse"
            )
            m_col3.metric(
                label="Avg Cost",
                value=f"${cost_b:.5f}",
                delta=f"${delta_cost:+.5f}",
                delta_color="inverse"
            )
            m_col4.metric(
                label="Total Tasks",
                value=tasks_b,
                delta=delta_tasks
            )
            
            # Task-by-task matrix comparison
            results_a = {res["task_id"]: res for res in metrics_a.get("detailed_results", [])}
            results_b = {res["task_id"]: res for res in metrics_b.get("detailed_results", [])}
            
            all_task_ids = sorted(list(set(results_a.keys()) | set(results_b.keys())))
            
            matrix_data = []
            for t_id in all_task_ids:
                res_a = results_a.get(t_id)
                res_b = results_b.get(t_id)
                
                status_a = "N/A" if res_a is None else ("✅ Pass" if res_a["is_pass"] else "❌ Fail")
                status_b = "N/A" if res_b is None else ("✅ Pass" if res_b["is_pass"] else "❌ Fail")
                
                if res_a is None:
                    comparison = "🆕 New in Target"
                elif res_b is None:
                    comparison = "🗑️ Removed in Target"
                elif res_a["is_pass"] and res_b["is_pass"]:
                    comparison = "✅ Passed (Both)"
                elif not res_a["is_pass"] and not res_b["is_pass"]:
                    comparison = "❌ Failed (Both)"
                elif not res_a["is_pass"] and res_b["is_pass"]:
                    comparison = "📈 Improved (Fail -> Pass)"
                else:
                    comparison = "📉 Regressed (Pass -> Fail)"
                    
                matrix_data.append({
                    "Task ID": t_id,
                    "Base Run A": status_a,
                    "Target Run B": status_b,
                    "Comparison State": comparison
                })
                
            st.markdown("### 📋 Task Comparison Matrix")
            st.dataframe(pd.DataFrame(matrix_data), use_container_width=True)
            
            st.markdown("---")
            st.subheader("🔍 Inspect Single Task Side-by-Side")
            selected_t_id = st.selectbox("Select Task to Inspect", all_task_ids, key="compare_task_select")
            
            if selected_t_id:
                res_a = results_a.get(selected_t_id)
                res_b = results_b.get(selected_t_id)
                
                det_col1, det_col2 = st.columns(2)
                
                with det_col1:
                    st.markdown("#### 🅰️ Base Run A")
                    if res_a is None:
                        st.info("This task was not executed in Base Run A.")
                    else:
                        is_pass_html_a = '<span class="pass-badge">PASSED</span>' if res_a["is_pass"] else '<span class="fail-badge">FAILED</span>'
                        st.markdown(f"**Outcome:** {is_pass_html_a}", unsafe_allow_html=True)
                        st.markdown(f"**Failure Mode:** {res_a['trajectory'].get('failure_mode') or 'None'}")
                        
                        spans_a = get_traces_for_run(res_a["trace_id"], DEFAULT_DB_PATH)
                        final_span_a = spans_a[-1] if spans_a else None
                        final_output_a = final_span_a["output_summary"] if final_span_a else "N/A"
                        
                        st.markdown("**Final Agent Output:**")
                        st.text_area("Output A", final_output_a, height=250, key="out_a", disabled=True)
                        
                        st.markdown("**Deterministic Validations:**")
                        st.json(res_a["deterministic"])
                        
                        if res_a["llm_judge"]:
                            st.markdown("**LLM Judge Feedback:**")
                            st.json(res_a["llm_judge"])
                            
                with det_col2:
                    st.markdown("#### 🅱️ Target Run B")
                    if res_b is None:
                        st.info("This task was not executed in Target Run B.")
                    else:
                        is_pass_html_b = '<span class="pass-badge">PASSED</span>' if res_b["is_pass"] else '<span class="fail-badge">FAILED</span>'
                        st.markdown(f"**Outcome:** {is_pass_html_b}", unsafe_allow_html=True)
                        st.markdown(f"**Failure Mode:** {res_b['trajectory'].get('failure_mode') or 'None'}")
                        
                        spans_b = get_traces_for_run(res_b["trace_id"], DEFAULT_DB_PATH)
                        final_span_b = spans_b[-1] if spans_b else None
                        final_output_b = final_span_b["output_summary"] if final_span_b else "N/A"
                        
                        st.markdown("**Final Agent Output:**")
                        st.text_area("Output B", final_output_b, height=250, key="out_b", disabled=True)
                        
                        st.markdown("**Deterministic Validations:**")
                        st.json(res_b["deterministic"])
                        
                        if res_b["llm_judge"]:
                            st.markdown("**LLM Judge Feedback:**")
                            st.json(res_b["llm_judge"])

# ----------------------------------------------------
# View 5: Failure Mode Analysis
# ----------------------------------------------------
elif navigation == "⚠️ Failure Mode Analysis":
    st.title("⚠️ Failure Mode Analysis")
    st.write("Diagnose and inspect agent trajectory failures (loops, premature endings, missed criteria).")
    
    runs = get_all_runs(DEFAULT_DB_PATH)
    if not runs:
        st.warning("No runs found in the database.")
    else:
        # Collect failure statistics from all runs
        failure_stats = {}
        failed_tasks_list = []
        
        for r in runs:
            detailed = get_grading_results_for_run(r["run_id"], DEFAULT_DB_PATH)
            for item in detailed:
                if not item["is_pass"]:
                    mode = item["trajectory"].get("failure_mode") or "missed_issue"
                    failure_stats[mode] = failure_stats.get(mode, 0) + 1
                    
                    failed_tasks_list.append({
                        "Run ID": r["run_id"],
                        "Agent": f"{r['agent_name']} ({r['agent_version']})",
                        "Task ID": item["task_id"],
                        "Trace ID": item["trace_id"],
                        "Failure Mode": mode,
                        "Grading Details": item
                    })
                    
        if not failed_tasks_list:
            st.success("🎉 No failed runs or trajectory problems found in history!")
        else:
            # Render chart of failure modes
            st.subheader("📊 Failure Mode Distribution")
            df_fail = pd.DataFrame(list(failure_stats.items()), columns=["Failure Mode", "Frequencies"])
            
            st.bar_chart(df_fail.set_index("Failure Mode"))
            
            st.subheader("📋 Failed Tasks Breakdown")
            df_table = pd.DataFrame([
                {
                    "Run ID": x["Run ID"],
                    "Agent": x["Agent"],
                    "Task ID": x["Task ID"],
                    "Failure Mode": x["Failure Mode"]
                } for x in failed_tasks_list
            ])
            st.dataframe(df_table, use_container_width=True)
            
            st.markdown("---")
            st.subheader("🔍 Failure Diagnostics & Logs")
            
            selected_failed_task_label = st.selectbox(
                "Select a failed task to audit", 
                [f"{x['Task ID']} - Mode: {x['Failure Mode']} ({x['Agent']})" for x in failed_tasks_list]
            )
            
            # Find the record
            task_id_match = selected_failed_task_label.split(" - Mode:")[0].strip()
            task_record = next((x for x in failed_tasks_list if x["Task ID"] == task_id_match), None)
            
            if task_record:
                details = task_record["Grading Details"]
                
                st.markdown(f"#### Diagnosis for Task `{task_record['Task ID']}`")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Deterministic Failures**")
                    st.json(details["deterministic"])
                with col2:
                    st.markdown("**Trajectory Failure Diagnostics**")
                    st.json(details["trajectory"])
                    
                st.markdown("**Trace Event Diagnostics**")
                spans = get_traces_for_run(task_record["Trace ID"], DEFAULT_DB_PATH)
                
                # Check for errors in spans
                error_spans = [s for s in spans if s["error"]]
                if error_spans:
                    st.error("Captured Exceptions inside execution spans:")
                    for idx, err in enumerate(error_spans):
                        st.markdown(f"**Error in Node: `{err['node']}` (Span ID: `{err['span_id']}`)**")
                        st.code(err["error"], language="python")
                else:
                    st.info("No structural exceptions were thrown during execution; failure is due to semantic check failures or timeout flags.")

# ----------------------------------------------------
# View 6: Judge Calibration
# ----------------------------------------------------
elif navigation == "🎯 Judge Calibration":
    st.title("🎯 Judge Calibration")
    st.write("Compare the subjective ratings generated by LLM-as-a-Judge against human annotated ground truths.")
    
    # Path to manual calibration JSON
    calibration_path = Path("data/calibration_human_labels.json")
    
    # If file doesn't exist, create samples
    if not calibration_path.exists():
        calibration_path.parent.mkdir(parents=True, exist_ok=True)
        sample_data = [
            {
                "task_id": "blog_tech_001",
                "topic": "Model Context Protocol",
                "agent_output": "# Draft: Model Context Protocol\n\nThis is an intro section to Model Context Protocol.\nHere we describe client and server communication.\nCitations: [1] MCP standard.",
                "human_scores": {"clarity": 4, "accuracy": 5, "completeness": 3}
            },
            {
                "task_id": "blog_tech_002",
                "topic": "LangGraph vs LangChain",
                "agent_output": "LangGraph uses graph state loops. LangChain is linear chains. It is simple but powerful.",
                "human_scores": {"clarity": 3, "accuracy": 4, "completeness": 2}
            }
        ]
        with open(calibration_path, "w", encoding="utf-8") as f:
            json.dump(sample_data, f, indent=2)
            
    # Load calibration labels
    with open(calibration_path, "r", encoding="utf-8") as f:
        datasets = json.load(f)
        
    st.markdown(f"Running LLM Judge Evaluation on `{len(datasets)}` labeled dataset records...")
    
    # Run evaluation live or fallback
    mae_metrics = {"clarity": 0.0, "accuracy": 0.0, "completeness": 0.0}
    calibration_records = []
    
    with st.spinner("Executing LLM-as-a-Judge grading to match annotations..."):
        for item in datasets:
            task_id = item.get("task_id")
            topic = item.get("topic") or item.get("question")
            output_text = item.get("agent_output")
            human = item.get("human_scores", {})
            
            task = TaskSpec(
                task_id=task_id,
                agent_target="mock",
                input={"question": topic},
                expected={},
                grading_strategy=[]
            )
            
            result = AgentResult(
                task_id=task_id,
                final_output=output_text,
                trace=[],
                total_cost_usd=0.0,
                total_latency_ms=0
            )
            
            score = evaluate_subjective_quality(task, result)
            
            if score:
                clarity_delta = abs(score.clarity - human.get("clarity", 0))
                accuracy_delta = abs(score.accuracy - human.get("accuracy", 0))
                completeness_delta = abs(score.completeness - human.get("completeness", 0))
                
                mae_metrics["clarity"] += clarity_delta
                mae_metrics["accuracy"] += accuracy_delta
                mae_metrics["completeness"] += completeness_delta
                
                calibration_records.append({
                    "Task ID": task_id,
                    "Topic": topic,
                    "Clarity (AI)": score.clarity,
                    "Clarity (Human)": human.get("clarity", 0),
                    "Clarity Delta": clarity_delta,
                    "Accuracy (AI)": score.accuracy,
                    "Accuracy (Human)": human.get("accuracy", 0),
                    "Accuracy Delta": accuracy_delta,
                    "Completeness (AI)": score.completeness,
                    "Completeness (Human)": human.get("completeness", 0),
                    "Completeness Delta": completeness_delta
                })
                
    if calibration_records:
        df_cal = pd.DataFrame(calibration_records)
        
        # Calculate MAE values
        st.subheader("📈 Mean Absolute Error (MAE) Summary")
        mae_col1, mae_col2, mae_col3 = st.columns(3)
        
        mae_clarity = mae_metrics["clarity"] / len(calibration_records)
        mae_accuracy = mae_metrics["accuracy"] / len(calibration_records)
        mae_completeness = mae_metrics["completeness"] / len(calibration_records)
        
        mae_col1.metric("Clarity MAE", f"{mae_clarity:.3f}")
        mae_col2.metric("Accuracy MAE", f"{mae_accuracy:.3f}")
        mae_col3.metric("Completeness MAE", f"{mae_completeness:.3f}")
        
        st.subheader("📊 Detailed Score Comparison")
        st.dataframe(df_cal, use_container_width=True)
        
        # Plot calibration differences
        st.subheader("🎯 Visual Deviation Chart")
        
        # Melt dataframe for easier plotting in Streamlit
        plot_data = []
        for r in calibration_records:
            plot_data.append({"Task": r["Task ID"], "Metric": "Clarity (AI)", "Score": r["Clarity (AI)"]})
            plot_data.append({"Task": r["Task ID"], "Metric": "Clarity (Human)", "Score": r["Clarity (Human)"]})
            plot_data.append({"Task": r["Task ID"], "Metric": "Accuracy (AI)", "Score": r["Accuracy (AI)"]})
            plot_data.append({"Task": r["Task ID"], "Metric": "Accuracy (Human)", "Score": r["Accuracy (Human)"]})
            plot_data.append({"Task": r["Task ID"], "Metric": "Completeness (AI)", "Score": r["Completeness (AI)"]})
            plot_data.append({"Task": r["Task ID"], "Metric": "Completeness (Human)", "Score": r["Completeness (Human)"]})
            
        st.bar_chart(pd.DataFrame(plot_data).pivot(index="Task", columns="Metric", values="Score"))
    else:
        st.error("Could not run Judge Calibration. Please verify API keys or configure manual calibration data.")
