import json
import re

from prompt import (
    get_planning_messages,
    get_file_generation_messages,
    get_error_fix_messages,
)
from llm_manager import call_llm
from workspace_manager import WorkspaceManager


def extract_json_from_response(text: str):
    """
    Extract the first valid JSON object or array from an LLM response.
    Handles markdown, explanations, and malformed wrappers.
    """

    # ---------------------------------------------------------
    # Attempt 1: Direct parse
    # ---------------------------------------------------------
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # ---------------------------------------------------------
    # Attempt 2: Markdown code blocks
    # ---------------------------------------------------------
    code_blocks = re.findall(
        r"```(?:json)?\s*(.*?)\s*```",
        text,
        re.DOTALL | re.IGNORECASE,
    )

    for block in code_blocks:
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            continue

    # ---------------------------------------------------------
    # Attempt 3: Brace matching
    # ---------------------------------------------------------
    start = None

    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            break

    if start is None:
        raise ValueError("No JSON structure found in LLM response.")

    opening = text[start]
    closing = "}" if opening == "{" else "]"

    depth = 0
    in_string = False
    escaped = False

    for i in range(start, len(text)):
        ch = text[i]

        if escaped:
            escaped = False
            continue

        if ch == "\\":
            escaped = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == opening:
            depth += 1

        elif ch == closing:
            depth -= 1

            if depth == 0:
                candidate = text[start:i + 1]

                try:
                    return json.loads(candidate)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Located JSON block but parsing failed: {e}"
                    )

    raise ValueError("Incomplete JSON structure in LLM response.")


def flatten_tree(tree: dict, current_path: str = "") -> list:
    """
    Converts nested directory structure into a flat list of files.
    """

    file_paths = []

    for key, value in tree.items():
        path = f"{current_path}/{key}" if current_path else key

        if isinstance(value, dict):
            file_paths.extend(flatten_tree(value, path))
        else:
            file_paths.append(path)

    return file_paths


# ------------------------------------------------------------------
# 1. Initialize Workspace
# ------------------------------------------------------------------

workspace = WorkspaceManager("./my_new_project")

# ------------------------------------------------------------------
# 2. User Prompt
# ------------------------------------------------------------------

user_prompt = """
Build a command-line application that reads student exam data from a CSV file, computes statistics, assigns letter grades, and produces a formatted summary report. This assignment practises OOP design, file I/O, and input validation — all essential before touching any web framework.
 
 
Problem statement
 
Your company runs internal training exams. After each exam, HR exports a CSV with student names and three subject scores. They want an automated tool that reads this file, calculates averages, maps to letter grades, identifies top and bottom performers, and writes a clean summary CSV for management.
 
 
Project setup
 
Use uv to initialise the project: uv init <project-name>
 
Add dependencies: uv add <package>
 
Run scripts: uv run python main.py
 
File structure is your choice — organise logically using pyproject.toml as the project root
 
 
Input format
 
CSV file with header: Name,Math,Science,English
 
Each row = one student with three integer scores (0–100)
 
Must handle at least 10 students
 
Example row:  Rahul Sharma,88,72,90
 
 
Requirements
 
Student class: stores name and three scores; has methods average() → float and grade() → str
 
Grade mapping: A=90–100, B=75–89, C=60–74, D=45–59, F=below 45
 
GradeBook class: holds list of Student objects; methods — load_csv(path), save_summary(path), top_performers(n=3), class_average()
 
file_handler.py: read_csv(path) → list[dict], write_csv(path, data)
 
validators.py: validate_score(value) raises ValueError if score < 0 or > 100
 
main.py: accepts input CSV path as a command-line argument (sys.argv)
 
Handle FileNotFoundError with a friendly message — do not crash
 
Handle rows with missing or non-numeric scores — skip the row and print a warning
 
 
Expected output
 
Console: print class average, top 3 students, count of each grade
 
summary.csv columns: Name, Math, Science, English, Average, Grade
 
Average rounded to 2 decimal places
 
 
Sample output
 
Class average: 76.40
 
Top performers: Rahul Sharma (92.33), Priya Patel (89.00), ...
 
Grade distribution: A=2  B=5  C=2  D=1  F=0

"""

# ------------------------------------------------------------------
# 3. Phase 1: Planning
# ------------------------------------------------------------------

print("🧠 Phase 1: Planning Project Architecture...")

plan_messages = get_planning_messages(user_prompt)
raw_plan_response = call_llm(plan_messages)

try:
    planning_data = extract_json_from_response(raw_plan_response)

    tech_stack = planning_data.get("tech_stack", "")
    execution_command = planning_data.get("execution_command", "")
    project_structure = planning_data.get("structure")

    if not isinstance(project_structure, dict):
        raise ValueError(
            "Planning response missing valid 'structure' object."
        )

    workspace.create_structure(project_structure)

    files_to_build = flatten_tree(project_structure)

    print(f"📦 Tech Stack: {tech_stack}")
    print(f"▶ Execution Command: {execution_command}")
    print(f"📋 Planned {len(files_to_build)} files.")

except Exception as e:
    print(f"❌ Failed to parse planning output: {e}")
    print("\nRaw response:\n")
    print(raw_plan_response)
    raise SystemExit(1)

# ------------------------------------------------------------------
# 4. Phase 2: Stateful File Generation
# ------------------------------------------------------------------

global_state = {}

print("\n🚀 Phase 2: Stateful File Generation...")

for filepath in files_to_build:

    print(f"\n⚙️ Generating: {filepath}")

    file_messages = get_file_generation_messages(
        requirements=user_prompt,
        target_file=filepath,
        shared_context=global_state,
    )

    raw_file_response = call_llm(file_messages)

    try:
        parsed_response = extract_json_from_response(raw_file_response)

        if not isinstance(parsed_response, dict):
            raise ValueError(
                f"Expected JSON object, got {type(parsed_response).__name__}"
            )

        file_code = parsed_response.get("code")
        file_summary = parsed_response.get(
            "summary",
            "No summary provided."
        )

        if file_code is None:
            raise ValueError("Missing required field: code")

        workspace.write_file(filepath, file_code)

        global_state[filepath] = file_summary

        print(f"✅ Saved {filepath}")

    except Exception as e:
        print(f"❌ Failed to generate {filepath}: {e}")
        print("\nResponse Preview:\n")
        print(raw_file_response[:500])


# ------------------------------------------------------------------
# 5. Phase 3: Execution + Auto Fix Loop
# ------------------------------------------------------------------

if execution_command:

    print(
        f"\n🖥️ Phase 3: Running execution command: "
        f"`{execution_command}`"
    )

    max_fix_attempts = 4

    for attempt in range(1, max_fix_attempts + 1):

        exit_code, terminal_output = workspace.execute_command(
            execution_command
        )

        execution_success = (
            exit_code == 0
            and "Traceback" not in terminal_output
            and "Error" not in terminal_output
        )

        if execution_success:

            print(
                f"✅ Execution successful!\n\n"
                f"Terminal Output:\n{terminal_output}"
            )

            break

        print(
            f"⚠️ Execution failed "
            f"(Attempt {attempt}/{max_fix_attempts})"
        )

        print(f"\nTerminal Output:\n{terminal_output[:500]}... [truncated]\n")

        if attempt == max_fix_attempts:
            print(
                "🛑 Max fix attempts reached. "
                "Manual intervention required."
            )
            break

        print(
            "🛠️ Asking agent to analyze logs and "
            "generate a fix..."
        )

        fix_messages = get_error_fix_messages(
            requirements=user_prompt,
            tech_stack=tech_stack,
            execution_command=execution_command,
            error_log=terminal_output,
            shared_context=global_state,
        )

        raw_fix_response = call_llm(fix_messages)

        try:
            fix_data = extract_json_from_response(
                raw_fix_response
            )

            file_to_fix = fix_data.get("file_to_fix")
            fixed_code = fix_data.get("code")
            fix_summary = fix_data.get(
                "summary",
                "Auto-generated fix."
            )
            new_cmd = fix_data.get("new_execution_command")

            # Apply File Fixes
            if file_to_fix and fixed_code:
                workspace.write_file(
                    file_to_fix,
                    fixed_code
                )

                global_state[file_to_fix] = fix_summary

                print(
                    f"🩹 Patched {file_to_fix}\n"
                    f"Reason: {fix_summary}"
                )
            
            # Apply Command Fixes
            if new_cmd and new_cmd != execution_command:
                print(f"🔄 Agent updated execution command: `{execution_command}` -> `{new_cmd}`")
                execution_command = new_cmd
            
            if not file_to_fix and not new_cmd:
                print("❌ Agent did not return a valid file to fix or a new command.")

        except Exception as e:
            print(
                f"❌ Failed to apply auto-fix: {e}"
            )

else:
    print(
        "\n⚠️ No execution command provided by planner. "
        "Skipping Phase 3."
    )

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------

print("\n🎉 Agent Workflow Complete!")