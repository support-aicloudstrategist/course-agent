"""
Course Training Agent - Main Orchestrator

This is the entry point for the automated course training agent.
It orchestrates the full workflow:
  1. Connect to your browser (where the course is open)
  2. Read all course content (text, code, video transcripts)
  3. Parse content into executable instructions using AI
  4. Execute the setup steps automatically
  5. Generate a detailed report of everything done

Usage:
  python main.py                     # Interactive mode
  python main.py --read-only         # Only read & parse, don't execute
  python main.py --cdp-port 9222     # Custom CDP port
  python main.py --tab 0             # Auto-select first tab
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import REPORTS_DIR, save_config, load_config
from agents.course_reader import CourseReader
from agents.instruction_parser import InstructionParser
from agents.executor import Executor
from agents.reporter import Reporter


def print_banner():
    print("""
  ╔══════════════════════════════════════════════════════╗
  ║         COURSE TRAINING AGENT                       ║
  ║   Automated Training Course Completion System       ║
  ╚══════════════════════════════════════════════════════╝
    """)


async def confirm_action(message: str) -> bool:
    """Ask the user to confirm a potentially destructive action."""
    print(f"\n⚠️  CONFIRMATION REQUIRED:")
    print(message)
    while True:
        response = input("Proceed? (yes/no): ").strip().lower()
        if response in ("yes", "y"):
            return True
        if response in ("no", "n"):
            return False
        print("Please enter 'yes' or 'no'.")


async def run_interactive(args):
    """Run the agent in interactive mode."""
    print_banner()

    # Step 0: Check API key
    from config import get_api_key
    api_key = get_api_key()
    if not api_key:
        print("No Anthropic API key found.")
        api_key = input("Enter your Anthropic API key: ").strip()
        if api_key:
            cfg = load_config()
            cfg["anthropic_api_key"] = api_key
            save_config(cfg)
            os.environ["ANTHROPIC_API_KEY"] = api_key
            print("API key saved to settings.json")
        else:
            print("ERROR: API key is required for AI-powered instruction parsing.")
            print("Set ANTHROPIC_API_KEY env variable or re-run and enter it.")
            return

    cdp_url = f"http://localhost:{args.cdp_port}"

    # Step 1: Connect to browser
    print(f"\n[1/5] CONNECTING TO BROWSER")
    print(f"  Connecting to Chrome via CDP at {cdp_url}...")
    print(f"  Make sure your browser was started with:")
    print(f"    chrome.exe --remote-debugging-port={args.cdp_port}")
    print()

    reader = CourseReader()
    try:
        await reader.connect_to_browser(cdp_url)
    except Exception as e:
        print(f"\n  ERROR: Could not connect to browser at {cdp_url}")
        print(f"  {e}")
        print(f"\n  To fix this, close Chrome completely, then restart it with:")
        print(f'    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port={args.cdp_port}')
        print(f"  Or for Edge:")
        print(f'    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" --remote-debugging-port={args.cdp_port}')
        print(f"\n  Then open your training course in the browser and re-run this agent.")
        return

    # Step 2: Select the course tab
    print(f"\n[2/5] SELECTING COURSE TAB")
    tabs = await reader.get_open_tabs()

    if not tabs:
        print("  No tabs found. Open your course in the browser first.")
        await reader.close()
        return

    print(f"  Found {len(tabs)} open tab(s):")
    for tab in tabs:
        marker = " ← " if args.tab is not None and tab["index"] == args.tab else "   "
        print(f"  {marker}[{tab['index']}] {tab['title'][:70]}")
        print(f"       {tab['url'][:80]}")

    if args.tab is not None:
        tab_index = args.tab
    else:
        while True:
            try:
                tab_index = int(input(f"\n  Enter tab number to read (0-{len(tabs)-1}): "))
                if 0 <= tab_index < len(tabs):
                    break
            except ValueError:
                pass
            print("  Invalid selection. Try again.")

    await reader.select_tab(tab_index)

    # Step 3: Read course content
    print(f"\n[3/5] READING COURSE CONTENT")
    print(f"  Extracting text, code blocks, transcripts...")

    read_all = True
    if not args.single_page:
        # Check if multi-section course
        content = await reader.extract_page_content()
        if content.get("navigation"):
            print(f"  Found {len(content['navigation'])} navigation items.")
            if args.all_sections:
                read_all = True
            else:
                resp = input("  Read all sections? (yes/no, default=yes): ").strip().lower()
                read_all = resp in ("", "yes", "y")

        if read_all and content.get("navigation"):
            print("  Reading all sections...")
            await reader.read_all_sections()
    else:
        await reader.extract_page_content()

    full_text = reader.get_all_content_as_text()
    print(f"\n  Extracted {len(full_text)} characters of content")
    print(f"  {len(reader.all_content)} section(s) read")

    # Save raw content
    raw_content_path = REPORTS_DIR / f"raw_content_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(raw_content_path, "w", encoding="utf-8") as f:
        f.write(full_text)
    print(f"  Raw content saved to: {raw_content_path}")

    # Step 4: Parse instructions with AI
    print(f"\n[4/5] PARSING INSTRUCTIONS WITH AI")
    print(f"  Analyzing course content and extracting setup instructions...")

    parser = InstructionParser()
    instructions = parser.parse_instructions(full_text)

    print(f"\n  Course: {instructions.get('course_title', 'Unknown')}")
    print(f"  Platform: {instructions.get('course_platform', 'Unknown')}")
    print(f"  Steps found: {len(instructions.get('steps', []))}")
    print(f"  Manual steps: {len(instructions.get('manual_steps', []))}")

    # Save parsed instructions
    instructions_path = REPORTS_DIR / f"instructions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(instructions_path, "w", encoding="utf-8") as f:
        json.dump(instructions, f, indent=2, default=str)
    print(f"  Instructions saved to: {instructions_path}")

    # Show steps preview
    print(f"\n  Steps to execute:")
    for step in instructions.get("steps", []):
        human_tag = " [MANUAL]" if step.get("requires_human") else ""
        print(f"    {step.get('step_number', '?')}. {step.get('title', 'Unknown')}{human_tag}")

    if instructions.get("manual_steps"):
        print(f"\n  Manual steps (you need to do these):")
        for ms in instructions["manual_steps"]:
            print(f"    - {ms.get('description', '')}")

    # Step 5: Execute (unless read-only mode)
    execution_results = {"total_steps": 0, "successful": 0, "failed": 0, "skipped": 0, "results": []}

    if args.read_only:
        print(f"\n[5/5] EXECUTION SKIPPED (read-only mode)")
    else:
        print(f"\n[5/5] EXECUTING INSTRUCTIONS")

        if not args.auto_execute:
            resp = input("\n  Ready to execute? (yes/no): ").strip().lower()
            if resp not in ("yes", "y"):
                print("  Execution cancelled by user.")
                args.read_only = True

        if not args.read_only:
            working_dir = args.working_dir or os.getcwd()
            print(f"  Working directory: {working_dir}")

            executor = Executor(working_dir=working_dir, confirm_callback=confirm_action)
            await executor.execute_all(instructions)
            execution_results = executor.get_execution_summary()

            print(f"\n  Execution complete:")
            print(f"    Successful: {execution_results['successful']}")
            print(f"    Failed: {execution_results['failed']}")
            print(f"    Skipped: {execution_results['skipped']}")

    # Generate report
    print(f"\n[REPORT] GENERATING COMPLETION REPORT")
    reporter = Reporter()
    report = reporter.generate_report(
        instructions=instructions,
        execution_results=execution_results,
        course_content_summary=full_text[:10000],
    )

    report_path = reporter.save_report(report)
    reporter.save_raw_data(instructions, execution_results)

    print(f"\n{'='*60}")
    print(f"REPORT")
    print(f"{'='*60}")
    print(report)
    print(f"\n{'='*60}")
    print(f"Report saved to: {report_path}")
    print(f"All files in: {REPORTS_DIR}")

    # Cleanup
    await reader.close()
    print("\nDone!")


def main():
    parser = argparse.ArgumentParser(
        description="Course Training Agent - Automatically complete online training courses"
    )
    parser.add_argument(
        "--cdp-port", type=int, default=9222,
        help="Chrome DevTools Protocol port (default: 9222)"
    )
    parser.add_argument(
        "--tab", type=int, default=None,
        help="Auto-select browser tab by index"
    )
    parser.add_argument(
        "--read-only", action="store_true",
        help="Only read and parse course, don't execute commands"
    )
    parser.add_argument(
        "--auto-execute", action="store_true",
        help="Execute without asking for confirmation (still confirms destructive ops)"
    )
    parser.add_argument(
        "--single-page", action="store_true",
        help="Only read the current page, don't navigate to other sections"
    )
    parser.add_argument(
        "--all-sections", action="store_true",
        help="Automatically read all sections without asking"
    )
    parser.add_argument(
        "--working-dir", type=str, default=None,
        help="Working directory for command execution"
    )
    parser.add_argument(
        "--set-api-key", type=str, default=None,
        help="Set the Anthropic API key and save to config"
    )

    args = parser.parse_args()

    # Handle API key setup
    if args.set_api_key:
        cfg = load_config()
        cfg["anthropic_api_key"] = args.set_api_key
        save_config(cfg)
        print("API key saved to settings.json")
        return

    asyncio.run(run_interactive(args))


if __name__ == "__main__":
    main()
