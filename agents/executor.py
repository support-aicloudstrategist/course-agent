"""
Executor Agent - Runs the extracted instructions step by step.

Handles:
- Shell command execution with output capture
- File creation and modification
- Download of resources
- Verification steps
- Safety checks before destructive operations
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from config import COMMAND_TIMEOUT, SAFE_MODE, REPORTS_DIR


class ExecutionResult:
    """Result of executing a single step."""

    def __init__(self, step_number: int, title: str):
        self.step_number = step_number
        self.title = title
        self.status = "pending"  # pending, running, success, failed, skipped
        self.commands_run = []
        self.outputs = []
        self.errors = []
        self.files_created = []
        self.files_modified = []
        self.start_time = None
        self.end_time = None
        self.skipped_reason = ""

    def to_dict(self) -> dict:
        return {
            "step_number": self.step_number,
            "title": self.title,
            "status": self.status,
            "commands_run": self.commands_run,
            "outputs": self.outputs,
            "errors": self.errors,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "duration_seconds": (
                (self.end_time - self.start_time).total_seconds()
                if self.start_time and self.end_time
                else 0
            ),
            "skipped_reason": self.skipped_reason,
        }


class Executor:
    """Executes training instructions step by step."""

    def __init__(self, working_dir: str = None, confirm_callback=None):
        self.working_dir = working_dir or os.getcwd()
        self.results: list[ExecutionResult] = []
        self.confirm_callback = confirm_callback  # async callable for user confirmation
        self.env = os.environ.copy()
        self.log_file = REPORTS_DIR / f"execution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    def _log(self, message: str):
        """Log a message to both console and log file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}"
        print(line)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    async def execute_all(self, instructions: dict) -> list[dict]:
        """Execute all steps from parsed instructions."""
        steps = instructions.get("steps", [])
        if not steps:
            self._log("No steps found to execute.")
            return []

        self._log(f"Starting execution of {len(steps)} steps...")
        self._log(f"Course: {instructions.get('course_title', 'Unknown')}")
        self._log(f"Working directory: {self.working_dir}")
        self._log("")

        for step in steps:
            result = await self._execute_step(step)
            self.results.append(result)

            if result.status == "failed":
                self._log(f"Step {step['step_number']} FAILED. Continuing to next step...")

        return [r.to_dict() for r in self.results]

    async def _execute_step(self, step: dict) -> ExecutionResult:
        """Execute a single step."""
        result = ExecutionResult(step.get("step_number", 0), step.get("title", "Unknown"))
        result.start_time = datetime.now()
        result.status = "running"

        step_type = step.get("type", "command")
        self._log(f"\n{'='*50}")
        self._log(f"STEP {result.step_number}: {result.title}")
        self._log(f"Type: {step_type}")
        self._log(f"{'='*50}")

        if step.get("description"):
            self._log(f"Description: {step['description']}")

        # Check if human intervention is needed
        if step.get("requires_human"):
            result.status = "skipped"
            result.skipped_reason = step.get(
                "human_reason", "This step requires manual human intervention"
            )
            self._log(f"SKIPPED (requires human): {result.skipped_reason}")
            result.end_time = datetime.now()
            return result

        # Safety check
        if SAFE_MODE and self.confirm_callback:
            from agents.instruction_parser import InstructionParser
            parser = InstructionParser()
            safety = parser.classify_step_safety(step)
            if not safety["safe"]:
                reasons = ", ".join(safety["reasons"])
                self._log(f"SAFETY CHECK: {reasons}")
                confirmed = await self.confirm_callback(
                    f"Step {result.step_number}: {result.title}\n"
                    f"Safety concerns: {reasons}\n"
                    f"Commands: {step.get('commands', [])}\n"
                    f"Proceed? (yes/no)"
                )
                if not confirmed:
                    result.status = "skipped"
                    result.skipped_reason = "User declined after safety check"
                    result.end_time = datetime.now()
                    return result

        try:
            if step_type == "command":
                await self._run_commands(step, result)
            elif step_type == "file_create":
                self._create_file(step, result)
            elif step_type == "file_edit":
                self._edit_file(step, result)
            elif step_type == "download":
                self._download_resource(step, result)
            elif step_type == "config":
                await self._run_commands(step, result)
            elif step_type == "verify":
                await self._run_verification(step, result)
            elif step_type == "manual":
                result.status = "skipped"
                result.skipped_reason = step.get("description", "Manual step")
                self._log(f"SKIPPED (manual): {result.skipped_reason}")
            else:
                # Default: try to run commands if present
                if step.get("commands"):
                    await self._run_commands(step, result)
                else:
                    result.status = "skipped"
                    result.skipped_reason = f"Unknown step type: {step_type}"

            if result.status == "running":
                result.status = "success"

        except Exception as e:
            result.status = "failed"
            result.errors.append(str(e))
            self._log(f"ERROR: {e}")

        result.end_time = datetime.now()
        duration = (result.end_time - result.start_time).total_seconds()
        self._log(f"Result: {result.status} ({duration:.1f}s)")
        return result

    async def _run_commands(self, step: dict, result: ExecutionResult):
        """Run shell commands from a step."""
        commands = step.get("commands", [])
        if not commands:
            return

        for cmd in commands:
            self._log(f"  $ {cmd}")
            result.commands_run.append(cmd)

            try:
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=COMMAND_TIMEOUT,
                    cwd=self.working_dir,
                    env=self.env,
                )
                output = proc.stdout.strip()
                error = proc.stderr.strip()

                if output:
                    result.outputs.append(output)
                    # Log first few lines
                    for line in output.split("\n")[:10]:
                        self._log(f"    {line}")
                    if len(output.split("\n")) > 10:
                        self._log(f"    ... ({len(output.split(chr(10)))} total lines)")

                if error:
                    result.errors.append(error)
                    for line in error.split("\n")[:5]:
                        self._log(f"    [stderr] {line}")

                if proc.returncode != 0:
                    self._log(f"    Exit code: {proc.returncode}")
                    result.status = "failed"
                    return

            except subprocess.TimeoutExpired:
                result.errors.append(f"Command timed out after {COMMAND_TIMEOUT}s: {cmd}")
                result.status = "failed"
                self._log(f"    TIMEOUT after {COMMAND_TIMEOUT}s")
                return

    def _create_file(self, step: dict, result: ExecutionResult):
        """Create a file with specified content."""
        file_path = step.get("file_path", "")
        content = step.get("file_content", "")

        if not file_path:
            result.status = "failed"
            result.errors.append("No file_path specified for file creation")
            return

        # Make path absolute if relative
        if not os.path.isabs(file_path):
            file_path = os.path.join(self.working_dir, file_path)

        # Create parent directories
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        self._log(f"  Creating file: {file_path}")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        result.files_created.append(file_path)
        self._log(f"  File created ({len(content)} bytes)")

    def _edit_file(self, step: dict, result: ExecutionResult):
        """Edit an existing file."""
        file_path = step.get("file_path", "")
        content = step.get("file_content", "")

        if not file_path:
            result.status = "failed"
            result.errors.append("No file_path specified for file edit")
            return

        if not os.path.isabs(file_path):
            file_path = os.path.join(self.working_dir, file_path)

        if not os.path.exists(file_path):
            self._log(f"  File not found, creating: {file_path}")
            self._create_file(step, result)
            return

        self._log(f"  Editing file: {file_path}")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        result.files_modified.append(file_path)

    def _download_resource(self, step: dict, result: ExecutionResult):
        """Download a resource from a URL."""
        commands = step.get("commands", [])
        # If there are wget/curl commands, run them
        if commands:
            import asyncio
            asyncio.get_event_loop().run_until_complete(self._run_commands(step, result))
            return

        # Otherwise try direct URL download
        links = step.get("links", [])
        for link in links:
            url = link.get("href", "")
            if url:
                self._log(f"  Downloading: {url}")
                try:
                    resp = requests.get(url, timeout=60)
                    filename = url.split("/")[-1] or "downloaded_file"
                    filepath = os.path.join(self.working_dir, filename)
                    with open(filepath, "wb") as f:
                        f.write(resp.content)
                    result.files_created.append(filepath)
                    self._log(f"  Downloaded to: {filepath}")
                except Exception as e:
                    result.errors.append(f"Download failed: {e}")

    async def _run_verification(self, step: dict, result: ExecutionResult):
        """Run verification commands and check expected output."""
        await self._run_commands(step, result)

        expected = step.get("expected_output", "")
        if expected and result.outputs:
            last_output = result.outputs[-1]
            if expected.lower() in last_output.lower():
                self._log(f"  Verification PASSED: found expected output")
            else:
                self._log(f"  Verification WARNING: expected output not found")
                self._log(f"    Expected: {expected[:100]}")
                self._log(f"    Got: {last_output[:100]}")

    def get_execution_summary(self) -> dict:
        """Get a summary of all execution results."""
        total = len(self.results)
        success = sum(1 for r in self.results if r.status == "success")
        failed = sum(1 for r in self.results if r.status == "failed")
        skipped = sum(1 for r in self.results if r.status == "skipped")

        return {
            "total_steps": total,
            "successful": success,
            "failed": failed,
            "skipped": skipped,
            "results": [r.to_dict() for r in self.results],
        }
