
import yaml
from pathlib import Path
from loguru import logger
from ..tool_registry import tool

@tool(
    id="schedule_task",
    name="Schedule Task",
    description="Schedule a task to run periodically (e.g., daily, hourly).",
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Unique name for the scheduled task"
            },
            "schedule": {
                "type": "string",
                "description": "Schedule expression (e.g., 'daily at 9am', 'every hour', '0 9 * * *')"
            },
            "prompt": {
                "type": "string",
                "description": "The prompt/task to execute"
            }
        },
        "required": ["name", "schedule", "prompt"]
    },
    permissions=["write"],
    category="system"
)
async def schedule_task(name: str, schedule: str, prompt: str):
    """
    Add a task to the schedule configuration.
    """
    config_path = Path("config/schedule.yaml")
    
    # Load existing config
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load schedule config: {e}")
            config = {}
    else:
        config = {}
        
    scheduled_tasks = config.get("scheduled_tasks", [])
    
    # Check if task with same name exists
    for task in scheduled_tasks:
        if task["name"] == name:
            # Update existing
            task["schedule"] = schedule
            task["prompt"] = prompt
            task["enabled"] = True
            break
    else:
        # Add new task
        scheduled_tasks.append({
            "name": name,
            "schedule": schedule,
            "prompt": prompt,
            "enabled": True
        })
        
    config["scheduled_tasks"] = scheduled_tasks
    
    # Save config
    try:
        config_path.parent.mkdir(exist_ok=True)
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        return f"Task '{name}' scheduled: {schedule}"
    except Exception as e:
        return f"Failed to save schedule: {e}"
