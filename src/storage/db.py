import sqlite3
import json
import os
from typing import Optional, List, Dict, Any
from pathlib import Path

DEFAULT_DB_PATH = Path("data/harness.db")

def get_connection(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Returns a connection to the SQLite database, creating parent directories if needed."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: Path = DEFAULT_DB_PATH):
    """Initializes the database schema if tables do not exist."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Table: tasks
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY,
        agent_target TEXT NOT NULL,
        input TEXT NOT NULL,          -- JSON string
        expected TEXT NOT NULL,       -- JSON string
        grading_strategy TEXT NOT NULL, -- JSON string array
        difficulty TEXT DEFAULT 'medium',
        tags TEXT DEFAULT '[]'        -- JSON string array
    );
    """)

    # Table: runs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        agent_name TEXT NOT NULL,
        agent_version TEXT NOT NULL,
        timestamp TEXT NOT NULL,      -- ISO-8601 string
        metrics TEXT                  -- JSON string of MetricsReport summary statistics
    );
    """)

    # Table: traces (Spans)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS traces (
        span_id TEXT PRIMARY KEY,
        trace_id TEXT NOT NULL,
        parent_span_id TEXT,
        node TEXT NOT NULL,
        type TEXT NOT NULL,           -- tool_call, llm_call, state_transition
        start_ts INTEGER NOT NULL,    -- epoch millisecond
        end_ts INTEGER,               -- epoch millisecond
        tokens_in INTEGER,
        tokens_out INTEGER,
        cost_usd REAL,
        tool_name TEXT,
        tool_args TEXT,               -- JSON string
        output_summary TEXT,
        error TEXT,
        FOREIGN KEY (parent_span_id) REFERENCES traces(span_id) ON DELETE CASCADE
    );
    """)

    # Indexing on trace_id for fast queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_traces_trace_id ON traces(trace_id);")

    # Table: grading_results
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS grading_results (
        task_id TEXT NOT NULL,
        trace_id TEXT NOT NULL,
        deterministic TEXT NOT NULL,  -- JSON string
        llm_judge TEXT,               -- JSON string
        trajectory TEXT NOT NULL,     -- JSON string
        is_pass INTEGER NOT NULL,     -- 0 or 1
        PRIMARY KEY (task_id, trace_id)
    );
    """)

    # Table: baselines
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS baselines (
        agent_name TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        version_tag TEXT NOT NULL,
        FOREIGN KEY (run_id) REFERENCES runs(run_id)
    );
    """)

    conn.commit()
    conn.close()

def save_task(task_id: str, agent_target: str, input_data: Dict[str, Any], expected: Dict[str, Any], grading_strategy: List[str], difficulty: str = "medium", tags: List[str] = None, db_path: Path = DEFAULT_DB_PATH):
    """Saves or updates a task specification in the DB."""
    if tags is None:
        tags = []
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO tasks (task_id, agent_target, input, expected, grading_strategy, difficulty, tags)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """, (
        task_id,
        agent_target,
        json.dumps(input_data),
        json.dumps(expected),
        json.dumps(grading_strategy),
        difficulty,
        json.dumps(tags)
    ))
    conn.commit()
    conn.close()

def save_run(run_id: str, agent_name: str, agent_version: str, timestamp: str, metrics: Optional[Dict[str, Any]] = None, db_path: Path = DEFAULT_DB_PATH):
    """Saves a suite run record."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    metrics_json = json.dumps(metrics) if metrics else None
    cursor.execute("""
    INSERT OR REPLACE INTO runs (run_id, agent_name, agent_version, timestamp, metrics)
    VALUES (?, ?, ?, ?, ?);
    """, (run_id, agent_name, agent_version, timestamp, metrics_json))
    conn.commit()
    conn.close()

def save_trace_events(events: List[Dict[str, Any]], db_path: Path = DEFAULT_DB_PATH):
    """Saves a batch of trace events / spans."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    for e in events:
        tool_args_json = json.dumps(e.get("tool_args")) if e.get("tool_args") else None
        cursor.execute("""
        INSERT OR REPLACE INTO traces (
            span_id, trace_id, parent_span_id, node, type, start_ts, end_ts, 
            tokens_in, tokens_out, cost_usd, tool_name, tool_args, output_summary, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            e["span_id"], e["trace_id"], e.get("parent_span_id"), e["node"], e["type"],
            e["start_ts"], e.get("end_ts"), e.get("tokens_in"), e.get("tokens_out"),
            e.get("cost_usd"), e.get("tool_name"), tool_args_json, e.get("output_summary"), e.get("error")
        ))
    conn.commit()
    conn.close()

def save_grading_result(task_id: str, trace_id: str, deterministic: Dict[str, Any], llm_judge: Optional[Dict[str, Any]], trajectory: Dict[str, Any], is_pass: bool, db_path: Path = DEFAULT_DB_PATH):
    """Saves evaluation and grading outcomes."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO grading_results (task_id, trace_id, deterministic, llm_judge, trajectory, is_pass)
    VALUES (?, ?, ?, ?, ?, ?);
    """, (
        task_id,
        trace_id,
        json.dumps(deterministic),
        json.dumps(llm_judge) if llm_judge else None,
        json.dumps(trajectory),
        1 if is_pass else 0
    ))
    conn.commit()
    conn.close()

def get_baseline(agent_name: str, db_path: Path = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    """Gets the baseline run information for a given agent."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    SELECT b.agent_name, b.run_id, b.version_tag, r.metrics
    FROM baselines b
    JOIN runs r ON b.run_id = r.run_id
    WHERE b.agent_name = ?;
    """, (agent_name,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "agent_name": row["agent_name"],
            "run_id": row["run_id"],
            "version_tag": row["version_tag"],
            "metrics": json.loads(row["metrics"]) if row["metrics"] else None
        }
    return None

def set_baseline(agent_name: str, run_id: str, version_tag: str, db_path: Path = DEFAULT_DB_PATH):
    """Establishes a baseline run for an agent."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO baselines (agent_name, run_id, version_tag)
    VALUES (?, ?, ?);
    """, (agent_name, run_id, version_tag))
    conn.commit()
    conn.close()
