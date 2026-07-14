import pytest
import tempfile
import json
import yaml
from pathlib import Path
from src.core.schemas import TaskSpec, TraceEvent, AgentResult, GradingResult
from src.storage.db import init_db, save_task, get_connection, save_run, save_trace_events, save_grading_result, get_baseline, set_baseline
from src.loader.suite_loader import load_task_file, load_task_suite

@pytest.fixture
def temp_db():
    """Fixture that provides a path to a temporary database and initializes it."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
    init_db(db_path)
    yield db_path
    
    # Cleanup after test
    if db_path.exists():
        db_path.unlink()

def test_pydantic_schemas():
    """Verify core Pydantic models can be instantiated and validated."""
    # Test TaskSpec
    task = TaskSpec(
        task_id="test_001",
        agent_target="dummy_agent",
        input={"query": "hello"},
        expected={"response": "hi"},
        grading_strategy=["deterministic"],
        difficulty="easy",
        tags=["unit-test"]
    )
    assert task.task_id == "test_001"
    assert task.difficulty == "easy"

    # Test TraceEvent
    event = TraceEvent(
        trace_id="trace_abc",
        span_id="span_123",
        node="test_node",
        type="tool_call",
        start_ts=1000,
        end_ts=2000,
        tool_name="dummy_tool",
        tool_args={"arg1": "val1"},
        output_summary="success"
    )
    assert event.span_id == "span_123"
    assert event.tool_name == "dummy_tool"

def test_database_operations(temp_db):
    """Verify table creation, inserts, and retrievals in SQLite."""
    # 1. Save and verify Task
    save_task(
        task_id="task_db_01",
        agent_target="agent_x",
        input_data={"param": 42},
        expected={"result": "ok"},
        grading_strategy=["deterministic"],
        difficulty="medium",
        tags=["db-test"],
        db_path=temp_db
    )
    
    conn = get_connection(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE task_id = 'task_db_01'")
    row = cursor.fetchone()
    assert row is not None
    assert row["agent_target"] == "agent_x"
    assert json.loads(row["input"]) == {"param": 42}
    
    # 2. Save and verify Run
    save_run(
        run_id="run_001",
        agent_name="agent_x",
        agent_version="v1.0",
        timestamp="2026-07-14T12:00:00Z",
        metrics={"score": 0.9},
        db_path=temp_db
    )
    cursor.execute("SELECT * FROM runs WHERE run_id = 'run_001'")
    row = cursor.fetchone()
    assert row is not None
    assert row["agent_version"] == "v1.0"
    assert json.loads(row["metrics"]) == {"score": 0.9}

    # 3. Save and verify Trace Events
    trace_event = {
        "span_id": "span_01",
        "trace_id": "trace_01",
        "node": "orchestrator",
        "type": "agent_step",
        "start_ts": 1710000000000,
        "end_ts": 1710000001000,
        "tool_name": None,
        "tool_args": None,
        "output_summary": "stepped",
        "error": None
    }
    save_trace_events([trace_event], db_path=temp_db)
    cursor.execute("SELECT * FROM traces WHERE span_id = 'span_01'")
    row = cursor.fetchone()
    assert row is not None
    assert row["trace_id"] == "trace_01"
    assert row["output_summary"] == "stepped"

    # 4. Save and verify Grading Result
    save_grading_result(
        task_id="task_db_01",
        trace_id="trace_01",
        deterministic={"correct": True},
        llm_judge={"grade": 5, "comment": "Excellent"},
        trajectory={"loops": 0},
        is_pass=True,
        db_path=temp_db
    )
    cursor.execute("SELECT * FROM grading_results WHERE task_id = 'task_db_01' AND trace_id = 'trace_01'")
    row = cursor.fetchone()
    assert row is not None
    assert row["is_pass"] == 1
    assert json.loads(row["llm_judge"]) == {"grade": 5, "comment": "Excellent"}

    # 5. Save and verify Baseline
    set_baseline(agent_name="agent_x", run_id="run_001", version_tag="v1.0", db_path=temp_db)
    baseline = get_baseline("agent_x", db_path=temp_db)
    assert baseline is not None
    assert baseline["run_id"] == "run_001"
    assert baseline["version_tag"] == "v1.0"
    assert baseline["metrics"] == {"score": 0.9}

    conn.close()

def test_loader_yaml_and_json(temp_db):
    """Verify suite loader parses files and directories correctly, and saves to database."""
    # Prepare dummy files
    yaml_content = {
        "tasks": [
            {
                "task_id": "yaml_task_1",
                "agent_target": "agent_alpha",
                "input": {"prompt": "write a function"},
                "expected": {"has_code": True},
                "grading_strategy": ["deterministic"],
                "difficulty": "hard",
                "tags": ["coding"]
            }
        ]
    }
    
    json_content = [
        {
            "task_id": "json_task_1",
            "agent_target": "agent_beta",
            "input": {"prompt": "summarize this"},
            "expected": {"length_less_than": 100},
            "grading_strategy": ["llm_judge"],
            "difficulty": "easy",
            "tags": ["nlp"]
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        yaml_file = tmp_path / "tasks.yaml"
        json_file = tmp_path / "tasks.json"

        with open(yaml_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(yaml_content, f)

        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(json_content, f)

        # 1. Test single file load (YAML)
        yaml_tasks = load_task_file(yaml_file)
        assert len(yaml_tasks) == 1
        assert yaml_tasks[0].task_id == "yaml_task_1"
        assert yaml_tasks[0].difficulty == "hard"

        # 2. Test single file load (JSON)
        json_tasks = load_task_file(json_file)
        assert len(json_tasks) == 1
        assert json_tasks[0].task_id == "json_task_1"
        assert json_tasks[0].tags == ["nlp"]

        # 3. Test loading full suite directory and saving to database
        suite_tasks = load_task_suite(tmp_path, save_to_db=True, db_path=temp_db)
        assert len(suite_tasks) == 2

        # Verify insertion in database
        conn = get_connection(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) as count FROM tasks")
        row = cursor.fetchone()
        assert row["count"] == 2
        
        cursor.execute("SELECT * FROM tasks WHERE task_id = 'yaml_task_1'")
        row_yaml = cursor.fetchone()
        assert row_yaml["agent_target"] == "agent_alpha"
        conn.close()
