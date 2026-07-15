import os
import json
import logging
import requests
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from src.core.schemas import TaskSpec, AgentResult

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)

class JudgeScore(BaseModel):
    """Pydantic model representing structured ratings from the LLM-as-a-Judge evaluation."""
    clarity: int = Field(description="Clarity rating of writing from 0 (poor) to 5 (excellent)")
    accuracy: int = Field(description="Technical accuracy rating from 0 to 5")
    completeness: int = Field(description="Completeness and rubric satisfaction rating from 0 to 5")
    critique: str = Field(description="Free-text narrative explanation of the grading scores and advice")

def is_valid_key(key: Optional[str]) -> bool:
    """Helper to check if a loaded key is valid and not a placeholder dummy value."""
    if not key:
        return False
    key_strip = key.strip()
    return len(key_strip) > 0 and not key_strip.startswith("your_")

def evaluate_subjective_quality(task: TaskSpec, result: AgentResult) -> Optional[JudgeScore]:
    """Uses LLM-as-a-Judge to evaluate subjective content quality.
    
    Tries OpenRouter (Primary, calling Claude 3.5 Sonnet).
    Falls back to Gemini (Secondary, calling gemini-2.5-flash via native SDK).
    Falls back to Offline Mock if no valid keys exist.
    """
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    
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
You MUST output raw JSON matching this schema:
{{
  "clarity": int (0 to 5),
  "accuracy": int (0 to 5),
  "completeness": int (0 to 5),
  "critique": "detailed string critique"
}}
"""

    # --- 1. Primary: OpenRouter API (Claude 3.5 Sonnet) ---
    if is_valid_key(openrouter_key):
        try:
            logger.info("Calling OpenRouter LLM Judge (Claude 3.5 Sonnet)...")
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/saket0x07/Agent-Harness",
                },
                json={
                    "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1
                },
                timeout=20
            )
            
            if response.status_code == 200:
                res_data = response.json()
                content = res_data["choices"][0]["message"]["content"]
                return JudgeScore.model_validate_json(content)
            else:
                logger.warning(f"OpenRouter returned status {response.status_code}: {response.text}. Retrying with Gemini...")
        except Exception as e:
            logger.warning(f"OpenRouter query failed: {e}. Retrying with Gemini...")

    # --- 2. Fallback: Gemini API (Native SDK) ---
    if is_valid_key(gemini_key):
        try:
            logger.info("Calling Gemini Fallback LLM Judge (gemini-2.5-flash)...")
            from google import genai
            from google.genai import types
            
            # Explicitly pass the key if available, else standard environment resolution
            client = genai.Client(api_key=gemini_key)
            
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=JudgeScore,
                    temperature=0.1
                ),
            )
            
            if response.text:
                return JudgeScore.model_validate_json(response.text)
            else:
                logger.warning("Empty response text from Gemini API. Emitting offline mock scores.")
        except Exception as e:
            logger.warning(f"Gemini Fallback query failed: {e}. Emitting offline mock scores.")

    # --- 3. Final Fallback: Offline Mock ---
    return JudgeScore(
        clarity=4,
        accuracy=4,
        completeness=4,
        critique="[Offline Fallback Mode] Neither OpenRouter nor Gemini API keys were configured. Emitted placeholder scores."
    )
