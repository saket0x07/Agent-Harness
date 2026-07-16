import pytest
import requests
from unittest.mock import patch, MagicMock

from src.core.schemas import TaskSpec
from src.adapters.drs_adapter import DRSAdapter

def test_drs_adapter_success():
    """Test DRSAdapter handles successful API responses and records appropriate spans."""
    task = TaskSpec(
        task_id="drs_test_001",
        agent_target="drs",
        input={"question": "What are candidate skills?"},
        expected={"required_keywords": ["python"]},
        grading_strategy=["deterministic_keyword_match"]
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "question": "What are candidate skills?",
        "answer": "The candidate is skilled in Python and Machine Learning."
    }

    adapter = DRSAdapter()
    
    with patch("requests.post", return_value=mock_response) as mock_post:
        result = adapter.run(task)
        
        # Verify request parameters
        mock_post.assert_called_once_with("http://localhost:8000/ask", json={"question": "What are candidate skills?"}, timeout=60)
        
        # Verify results
        assert result.task_id == "drs_test_001"
        assert "skilled in Python" in result.final_output
        assert result.total_latency_ms >= 0
        assert result.total_cost_usd > 0
        
        # Verify trace collection
        trace_nodes = [span.node for span in result.trace]
        assert "drs_api_request" in trace_nodes
        assert "retriever" in trace_nodes
        assert "llm_generation" in trace_nodes

        # Verify token estimations
        llm_span = next(span for span in result.trace if span.node == "llm_generation")
        assert llm_span.tokens_in == len("What are candidate skills?") // 4 + 150
        assert llm_span.tokens_out == len(result.final_output) // 4
        assert llm_span.cost_usd is not None

def test_drs_adapter_api_error():
    """Test DRSAdapter handles API status code errors gracefully."""
    task = TaskSpec(
        task_id="drs_test_002",
        agent_target="drs",
        input={"query": "Test error query"},
        expected={},
        grading_strategy=[]
    )

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    adapter = DRSAdapter()

    with patch("requests.post", return_value=mock_response) as mock_post:
        result = adapter.run(task)
        
        assert "API Error: DRS API responded with status 500" in result.final_output
        
        # Verify error logged in trace span
        api_span = next(span for span in result.trace if span.node == "drs_api_request")
        assert "500" in api_span.error

def test_drs_adapter_connection_failure():
    """Test DRSAdapter handles server connection timeout/failure gracefully."""
    task = TaskSpec(
        task_id="drs_test_003",
        agent_target="drs",
        input={"topic": "Test connection failure"},
        expected={},
        grading_strategy=[]
    )

    adapter = DRSAdapter()

    with patch("requests.post", side_effect=requests.exceptions.ConnectionError("Connection refused")):
        result = adapter.run(task)
        
        assert "Connection Failure" in result.final_output
        
        api_span = next(span for span in result.trace if span.node == "drs_api_request")
        assert "Connection refused" in api_span.error

def test_drs_adapter_missing_question():
    """Test DRSAdapter raises ValueError when task input lacks all valid question keys."""
    task = TaskSpec(
        task_id="drs_test_004",
        agent_target="drs",
        input={"some_other_field": "unrelated"},
        expected={},
        grading_strategy=[]
    )

    adapter = DRSAdapter()
    with pytest.raises(ValueError, match="Task input is missing 'question'"):
        adapter.run(task)
