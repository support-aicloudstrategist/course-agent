"""
Reporter Agent - Generates detailed reports of what was done and what the user needs to do.

Produces:
1. A human-readable summary report
2. Detailed execution log
3. List of manual steps the user must complete
4. Cleanup instructions
"""
import json
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic

from config import get_api_key, AI_MODEL, MAX_TOKENS, REPORTS_DIR


REPORT_SYSTEM_PROMPT = """You are a training course completion reporter. Given execution results from an automated training course setup, generate a clear, detailed report for the user.

The report should be in Markdown format with these sections:

1. **Course Summary** - What course was completed, platform, key topics
2. **What Was Done** - Detailed list of every action taken, with specifics (exact commands, files created, configs applied)
3. **Execution Results** - Success/failure status of each step, with any error details
4. **What You Need To Do** - Clear list of manual steps the user must complete themselves (e.g., GUI actions, payments, logins, approvals)
5. **Verification Checklist** - How to verify everything is working correctly
6. **Important Notes** - Warnings, gotchas, things to be aware of
7. **Cleanup Instructions** - How to tear down resources when done (to avoid costs)
8. **Resources & Links** - Relevant documentation, repos, dashboards

Be specific and detailed. Include exact commands, file paths, URLs, and configuration values.
For manual steps, explain exactly what the user needs to click/do, step by step.
"""


class Reporter:
    """Generates detailed reports of course completion."""

    def __init__(self):
        api_key = get_api_key()
        self.client = Anthropic(api_key=api_key) if api_key else None

    def generate_report(
        self,
        instructions: dict,
        execution_results: dict,
        course_content_summary: str = "",
    ) -> str:
        """Generate a comprehensive report using AI."""
        if self.client:
            return self._generate_ai_report(instructions, execution_results, course_content_summary)
        else:
            return self._generate_basic_report(instructions, execution_results)

    def _generate_ai_report(
        self, instructions: dict, execution_results: dict, course_content_summary: str
    ) -> str:
        """Generate a detailed report using Claude AI."""
        prompt = f"""Generate a detailed completion report for this training course setup.

COURSE INSTRUCTIONS (parsed):
{json.dumps(instructions, indent=2, default=str)[:50000]}

EXECUTION RESULTS:
{json.dumps(execution_results, indent=2, default=str)[:30000]}

COURSE CONTENT SUMMARY:
{course_content_summary[:20000]}

Generate the report now."""

        response = self.client.messages.create(
            model=AI_MODEL,
            max_tokens=MAX_TOKENS,
            system=REPORT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _generate_basic_report(self, instructions: dict, execution_results: dict) -> str:
        """Generate a basic report without AI (fallback)."""
        lines = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines.append(f"# Course Completion Report")
        lines.append(f"**Generated:** {now}")
        lines.append(f"**Course:** {instructions.get('course_title', 'Unknown')}")
        lines.append(f"**Platform:** {instructions.get('course_platform', 'Unknown')}")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append(instructions.get("summary", "No summary available."))
        lines.append("")

        # Execution results
        summary = execution_results
        lines.append("## Execution Results")
        lines.append(f"- **Total Steps:** {summary.get('total_steps', 0)}")
        lines.append(f"- **Successful:** {summary.get('successful', 0)}")
        lines.append(f"- **Failed:** {summary.get('failed', 0)}")
        lines.append(f"- **Skipped:** {summary.get('skipped', 0)}")
        lines.append("")

        # What was done
        lines.append("## What Was Done")
        for result in summary.get("results", []):
            status_icon = {"success": "OK", "failed": "FAIL", "skipped": "SKIP"}.get(
                result["status"], "?"
            )
            lines.append(f"### Step {result['step_number']}: {result['title']} [{status_icon}]")
            if result["commands_run"]:
                lines.append("**Commands executed:**")
                for cmd in result["commands_run"]:
                    lines.append(f"```\n{cmd}\n```")
            if result["files_created"]:
                lines.append(f"**Files created:** {', '.join(result['files_created'])}")
            if result["files_modified"]:
                lines.append(f"**Files modified:** {', '.join(result['files_modified'])}")
            if result["errors"]:
                lines.append("**Errors:**")
                for err in result["errors"]:
                    lines.append(f"> {err[:200]}")
            if result["skipped_reason"]:
                lines.append(f"**Skipped reason:** {result['skipped_reason']}")
            lines.append("")

        # Manual steps
        lines.append("## What You Need To Do")
        manual_steps = instructions.get("manual_steps", [])
        skipped_results = [r for r in summary.get("results", []) if r["status"] == "skipped"]

        if manual_steps:
            for i, step in enumerate(manual_steps, 1):
                lines.append(f"{i}. **{step.get('description', '')}**")
                lines.append(f"   Reason: {step.get('reason', '')}")
        if skipped_results:
            for r in skipped_results:
                lines.append(f"- **Step {r['step_number']}: {r['title']}** - {r['skipped_reason']}")

        if not manual_steps and not skipped_results:
            lines.append("All steps were completed automatically!")
        lines.append("")

        # Cleanup
        cleanup = instructions.get("cleanup", [])
        if cleanup:
            lines.append("## Cleanup Instructions")
            for item in cleanup:
                lines.append(f"- {item.get('description', '')}")
                for cmd in item.get("commands", []):
                    lines.append(f"  ```\n  {cmd}\n  ```")
            lines.append("")

        return "\n".join(lines)

    def save_report(self, report: str, filename: str = None) -> str:
        """Save the report to a file and return the path."""
        if not filename:
            filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        filepath = REPORTS_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)

        print(f"[Reporter] Report saved to: {filepath}")
        return str(filepath)

    def save_raw_data(self, instructions: dict, execution_results: dict) -> str:
        """Save raw JSON data for debugging/reference."""
        filename = f"raw_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = REPORTS_DIR / filename
        data = {
            "instructions": instructions,
            "execution_results": execution_results,
            "timestamp": datetime.now().isoformat(),
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        return str(filepath)
