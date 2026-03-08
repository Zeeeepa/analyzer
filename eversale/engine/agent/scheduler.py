"""
Task Scheduler - Runs prompts on schedule (cron-like)
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from rich.console import Console
from rich.table import Table


console = Console()


class TaskScheduler:
    """
    Manages scheduled prompts that run autonomously

    Example schedules:
    - "daily at 9am" -> 0 9 * * *
    - "every monday at 2pm" -> 0 14 * * 1
    - "every friday at 10am" -> 0 10 * * 5
    - "every hour" -> 0 * * * *
    """

    def __init__(self, agent):
        self.agent = agent
        self.scheduler = AsyncIOScheduler()
        self.tasks = {}
        self.config_path = Path("config/schedule.yaml")
        self._load_tasks()

    def _load_tasks(self):
        """Load scheduled tasks from config"""

        if not self.config_path.exists():
            logger.info("No schedule config found, starting with empty schedule")
            self._save_tasks()
            return

        with open(self.config_path) as f:
            config = yaml.safe_load(f)

        scheduled_tasks = config.get("scheduled_tasks", [])

        for task in scheduled_tasks:
            if task.get("enabled", True):
                self.tasks[task["name"]] = task

        logger.info(f"Loaded {len(self.tasks)} scheduled tasks")

    def _save_tasks(self):
        """Save scheduled tasks to config"""

        config = {
            "scheduled_tasks": list(self.tasks.values())
        }

        self.config_path.parent.mkdir(exist_ok=True)

        with open(self.config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

        logger.debug("Saved schedule config")

    def parse_schedule(self, schedule_str: str) -> str:
        """
        Convert natural language to cron expression

        Examples:
        - "daily at 9am" -> "0 9 * * *"
        - "every monday at 2pm" -> "0 14 * * 1"
        - "every friday at 10am" -> "0 10 * * 5"
        - "every hour" -> "0 * * * *"
        - "every 30 minutes" -> "*/30 * * * *"
        """

        schedule_str = schedule_str.lower().strip()

        # Daily patterns
        if "daily" in schedule_str or "every day" in schedule_str:
            # Extract time
            time = self._extract_time(schedule_str)
            return f"{time['minute']} {time['hour']} * * *"

        # Weekly patterns
        days_map = {
            "monday": "1", "mon": "1",
            "tuesday": "2", "tue": "2",
            "wednesday": "3", "wed": "3",
            "thursday": "4", "thu": "4",
            "friday": "5", "fri": "5",
            "saturday": "6", "sat": "6",
            "sunday": "0", "sun": "0",
        }

        for day_name, day_num in days_map.items():
            if day_name in schedule_str:
                time = self._extract_time(schedule_str)
                return f"{time['minute']} {time['hour']} * * {day_num}"

        # Hourly
        if "every hour" in schedule_str or "hourly" in schedule_str:
            return "0 * * * *"

        # Every N minutes
        if "every" in schedule_str and "minute" in schedule_str:
            import re
            match = re.search(r'every\s+(\d+)\s+minute', schedule_str)
            if match:
                minutes = match.group(1)
                return f"*/{minutes} * * * *"

        # Default - try to parse as cron directly
        logger.warning(f"Could not parse schedule: {schedule_str}, using as-is")
        return schedule_str

    def _extract_time(self, schedule_str: str) -> Dict[str, int]:
        """Extract hour and minute from schedule string"""

        import re

        # Look for time patterns like "9am", "2pm", "14:30"
        time_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?'
        match = re.search(time_pattern, schedule_str)

        if match:
            hour = int(match.group(1))
            minute = int(match.group(2)) if match.group(2) else 0
            meridian = match.group(3)

            # Convert to 24-hour
            if meridian == "pm" and hour != 12:
                hour += 12
            elif meridian == "am" and hour == 12:
                hour = 0

            return {"hour": hour, "minute": minute}

        # Default to 9am
        return {"hour": 9, "minute": 0}

    def add_task(self, name: str, cron: str, prompt: str):
        """Add a scheduled task"""

        task = {
            "name": name,
            "schedule": cron,
            "prompt": prompt,
            "enabled": True
        }

        self.tasks[name] = task
        self._save_tasks()

        # Add to scheduler if running
        if self.scheduler.running:
            self._schedule_task(task)

        logger.info(f"Added scheduled task: {name}")

    def remove_task(self, name: str):
        """Remove a scheduled task"""

        if name in self.tasks:
            del self.tasks[name]
            self._save_tasks()

            # Remove from scheduler
            if self.scheduler.running:
                try:
                    self.scheduler.remove_job(name)
                except Exception:
                    pass

            logger.info(f"Removed scheduled task: {name}")

    def _schedule_task(self, task: Dict):
        """Add task to APScheduler"""

        cron_parts = task["schedule"].split()

        if len(cron_parts) != 5:
            logger.error(f"Invalid cron expression: {task['schedule']}")
            return

        minute, hour, day, month, day_of_week = cron_parts

        trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week
        )

        self.scheduler.add_job(
            self._execute_task,
            trigger=trigger,
            args=[task],
            id=task["name"],
            name=task["name"],
            replace_existing=True
        )

        logger.info(f"Scheduled: {task['name']} at {task['schedule']}")

    async def _execute_task(self, task: Dict):
        """Execute a scheduled task"""

        logger.info(f"🔔 Running scheduled task: {task['name']}")
        console.print(f"\n[bold yellow]🔔 Scheduled task:[/bold yellow] {task['name']}")
        console.print(f"[dim]{task['prompt']}[/dim]\n")

        try:
            # Run the prompt
            result = await self.agent.run(task['prompt'])

            # Log result
            logger.info(f"✓ Completed: {task['name']}")
            console.print(f"[green]✓[/green] Task complete: {task['name']}\n")

            # Could save result to database here

        except Exception as e:
            logger.error(f"Error executing scheduled task {task['name']}: {e}")
            console.print(f"[red]✗ Error in {task['name']}: {e}[/red]\n")

    async def start(self):
        """Start the scheduler"""

        # Schedule all tasks
        for task in self.tasks.values():
            if task.get("enabled", True):
                self._schedule_task(task)

        self.scheduler.start()
        logger.info("Scheduler started")

        console.print(f"[green]✓[/green] Scheduler running with {len(self.tasks)} tasks\n")

    async def stop(self):
        """Stop the scheduler"""

        self.scheduler.shutdown()
        logger.info("Scheduler stopped")

    def list_tasks(self):
        """Display all scheduled tasks"""

        if not self.tasks:
            console.print("[yellow]No scheduled tasks[/yellow]\n")
            return

        table = Table(title="Scheduled Tasks")
        table.add_column("ID", style="cyan")
        table.add_column("Schedule", style="magenta")
        table.add_column("Prompt", style="white")
        table.add_column("Status", style="green")

        for name, task in self.tasks.items():
            status = "✓ Enabled" if task.get("enabled", True) else "✗ Disabled"
            prompt_preview = task["prompt"][:50] + "..." if len(task["prompt"]) > 50 else task["prompt"]

            table.add_row(
                name,
                task["schedule"],
                prompt_preview,
                status
            )

        console.print(table)
        console.print()

    def show_status(self):
        """Show scheduler status"""

        console.print(f"[bold]Scheduler Status[/bold]")
        console.print(f"Running: {'Yes' if self.scheduler.running else 'No'}")
        console.print(f"Tasks: {len(self.tasks)}")

        if self.scheduler.running:
            console.print(f"\n[bold]Next runs:[/bold]")

            jobs = self.scheduler.get_jobs()
            for job in jobs:
                next_run = job.next_run_time
                console.print(f"  • {job.name}: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

        console.print()
