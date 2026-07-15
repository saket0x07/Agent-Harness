import pytest
import tempfile
import yaml
from pathlib import Path
from click.testing import CliRunner
from main import cli
from src.storage.db import get_connection

@pytest.fixture
def temp_suite():
    """Fixture providing a temporary task suite YAML file with 2 tasks for tests."""
    suite_data = {
        "tasks": [
            {
                "task_id": "test_mcp_001",
                "agent_target": "blog_researcher_writer_agent",
                "input": {
                    "topic": "Model Context Protocol",
                    "required_sections": ["Intro", "Outlook"],
                    "mock_behavior": "success"
                },
                "expected": {
                    "required_keywords": ["model context protocol", "client", "server"]
                },
                "grading_strategy": ["deterministic_keyword_match"],
                "difficulty": "medium",
                "tags": ["tech"]
            },
            {
                "task_id": "test_mcp_002",
                "agent_target": "blog_researcher_writer_agent",
                "input": {
                    "topic": "Model Context Protocol",
                    "mock_behavior": "infinite_loop"
                },
                "expected": {
                    "required_keywords": ["complete_match_impossible_kw"]
                },
                "grading_strategy": ["deterministic_keyword_match"],
                "difficulty": "high",
                "tags": ["tech"]
            }
        ]
    }
    
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False, encoding="utf-8") as f:
        yaml.safe_dump(suite_data, f)
        suite_path = Path(f.name)
        
    yield suite_path
    
    if suite_path.exists():
        suite_path.unlink()

@pytest.fixture
def temp_db_path():
    """Fixture providing a temporary DB path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()

def test_cli_run_command(temp_suite, temp_db_path, monkeypatch):
    """Verify that running the main.py CLI run command executes tasks, grades them, and saves output to SQLite."""
    from src.runner import ADAPTER_REGISTRY
    from src.adapters.mock_agent import MockAgentAdapter
    monkeypatch.setitem(ADAPTER_REGISTRY, "blog_researcher_writer_agent", MockAgentAdapter)

    runner = CliRunner()
    
    # Run command
    result = runner.invoke(cli, [
        "run",
        "--suite", str(temp_suite),
        "--agent", "blog_researcher_writer_agent",
        "--version", "test_v1.0",
        "--db", str(temp_db_path)
    ])
    
    assert result.exit_code == 0
    assert "🚀 Starting Suite Run:" in result.output
    assert "Suite Run Outcomes:" in result.output
    assert "Success Rate: 50.0%" in result.output  # 1 passed, 1 failed (due to missing required loop keyword)
    
    # Verify DB contents
    conn = get_connection(temp_db_path)
    cursor = conn.cursor()
    
    # Verify tasks table populated
    cursor.execute("SELECT count(*) as count FROM tasks")
    assert cursor.fetchone()["count"] == 2
    
    # Verify runs table populated
    cursor.execute("SELECT * FROM runs")
    run_row = cursor.fetchone()
    assert run_row is not None
    assert run_row["agent_name"] == "blog_researcher_writer_agent"
    assert run_row["agent_version"] == "test_v1.0"
    
    # Verify traces table populated (3 spans for task 1 success + 5 spans for task 2 loop = 8 spans total)
    cursor.execute("SELECT count(*) as count FROM traces")
    assert cursor.fetchone()["count"] == 8
    
    # Verify grading_results table populated
    cursor.execute("SELECT * FROM grading_results WHERE task_id = 'test_mcp_001'")
    grading_row_1 = cursor.fetchone()
    assert grading_row_1 is not None
    assert grading_row_1["is_pass"] == 1  # Passed keyword match
    
    cursor.execute("SELECT * FROM grading_results WHERE task_id = 'test_mcp_002'")
    grading_row_2 = cursor.fetchone()
    assert grading_row_2 is not None
    assert grading_row_2["is_pass"] == 0  # Failed keyword match
    
    conn.close()
