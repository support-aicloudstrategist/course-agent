"""
Instruction Parser Agent - Uses Claude AI to analyze course content and extract
structured, executable instructions.

Takes raw course content (text, code blocks, transcripts) and produces:
1. A list of ordered steps to complete the training
2. Commands to execute
3. Files to create/modify
4. Resources to download
5. Manual steps that require human intervention
"""
import json
from typing import Optional

from anthropic import Anthropic

from config import get_api_key, AI_MODEL, MAX_TOKENS


SYSTEM_PROMPT = """You are an expert training course analyzer. Your job is to read course/training content and extract precise, actionable setup instructions.

You will receive raw content extracted from an online training course. Analyze it and produce a structured JSON response with the following format:

{
  "course_title": "Name of the course/training",
  "course_platform": "Platform name (e.g., AWS Training, Udemy, Coursera, Qwiklabs)",
  "summary": "Brief 2-3 sentence summary of what this training covers",
  "prerequisites": ["List of prerequisites mentioned"],
  "environment": {
    "os": "Required OS if mentioned",
    "tools": ["List of required tools/software"],
    "accounts": ["Required accounts/subscriptions"],
    "cloud_services": ["AWS/Azure/GCP services used"]
  },
  "steps": [
    {
      "step_number": 1,
      "title": "Short title for the step",
      "description": "Detailed description of what to do",
      "type": "command|file_create|file_edit|download|config|manual|verify",
      "commands": ["exact commands to run, if applicable"],
      "file_path": "path for file operations, if applicable",
      "file_content": "content to write, if applicable",
      "expected_output": "what to expect after this step",
      "notes": "any warnings or important notes",
      "requires_human": false,
      "human_reason": "why human intervention is needed, if applicable"
    }
  ],
  "manual_steps": [
    {
      "description": "Steps that CANNOT be automated and need human action",
      "reason": "Why this needs human intervention (e.g., requires GUI click, payment, etc.)"
    }
  ],
  "resources": [
    {
      "name": "Resource name",
      "url": "URL if available",
      "purpose": "What it's used for"
    }
  ],
  "cleanup": [
    {
      "description": "Cleanup steps to run after training",
      "commands": ["cleanup commands"]
    }
  ]
}

Rules:
1. Extract EXACT commands from the course - do not guess or modify them
2. Preserve exact file paths, names, and content from the training
3. If a step requires clicking a UI button or visual interaction, mark it as requires_human=true
4. Include ALL steps, even small ones - completeness is critical
5. For cloud resources (EC2, S3, etc.), extract exact configurations (instance type, region, etc.)
6. If the training mentions specific values (AMI IDs, IP ranges, etc.), capture them exactly
7. Order steps in the exact sequence they should be executed
8. If credentials or API keys are needed, mark those steps as requires_human=true
9. For video content, pay extra attention to commands shown on screen vs spoken
10. Include verification steps (e.g., "curl localhost:8080 to verify the server is running")
"""


class InstructionParser:
    """Parses course content into executable instructions using Claude AI."""

    def __init__(self):
        api_key = get_api_key()
        if not api_key:
            raise ValueError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY env variable "
                "or add it to course-agent/settings.json"
            )
        self.client = Anthropic(api_key=api_key)

    def parse_instructions(self, course_content: str) -> dict:
        """Parse raw course content into structured instructions."""
        # Truncate if too long (Claude has context limits)
        max_content_len = 150000
        if len(course_content) > max_content_len:
            # Keep beginning and end, which often have the most important info
            half = max_content_len // 2
            course_content = (
                course_content[:half]
                + "\n\n[... content truncated for length ...]\n\n"
                + course_content[-half:]
            )

        response = self.client.messages.create(
            model=AI_MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Here is the training course content to analyze:\n\n{course_content}",
                }
            ],
        )

        raw_text = response.content[0].text

        # Extract JSON from the response
        parsed = self._extract_json(raw_text)
        return parsed

    def parse_incremental(self, new_content: str, previous_steps: dict) -> dict:
        """Parse additional course content, building on previously extracted steps."""
        prompt = f"""I previously extracted these steps from earlier sections of the training:

{json.dumps(previous_steps, indent=2)}

Now here is NEW content from the next section(s). Extract any ADDITIONAL steps and merge them with the existing ones.
Do not duplicate steps that already exist. Return the complete updated instruction set.

NEW CONTENT:
{new_content}"""

        response = self.client.messages.create(
            model=AI_MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text
        return self._extract_json(raw_text)

    def classify_step_safety(self, step: dict) -> dict:
        """Classify a step's safety level for execution."""
        commands = step.get("commands", [])
        step_type = step.get("type", "")

        safety = {
            "safe": True,
            "destructive": False,
            "cost_implications": False,
            "needs_confirmation": False,
            "reasons": [],
        }

        destructive_patterns = [
            "rm -rf", "rm -r", "drop database", "delete", "destroy",
            "terminate", "format", "fdisk", "mkfs",
        ]
        cost_patterns = [
            "aws ", "az ", "gcloud ", "terraform apply",
            "ec2 run-instances", "create-stack", "kubectl create",
        ]
        for cmd in commands:
            cmd_lower = cmd.lower()
            for pattern in destructive_patterns:
                if pattern in cmd_lower:
                    safety["destructive"] = True
                    safety["needs_confirmation"] = True
                    safety["reasons"].append(f"Destructive command: {pattern}")

            for pattern in cost_patterns:
                if pattern in cmd_lower:
                    safety["cost_implications"] = True
                    safety["needs_confirmation"] = True
                    safety["reasons"].append(f"May incur cloud costs: {pattern}")

        if step.get("requires_human"):
            safety["needs_confirmation"] = True
            safety["reasons"].append("Requires human intervention")

        if safety["destructive"] or safety["needs_confirmation"]:
            safety["safe"] = False

        return safety

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from AI response text."""
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON block in markdown code fence
        json_match = None
        for pattern in [r"```json\s*\n(.*?)\n```", r"```\s*\n(.*?)\n```", r"\{.*\}"]:
            import re
            match = re.search(pattern, text, re.DOTALL)
            if match:
                json_str = match.group(1) if match.lastindex else match.group(0)
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    continue

        # Last resort: find the first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        # Return raw text wrapped in a dict if parsing fails
        return {
            "course_title": "Unknown",
            "summary": "Failed to parse structured instructions",
            "raw_response": text,
            "steps": [],
            "manual_steps": [],
        }
