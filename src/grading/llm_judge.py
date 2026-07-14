import os
import json
import logging
from typing import Optional
from pydantic import BaseModel, Field

from src.core.schemas import TaskSpec, AgentResult

logger = logging.getLogger(__name__)

class JudgeScore(BaseModel):
    """Pydantic model representing structured ratings from the LLM-as-a-Judge evaluation."""
    clarity: int = Field(description="Clarity rating of writing from 0 (poor) to 5 (excellent)")
    accuracy: int = Field(description="Technical accuracy rating from 0 to 5")
    completeness: int = Field(description="Completeness and rubric satisfaction rating from 0 to 5")
    critique: str = Field(description="Free-text narrative explanation of the grading scores and advice")

def evaluate_subjective_quality(task: TaskSpec, result: AgentResult) -> Optional[JudgeScore]:
    """Uses Gemini API to evaluate subjective content quality. Falls back to mock scores if API key is missing."""
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        # Fallback offline mode
        return JudgeScore(
            clarity=4,
            accuracy=4,
            completeness=4,
            critique="[Offline Fallback Mode] GEMINI_API_KEY not found. Emitted placeholder scores."
        )
        
    try:
        from google import genai
        from google.genai import types
        
        # Initialize client (uses GEMINI_API_KEY from environment automatically)
        client = genai.Client()
        
        prompt = f"""
You are an expert technical editor and content reviewer. Your job is to grade the output of a content writer agent.

### Task Topic:
{task.input.get("topic", "Default Topic")}

### Target Audience:
{task.input.get("target_audience", "General Public")}

### Expected Sections:
{', '.join(task.input.get("required_sections", []))}

### Agent Output Content:
---
{result.final_output}
---

Please evaluate the content quality strictly against these rubrics and score clarity, accuracy, and completeness on a scale of 0 to 5.
Provide a clear critique explaining your scoring.
"""
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=JudgeScore,
                temperature=0.1
            ),
        )
        
        # Parse the JSON string directly back to Pydantic object
        if response.text:
            return JudgeScore.model_validate_json(response.text)
        else:
            raise ValueError("Empty response received from Gemini API.")
            
    except Exception as e:
        logger.warning(f"Failed to execute LLM Judge query: {e}. Emitting failure fallback score.")
        return JudgeScore(
            clarity=1,
            accuracy=1,
            completeness=1,
            critique=f"[API Error Fallback Mode] Query to Gemini model failed with exception: {str(e)}"
        )
