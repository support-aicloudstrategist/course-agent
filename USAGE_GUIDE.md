# Course Training Agent - Usage Guide

A comprehensive guide to installing, configuring, and using the Course Training Agent system. This tool automates the completion of online training courses by reading course content from your browser, parsing it into executable instructions using AI, and running the setup steps automatically.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Quick Start](#quick-start)
7. [Agent Details](#agent-details)
   - [Course Reader](#1-course-reader)
   - [Instruction Parser](#2-instruction-parser)
   - [Executor](#3-executor)
   - [Reporter](#4-reporter)
8. [Command-Line Options](#command-line-options)
9. [Workflow Walkthrough](#workflow-walkthrough)
10. [Safety & Security](#safety--security)
11. [Output & Reports](#output--reports)
12. [Supported Platforms](#supported-platforms)
13. [Troubleshooting](#troubleshooting)

---

## Overview

The Course Training Agent connects to your browser where a training course is open, reads all the content (text, code blocks, video transcripts), uses Claude AI to parse the content into structured step-by-step instructions, executes the automatable steps, and generates a detailed report of everything that was done and what still needs manual attention.

**Key workflow:**

```
Browser (course open) --> Course Reader --> Instruction Parser (AI) --> Executor --> Reporter
```

---

## Architecture

The system is composed of four specialized agents orchestrated by `main.py`:

| Agent | File | Role |
|---|---|---|
| **Course Reader** | `agents/course_reader.py` | Connects to browser via CDP, extracts page content |
| **Instruction Parser** | `agents/instruction_parser.py` | Uses Claude AI to convert raw content into structured instructions |
| **Executor** | `agents/executor.py` | Runs commands, creates files, downloads resources |
| **Reporter** | `agents/reporter.py` | Generates a Markdown report of all actions taken |

---

## Prerequisites

- **Python 3.10+**
- **Google Chrome** or **Microsoft Edge** browser
- **Anthropic API key** (for Claude AI-powered instruction parsing)
- **Windows OS** (batch scripts are provided for Windows; the Python code itself is cross-platform)

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/support-aicloudstrategist/course-agent.git
cd course-agent
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS/Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Playwright browsers

```bash
python -m playwright install chromium
```

---

## Configuration

### Anthropic API Key

The agent requires an Anthropic API key for AI-powered instruction parsing. Set it using any of these methods:

**Option A - Environment variable:**
```bash
set ANTHROPIC_API_KEY=sk-ant-your-key-here        # Windows CMD
export ANTHROPIC_API_KEY=sk-ant-your-key-here      # Bash/macOS/Linux
```

**Option B - Command-line flag:**
```bash
python main.py --set-api-key sk-ant-your-key-here
```
This saves the key to a local `settings.json` file (excluded from git).

**Option C - Interactive prompt:**
If no key is found at startup, the agent will prompt you to enter one.

### Settings File (`settings.json`)

A `settings.json` file is created automatically when you save your API key. It stores:
- `anthropic_api_key` - Your Anthropic API key

This file is listed in `.gitignore` and is never committed.

### Configuration Constants (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `AI_MODEL` | `claude-sonnet-4-6` | Claude model used for parsing and reporting |
| `MAX_TOKENS` | `8192` | Maximum tokens for AI responses |
| `BROWSER_CONNECT_TIMEOUT` | `30000` ms | Timeout for connecting to browser via CDP |
| `PAGE_LOAD_TIMEOUT` | `60000` ms | Timeout for page loads |
| `SCROLL_PAUSE_TIME` | `2` seconds | Pause between scroll actions during content extraction |
| `MAX_SCROLL_ATTEMPTS` | `50` | Maximum scroll iterations for infinite-scroll pages |
| `COMMAND_TIMEOUT` | `300` seconds | Timeout per executed command |
| `SAFE_MODE` | `True` | When enabled, prompts before running destructive commands |

---

## Quick Start

### Step 1: Start your browser with remote debugging

**Option A - Use the provided batch script:**
```
start-browser.bat
```

**Option B - Start manually:**
```bash
# Chrome
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222

# Edge
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222
```

> **Important:** Close all existing browser instances before starting with remote debugging. The `--remote-debugging-port` flag only works when Chrome/Edge starts fresh.

### Step 2: Open your training course

Navigate to your training course in the browser that was just launched.

### Step 3: Run the agent

**Option A - Use the provided batch script:**
```
run-agent.bat
```

**Option B - Run directly:**
```bash
python main.py
```

### Step 4: Follow the interactive prompts

1. Enter your API key (if not already configured)
2. Select the browser tab containing the course
3. Choose whether to read all sections or just the current page
4. Review the parsed instructions
5. Confirm execution

---

## Agent Details

### 1. Course Reader

**File:** `agents/course_reader.py`

The Course Reader connects to your browser using the Chrome DevTools Protocol (CDP) and extracts content from the open training course.

**What it extracts:**
- **Text content** - All visible text on the page, using platform-specific selectors for common LMS systems (AWS Training, Udemy, Coursera, Qwiklabs, etc.)
- **Code blocks** - Content inside `<pre><code>`, `.code-block`, `.CodeMirror`, and copy-to-clipboard elements
- **Video transcripts** - Captions, subtitle panels, and transcript sections; also attempts to click "Show Transcript" buttons
- **Navigation structure** - Sidebar menus, module lists, and table-of-contents links for multi-section courses
- **Images** - Images with alt text (useful for architecture diagrams), filtered to those wider than 200px
- **Resource links** - Links containing keywords like "download", "github", "documentation", "template"

**Multi-section support:**
If the course has a navigation sidebar with multiple sections/modules, the reader can automatically navigate through each one and extract all content sequentially.

**How it works:**
1. Connects to the browser's CDP endpoint (default: `http://localhost:9222`)
2. Lists all open tabs and lets you pick the course tab
3. Brings the selected tab to the front
4. Extracts content using a priority list of CSS selectors
5. Falls back to scroll-and-extract for pages without standard selectors
6. Optionally navigates to all linked sections

### 2. Instruction Parser

**File:** `agents/instruction_parser.py`

The Instruction Parser sends the extracted content to Claude AI and receives back structured, executable instructions in JSON format.

**What it produces:**
- **Course metadata** - Title, platform, summary, prerequisites
- **Environment requirements** - OS, tools, accounts, cloud services needed
- **Ordered steps** - Each step includes:
  - Step number and title
  - Type: `command`, `file_create`, `file_edit`, `download`, `config`, `manual`, or `verify`
  - Exact commands to run
  - File paths and content (for file operations)
  - Expected output (for verification steps)
  - Whether human intervention is required (and why)
- **Manual steps** - Steps that cannot be automated (GUI clicks, payments, logins)
- **Resources** - Links to documentation, repos, dashboards
- **Cleanup instructions** - Commands to tear down cloud resources after training

**Safety classification:**
The parser also classifies each step's safety level:
- **Destructive commands** - `rm -rf`, `drop database`, `terminate`, `destroy`, etc.
- **Cost-incurring commands** - `aws`, `az`, `gcloud`, `terraform apply`, `ec2 run-instances`, etc.
- **Human-required steps** - Flagged for manual intervention

**Content handling:**
If the course content exceeds 150,000 characters, it is truncated (keeping the beginning and end) to fit within Claude's context window.

### 3. Executor

**File:** `agents/executor.py`

The Executor takes the parsed instructions and runs them step by step on your machine.

**Supported step types:**

| Type | Action |
|---|---|
| `command` | Runs shell commands via `subprocess` |
| `file_create` | Creates new files with specified content |
| `file_edit` | Modifies existing files (or creates them if missing) |
| `download` | Downloads resources via `wget`/`curl` commands or direct HTTP requests |
| `config` | Runs configuration commands (treated same as `command`) |
| `verify` | Runs verification commands and checks output against expected results |
| `manual` | Skips the step and logs it for the user to complete |

**Execution flow for each step:**
1. Check if the step requires human intervention -> skip if yes
2. Run safety classification
3. If the step is flagged as unsafe (destructive or cost-incurring), prompt for confirmation
4. Execute the step based on its type
5. Capture stdout, stderr, exit codes, and timing
6. Log everything to both console and a log file

**Step results tracked:**
- Status: `success`, `failed`, `skipped`
- Commands run and their output
- Files created/modified
- Errors encountered
- Duration

### 4. Reporter

**File:** `agents/reporter.py`

The Reporter generates a comprehensive Markdown report of the entire process.

**Report sections:**
1. **Course Summary** - Course name, platform, key topics
2. **What Was Done** - Every action taken with exact commands and file paths
3. **Execution Results** - Success/failure status for each step with error details
4. **What You Need To Do** - Manual steps the user must complete
5. **Verification Checklist** - How to verify the setup is working
6. **Important Notes** - Warnings and gotchas
7. **Cleanup Instructions** - Commands to tear down resources (important for cloud costs)
8. **Resources & Links** - Relevant documentation and dashboards

**Two modes:**
- **AI-powered** (default) - Uses Claude to generate a detailed, context-aware report
- **Basic fallback** - Generates a structured report without AI if no API key is available

---

## Command-Line Options

```
python main.py [OPTIONS]
```

| Flag | Description | Default |
|---|---|---|
| `--cdp-port PORT` | Chrome DevTools Protocol port | `9222` |
| `--tab INDEX` | Auto-select browser tab by index (skip the interactive prompt) | Interactive |
| `--read-only` | Only read and parse the course; do not execute any commands | `False` |
| `--auto-execute` | Skip the "Ready to execute?" confirmation prompt (still confirms destructive ops) | `False` |
| `--single-page` | Only read the current page; don't navigate to other sections | `False` |
| `--all-sections` | Automatically read all sections without asking | `False` |
| `--working-dir PATH` | Working directory for command execution | Current directory |
| `--set-api-key KEY` | Save an Anthropic API key to `settings.json` and exit | - |

### Example Commands

```bash
# Full interactive mode
python main.py

# Read-only mode (parse course, don't execute anything)
python main.py --read-only

# Auto-select first tab, read all sections, execute automatically
python main.py --tab 0 --all-sections --auto-execute

# Use a custom CDP port and working directory
python main.py --cdp-port 9333 --working-dir C:\projects\my-lab

# Only read the current page (skip multi-section navigation)
python main.py --single-page

# Save your API key
python main.py --set-api-key sk-ant-your-key-here
```

---

## Workflow Walkthrough

Here is what happens when you run the agent end-to-end:

### Phase 1: Browser Connection
```
[1/5] CONNECTING TO BROWSER
  Connecting to Chrome via CDP at http://localhost:9222...
```
The agent connects to your browser via the Chrome DevTools Protocol. The browser must have been started with `--remote-debugging-port=9222`.

### Phase 2: Tab Selection
```
[2/5] SELECTING COURSE TAB
  Found 3 open tab(s):
   [0] Google - https://google.com
   [1] AWS Training - Module 3 - https://aws.training/...
   [2] GitHub - https://github.com/...

  Enter tab number to read (0-2): 1
```
You pick the tab with your training course open.

### Phase 3: Content Extraction
```
[3/5] READING COURSE CONTENT
  Extracting text, code blocks, transcripts...
  Found 8 navigation items.
  Read all sections? (yes/no, default=yes): yes
  Reading all sections...
  Extracted 45230 characters of content
  4 section(s) read
  Raw content saved to: reports/raw_content_20260405_143022.txt
```
The Course Reader extracts all content and saves the raw text.

### Phase 4: AI Parsing
```
[4/5] PARSING INSTRUCTIONS WITH AI
  Analyzing course content and extracting setup instructions...

  Course: AWS Cloud Practitioner Lab 3
  Platform: AWS Training
  Steps found: 12
  Manual steps: 2
```
Claude AI analyzes the content and produces structured instructions.

### Phase 5: Execution
```
[5/5] EXECUTING INSTRUCTIONS
  Ready to execute? (yes/no): yes
  Working directory: C:\projects\lab3

  Step 1: Install AWS CLI... SUCCESS
  Step 2: Configure credentials... SKIPPED (requires human)
  Step 3: Create S3 bucket... SUCCESS
  ...

  Execution complete:
    Successful: 9
    Failed: 1
    Skipped: 2
```

### Phase 6: Report Generation
A detailed Markdown report is generated and saved to the `reports/` directory.

---

## Safety & Security

The agent includes multiple safety mechanisms:

### Safe Mode (enabled by default)
When `SAFE_MODE = True` in `config.py`, the agent prompts for confirmation before running:
- **Destructive commands** - `rm -rf`, `drop database`, `delete`, `destroy`, `terminate`, `format`, `fdisk`, `mkfs`
- **Cost-incurring commands** - `aws`, `az`, `gcloud`, `terraform apply`, `ec2 run-instances`, `create-stack`, `kubectl create`

### Human-Required Steps
Steps that require GUI interaction, credentials entry, payments, or other human actions are automatically detected by the AI parser and **skipped during execution**. They are listed in the final report under "What You Need To Do".

### Read-Only Mode
Use `--read-only` to run the agent without executing any commands. This lets you review the parsed instructions before committing to execution.

### API Key Security
- API keys are stored in `settings.json`, which is excluded from git via `.gitignore`
- The agent never logs or displays your full API key

---

## Output & Reports

All output files are saved to the `reports/` directory (excluded from git):

| File | Description |
|---|---|
| `raw_content_YYYYMMDD_HHMMSS.txt` | Raw extracted text from the course |
| `instructions_YYYYMMDD_HHMMSS.json` | Structured instructions parsed by AI |
| `execution_YYYYMMDD_HHMMSS.log` | Timestamped execution log |
| `report_YYYYMMDD_HHMMSS.md` | Final Markdown report |
| `raw_data_YYYYMMDD_HHMMSS.json` | Combined instructions + execution results |

---

## Supported Platforms

The Course Reader includes CSS selectors optimized for these course platforms:

- **AWS Training / Qwiklabs** - `.aws-training-content`, `.qwiklabs-content`, `.lab-content`
- **Udemy** - `.ud-component--course-taking--app`
- **Coursera** - `.rc-DesktopContent`
- **Generic LMS** - `.lesson-content`, `.course-content`, `.training-content`, `.markdown-body`
- **Documentation sites** - `article`, `main`, `[role='main']`, `.content`

For platforms not listed above, the agent falls back to a scroll-and-extract approach that captures all visible text on the page.

---

## Troubleshooting

### Cannot connect to browser

**Error:** `Could not connect to browser at http://localhost:9222`

**Fix:**
1. Close **all** Chrome/Edge windows completely (check Task Manager)
2. Restart the browser with the debugging flag:
   ```
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
   ```
3. Or use `start-browser.bat`

### No tabs found

**Error:** `No tabs found. Open your course in the browser first.`

**Fix:** Make sure the course page is loaded in the browser before running the agent.

### API key not working

**Error:** `Anthropic API key not found`

**Fix:**
```bash
python main.py --set-api-key sk-ant-your-key-here
```
Or set the `ANTHROPIC_API_KEY` environment variable.

### Content extraction is incomplete

- Try using `--single-page` if multi-section navigation is incorrectly detected
- For pages with heavy JavaScript rendering, wait a few seconds after the page loads before running the agent
- The agent scrolls through the page automatically, but some dynamic content may not be captured

### Command execution fails

- Check the execution log in `reports/execution_*.log` for detailed error output
- Make sure required tools are installed (the parsed instructions will list prerequisites)
- Use `--working-dir` to specify the correct directory for command execution
- Run with `--read-only` first to review instructions before executing

### AI parsing returns empty steps

- The course content may be too short or not contain actionable instructions
- Check `reports/raw_content_*.txt` to verify content was extracted correctly
- Try reading a different tab or section of the course
