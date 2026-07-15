import re
from typing import Dict, Any, List
from src.core.schemas import TaskSpec, AgentResult, GradingResult
from src.grading.llm_judge import evaluate_subjective_quality

class GraderEngine:
    """Orchestrates deterministic validation, trajectory pattern auditing, and subjective LLM grading."""
    
    def __init__(self, task: TaskSpec):
        self.task = task

    def grade(self, result: AgentResult) -> GradingResult:
        """Evaluates the agent result against task specifications and returns a normalized GradingResult."""
        final_output = str(result.final_output)
        
        # 1. Deterministic Checks
        deterministic_checks: Dict[str, bool] = {}
        
        # Keyword checks
        required_keywords = self.task.expected.get("required_keywords", [])
        keyword_results = {}
        all_kws_present = True
        for kw in required_keywords:
            present = kw.lower() in final_output.lower()
            keyword_results[f"keyword_{kw}_present"] = present
            if not present:
                all_kws_present = False
        deterministic_checks["required_keywords_pass"] = all_kws_present
        
        # Min sections checks
        min_sections = self.task.expected.get("min_sections")
        if min_sections is not None:
            # Match lines starting with optional whitespace and # symbols (at least one) followed by a space
            headings = re.findall(r"(?:^|\n)\s*#{1,6}\s+.+", final_output)
            sections_pass = len(headings) >= min_sections
            deterministic_checks["min_sections_pass"] = sections_pass
            deterministic_checks["sections_count"] = len(headings)
            
        # Must have citations checks
        must_have_citations = self.task.expected.get("must_have_citations", False)
        if must_have_citations:
            # Check for bracketed footnotes [1] or markdown links containing http/https urls
            has_brackets = bool(re.search(r"\[\d+\]", final_output))
            has_urls = bool(re.search(r"https?://[^\s)]+", final_output))
            citations_pass = has_brackets or has_urls
            deterministic_checks["citations_pass"] = citations_pass
            
        # 2. Trajectory Auditing (Failure Mode Classification)
        trajectory_checks: Dict[str, Any] = {
            "total_spans": len(result.trace),
            "infinite_loop": False,
            "premature_termination": False,
            "failure_mode": None
        }
        
        # Infinite Loop Check
        # Check if the exact same tool name + tool arguments occurs 3 or more times consecutively
        consecutive_tool_count = 1
        last_tool_signature = None
        
        for event in result.trace:
            if event.type == "tool_call" and event.tool_name:
                # Stringify tool name and args to make a hashable/comparable signature
                args_str = str(event.tool_args) if event.tool_args else ""
                signature = (event.tool_name, args_str)
                
                if signature == last_tool_signature:
                    consecutive_tool_count += 1
                else:
                    consecutive_tool_count = 1
                    last_tool_signature = signature
                
                if consecutive_tool_count >= 3:
                    trajectory_checks["infinite_loop"] = True
                    trajectory_checks["failure_mode"] = "infinite_loop"
                    break

        # Premature Termination Check
        # Defined as ending with very little output (< 40 characters) without executing any tools or LLM calls
        if len(final_output.strip()) < 40:
            # Check if there are no deep tool interactions or LLM writer calls
            has_tools_or_calls = any(event.type in ["tool_call", "llm_call"] for event in result.trace)
            behavior_indicates_failure = "failed" in final_output.lower() or "timeout" in final_output.lower()
            if not has_tools_or_calls or behavior_indicates_failure:
                trajectory_checks["premature_termination"] = True
                trajectory_checks["failure_mode"] = "premature_termination"
                
        # 3. subjective LLM-as-a-Judge grading
        has_llm_judge = any(s.startswith("llm_judge") for s in self.task.grading_strategy)
        llm_judge_score = evaluate_subjective_quality(self.task, result) if has_llm_judge else None
        
        # 4. Compute overall Pass status
        # Must pass all deterministic checks and have no detected trajectory loop/termination failures
        det_pass = all(v for k, v in deterministic_checks.items() if k.endswith("_pass"))
        no_traj_failures = not trajectory_checks["infinite_loop"] and not trajectory_checks["premature_termination"]
        
        # Also, if we have an active LLM judge, we might enforce a minimum score (e.g. >= 3/5 on dimensions)
        # But for MVP, pass/fail is determined by deterministic + trajectory checks
        is_pass = det_pass and no_traj_failures
        
        # If trajectory checks found a failure but deterministic checks also failed, prioritize trajectory classification
        if not no_traj_failures:
            # failure_mode is set inside trajectory checks
            pass
        elif not det_pass:
            trajectory_checks["failure_mode"] = "missed_issue" # Standard tag for missing expected goals
            
        return GradingResult(
            task_id=self.task.task_id,
            trace_id=result.trace[0].trace_id if result.trace else "trace_none",
            deterministic=deterministic_checks,
            llm_judge=llm_judge_score.model_dump() if llm_judge_score else None,
            trajectory=trajectory_checks,
            is_pass=is_pass
        )
