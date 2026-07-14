import json
import yaml
from pathlib import Path
from typing import List, Union
from src.core.schemas import TaskSpec
from src.storage.db import save_task

def load_task_file(file_path: Union[str, Path]) -> List[TaskSpec]:
    """Loads tasks from a single JSON or YAML file and validates them.
    
    The file can contain either a single task dictionary or a list of task dictionaries.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Task file not found at: {path}")

    ext = path.suffix.lower()
    
    with open(path, "r", encoding="utf-8") as f:
        if ext in [".yaml", ".yml"]:
            data = yaml.safe_load(f)
        elif ext == ".json":
            data = json.load(f)
        else:
            raise ValueError(f"Unsupported file format: {ext}. Only .json, .yaml, and .yml are supported.")

    if not data:
        return []

    # Normalize to a list of tasks
    if isinstance(data, dict):
        # Could be a single task, or a container dict like {"tasks": [...]}
        if "tasks" in data and isinstance(data["tasks"], list):
            raw_tasks = data["tasks"]
        else:
            raw_tasks = [data]
    elif isinstance(data, list):
        raw_tasks = data
    else:
        raise ValueError(f"Invalid task data structure in file {path}. Must be a list or a dictionary.")

    tasks = []
    for idx, raw_task in enumerate(raw_tasks):
        try:
            # Pydantic validation
            task = TaskSpec(**raw_task)
            tasks.append(task)
        except Exception as e:
            raise ValueError(f"Validation failed for task at index {idx} in {path.name}: {e}")

    return tasks

def load_task_suite(suite_path: Union[str, Path], save_to_db: bool = False, db_path: Path = None) -> List[TaskSpec]:
    """Loads all tasks from a file or all matching JSON/YAML files in a directory.
    
    If save_to_db is True, stores the loaded tasks in SQLite.
    """
    path = Path(suite_path)
    all_tasks = []

    if path.is_file():
        all_tasks.extend(load_task_file(path))
    elif path.is_dir():
        # Iterate over all JSON and YAML files
        for file in path.iterdir():
            if file.suffix.lower() in [".json", ".yaml", ".yml"]:
                all_tasks.extend(load_task_file(file))
    else:
        raise FileNotFoundError(f"Suite path not found: {path}")

    if save_to_db:
        for task in all_tasks:
            # Use custom db_path if provided, otherwise db.py uses default
            save_kwargs = {}
            if db_path:
                save_kwargs["db_path"] = db_path
            save_task(
                task_id=task.task_id,
                agent_target=task.agent_target,
                input_data=task.input,
                expected=task.expected,
                grading_strategy=task.grading_strategy,
                difficulty=task.difficulty,
                tags=task.tags,
                **save_kwargs
            )

    return all_tasks
