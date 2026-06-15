import json
import re

from prompt import (
    get_planning_messages,
    get_file_generation_messages,
)
from llm_manager import call_llm
from workspace_manager import WorkspaceManager


def extract_json_from_response(text: str):
    """
    Extract the first valid JSON object or array from an LLM response.

    Handles:
    - Pure JSON
    - Markdown code fences
    - Explanatory text before/after JSON
    - Large JSON payloads efficiently

    Returns:
        Parsed Python object
    """

    # ---------------------------------------------------------
    # Attempt 1: direct parse
    # ---------------------------------------------------------
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # ---------------------------------------------------------
    # Attempt 2: markdown code blocks
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
    # Attempt 3: brace matching
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
                candidate = text[start : i + 1]

                try:
                    return json.loads(candidate)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Located JSON block but parsing failed: {e}"
                    )

    raise ValueError("Incomplete JSON structure in LLM response.")


def flatten_tree(tree: dict, current_path: str = "") -> list:
    """
    Recursively converts a JSON tree into a flat list of file paths.
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
# 1. Initialize workspace
# ------------------------------------------------------------------

workspace = WorkspaceManager("./my_new_project")

# ------------------------------------------------------------------
# 2. User requirements
# ------------------------------------------------------------------

user_prompt = "build a jumping dinosaur game in html css js"

# ------------------------------------------------------------------
# 3. Phase 1: Plan architecture
# ------------------------------------------------------------------

print("🧠 Phase 1: Planning Directory Structure...")

plan_messages = get_planning_messages(user_prompt)
raw_plan_response = call_llm(plan_messages)

try:
    project_structure = extract_json_from_response(raw_plan_response)

    if not isinstance(project_structure, dict):
        raise ValueError(
            f"Expected project structure dictionary, got {type(project_structure).__name__}"
        )

    workspace.create_structure(project_structure)

    files_to_build = flatten_tree(project_structure)

    print(f"📋 Planned {len(files_to_build)} files.")

except Exception as e:
    print(f"❌ Failed to parse planning output: {e}")
    print("\nRaw planning response:\n")
    print(raw_plan_response)
    raise SystemExit(1)


# ------------------------------------------------------------------
# 3.5 Filter Out Binary Files
# ------------------------------------------------------------------
BINARY_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.ico', '.mp3', '.wav', '.mp4', '.ttf')

# Filter the list so the LLM only tries to write text/code files
files_to_build = [f for f in files_to_build if not f.lower().endswith(BINARY_EXTENSIONS)]
print(f"📋 Filtered out binary files. {len(files_to_build)} text/code files to generate.")

# ------------------------------------------------------------------
# 4. Phase 2: Stateful File Generation with Retries
# ------------------------------------------------------------------
global_state = {}
MAX_RETRIES = 3

print("\n🚀 Phase 2: Stateful File Generation...")
for filepath in files_to_build:
    print(f"\n⚙️ Generating code for: {filepath}")
    
    success = False
    
    # The Retry Loop
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            file_messages = get_file_generation_messages(user_prompt, filepath, global_state)
            raw_file_response = call_llm(file_messages)
            
            # Catch completely empty responses before passing to the parser
            if not raw_file_response or not raw_file_response.strip():
                raise ValueError("Received an empty response from the LLM.")
            
            parsed_response = extract_json_from_response(raw_file_response)
            
            file_code = parsed_response.get("code", "")
            file_summary = parsed_response.get("summary", "No summary provided.")
            
            # Save and update memory
            workspace.write_file(filepath, file_code)
            global_state[filepath] = file_summary
            
            print(f"✅ Saved {filepath} | Memory updated.")
            success = True
            break  # Exit the retry loop because it succeeded
            
        except Exception as e:
            print(f"⚠️ Attempt {attempt}/{MAX_RETRIES} failed for {filepath}. Error: {e}")
            if attempt == MAX_RETRIES:
                print(f"❌ Skipping {filepath} after {MAX_RETRIES} failed attempts.")
                print(f"Raw response preview: {raw_file_response[:100] if 'raw_file_response' in locals() and raw_file_response else 'None'}...")

    if not success:
        print(f"🛑 Critical failure on {filepath}. The final project may not function correctly.")

print("\n🎉 Project Generation Complete!")