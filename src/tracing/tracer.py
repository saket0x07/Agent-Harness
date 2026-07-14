import time
import uuid
import contextlib
import threading
import traceback
from typing import Optional, Any, Dict, List
from src.core.schemas import TraceEvent

class _TraceStorage(threading.local):
    """Thread-local storage container for tracking nested span frames."""
    def __init__(self):
        self.current_trace_id: Optional[str] = None
        self.active_spans: List[str] = []  # Stack of span IDs to resolve parent-child context
        self.events: List[TraceEvent] = []

# Instantiate the thread-local storage object
_storage = _TraceStorage()

class TraceCollector:
    """Thread-safe context manager to collect trace events for a single agent execution run."""
    def __init__(self, trace_id: Optional[str] = None):
        self.trace_id = trace_id or str(uuid.uuid4())
        self.prev_trace_id: Optional[str] = None
        self.prev_events: List[TraceEvent] = []
        self.prev_active_spans: List[str] = []

    def __enter__(self):
        self.prev_trace_id = _storage.current_trace_id
        self.prev_events = _storage.events
        self.prev_active_spans = _storage.active_spans

        _storage.current_trace_id = self.trace_id
        _storage.events = []
        _storage.active_spans = []
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.collected_events = _storage.events
        _storage.current_trace_id = self.prev_trace_id
        
        # If we are a nested context, restore parent's events
        if self.prev_trace_id is not None:
            _storage.events = self.prev_events
            _storage.active_spans = self.prev_active_spans
        else:
            # Top-level context exits. Keep _storage.events so static get_events() works,
            # but clear active_spans stack.
            _storage.active_spans = []

    @staticmethod
    def get_trace_id() -> Optional[str]:
        """Returns the active trace ID for the current thread context."""
        return _storage.current_trace_id

    @staticmethod
    def get_events() -> List[TraceEvent]:
        """Retrieves all traces collected during the current session."""
        return _storage.events

    @staticmethod
    def add_event(event: TraceEvent):
        """Adds a verified trace event to the session queue."""
        if _storage.current_trace_id:
            _storage.events.append(event)

@contextlib.contextmanager
def trace_span(node: str, type: str, tool_name: Optional[str] = None, tool_args: Optional[Dict[str, Any]] = None):
    """Context manager to trace a specific step/span inside an agent execution block.
    
    Automatically records start/end timestamps, nests caller spans, captures errors, 
    and appends metrics to the TraceCollector.
    
    Usage:
        with trace_span("writer_node", "llm_call") as span_data:
            response = client.generate(...)
            span_data["tokens_in"] = 150
            span_data["tokens_out"] = 80
            span_data["cost_usd"] = 0.00045
            span_data["output_summary"] = response.text[:100]
    """
    trace_id = TraceCollector.get_trace_id()
    if not trace_id:
        # If tracer is not active in this thread context, yield an empty dict and bypass collection
        yield {}
        return

    span_id = str(uuid.uuid4())
    parent_span_id = _storage.active_spans[-1] if _storage.active_spans else None
    
    # Push onto execution stack
    _storage.active_spans.append(span_id)
    start_ts = int(time.time() * 1000)

    span_data: Dict[str, Any] = {
        "tokens_in": None,
        "tokens_out": None,
        "cost_usd": None,
        "output_summary": None
    }

    error_msg = None
    try:
        yield span_data
    except Exception as e:
        # Capture error trace details for regression diagnostic analysis
        error_msg = f"{e.__class__.__name__}: {str(e)}\n" + "".join(traceback.format_list(traceback.extract_tb(e.__traceback__)))
        raise e
    finally:
        end_ts = int(time.time() * 1000)
        # Pop from execution stack
        if _storage.active_spans and _storage.active_spans[-1] == span_id:
            _storage.active_spans.pop()

        event = TraceEvent(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            node=node,
            type=type,
            start_ts=start_ts,
            end_ts=end_ts,
            tokens_in=span_data.get("tokens_in"),
            tokens_out=span_data.get("tokens_out"),
            cost_usd=span_data.get("cost_usd"),
            tool_name=tool_name,
            tool_args=tool_args,
            output_summary=span_data.get("output_summary"),
            error=error_msg
        )
        TraceCollector.add_event(event)
