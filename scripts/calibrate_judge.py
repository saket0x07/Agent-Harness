import sys
import os
import json
import argparse
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.core.schemas import TaskSpec, AgentResult
from src.grading.llm_judge import evaluate_subjective_quality

def create_sample_calibration_data(dest_path: Path):
    """Generates a sample manual human annotation reference file."""
    sample_data = [
        {
            "task_id": "blog_tech_001",
            "topic": "Model Context Protocol",
            "agent_output": "# Draft: Model Context Protocol\n\nThis is an intro section to Model Context Protocol.\nHere we describe client and server communication.\nCitations: [1] MCP standard.",
            "human_scores": {
                "clarity": 4,
                "accuracy": 5,
                "completeness": 3
            }
        },
        {
            "task_id": "blog_tech_002",
            "topic": "LangGraph vs LangChain",
            "agent_output": "LangGraph uses graph state loops. LangChain is linear chains. It is simple but powerful.",
            "human_scores": {
                "clarity": 3,
                "accuracy": 4,
                "completeness": 2
            }
        }
    ]
    with open(dest_path, "w", encoding="utf-8") as f:
        json.dump(sample_data, f, indent=2)
    print(f"Created sample human labels at: {dest_path}")

def main():
    parser = argparse.ArgumentParser(description="Calibrate LLM Judge scores against manual human labels.")
    parser.add_argument("--labels", "-l", default="data/calibration_human_labels.json", help="Path to manual labels file")
    args = parser.parse_args()
    
    labels_path = Path(args.labels)
    if not labels_path.exists():
        labels_path.parent.mkdir(parents=True, exist_ok=True)
        create_sample_calibration_data(labels_path)

    with open(labels_path, "r", encoding="utf-8") as f:
        datasets = json.load(f)

    print(f"📊 Starting Calibration of LLM Judge on {len(datasets)} records...")
    
    total_records = 0
    mae_metrics = {"clarity": 0.0, "accuracy": 0.0, "completeness": 0.0}
    
    print("\n" + "=" * 80)
    print(f"{'Task ID':<15} | {'Metric':<12} | {'LLM Score':<10} | {'Human Score':<12} | {'Delta':<6}")
    print("=" * 80)

    for item in datasets:
        task_id = item.get("task_id")
        topic = item.get("topic")
        output_text = item.get("agent_output")
        human = item.get("human_scores", {})
        
        # Create TaskSpec and AgentResult wrappers
        task = TaskSpec(
            task_id=task_id,
            agent_target="mock",
            input={"topic": topic},
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
        
        # Run judge (either live Gemini call or offline fallback)
        score = evaluate_subjective_quality(task, result)
        if not score:
            print(f"⚠️ Skipped {task_id}: Judge returned None.")
            continue
            
        total_records += 1
        
        for key in mae_metrics.keys():
            llm_val = getattr(score, key, 0)
            human_val = human.get(key, 0)
            delta = abs(llm_val - human_val)
            mae_metrics[key] += delta
            print(f"{task_id:<15} | {key:<12} | {llm_val:<10} | {human_val:<12} | {delta:<6.1f}")
            
    print("=" * 80)
    
    if total_records > 0:
        print("\n📈 Mean Absolute Error (MAE) Calibration Summary:")
        for k, v in mae_metrics.items():
            avg_mae = v / total_records
            print(f"  - {k.capitalize()}: {avg_mae:.3f} MAE")
    else:
        print("❌ No records successfully processed.")

if __name__ == "__main__":
    main()
