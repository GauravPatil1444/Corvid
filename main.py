from code_editor import CodeEditor

from utils.json_utils import (
    extract_json_from_response,
    flatten_tree,
    looks_like_real_code,
    is_documentation_file,
)

from prompt import (
    get_intent_messages,
    get_planning_messages,
    get_file_generation_messages,
    get_error_fix_messages,
)

from llm_manager import call_llm
from workspace_manager import WorkspaceManager

MAX_FILE_GENERATION_RETRIES = 3
AUTO_RERUN_AFTER_FIX = True
MAX_FIX_ATTEMPTS = 4
STOP_AFTER_FIRST_FILE_PATCH = True
ENABLE_CODE_INDEXING = True


def route_intent(user_prompt: str) -> str:
    """Determines if the user wants to CREATE a new project or EDIT an existing one."""
    messages = get_intent_messages(user_prompt)
    raw_response = call_llm(messages)
    try:
        data = extract_json_from_response(raw_response)
        return data.get("intent", "CREATE").upper()
    except Exception as e:
        print(f"⚠️ Intent routing failed ({e}). Defaulting to CREATE.")
        return "CREATE"

# ------------------------------------------------------------------
# 1. Initialize Workspace
# ------------------------------------------------------------------

workspace_dir = "./my_new_project"

workspace = WorkspaceManager(
    workspace_dir
)

# ------------------------------------------------------------------
# 2. User Prompt
# ------------------------------------------------------------------

user_prompt = "move add button to right side below other opeartor btns"

intent = route_intent(user_prompt)
def run_project_generation():

    global workspace

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
        original_execution_command = execution_command
        project_structure = planning_data.get("structure")

        if not isinstance(project_structure, dict):
            raise ValueError(
                "Planning response missing valid 'structure' object."
            )

        workspace.create_structure(project_structure)

        files_to_build = flatten_tree(project_structure)

        BINARY_EXTENSIONS = (
            '.png', '.jpg', '.jpeg', '.gif', '.ico', 
            '.mp3', '.wav', '.mp4', '.ttf', '.pdf', '.woff'
        )
        files_to_build = [
            f for f in files_to_build 
            if not f.lower().endswith(BINARY_EXTENSIONS)
        ]

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
        # ---------------------------------------------------------
        # NEW: HARD BLOCK FOR BINARY ASSETS
        # ---------------------------------------------------------
        BINARY_EXTENSIONS = (
            '.png', '.jpg', '.jpeg', '.gif', '.ico', '.webp',
            '.mp3', '.wav', '.mp4', '.ttf', '.pdf', '.woff', '.eot'
        )
        
        # .strip() handles any weird trailing spaces the LLM might hallucinate
        if filepath.strip().lower().endswith(BINARY_EXTENSIONS):
            print(f"\n⏩ Skipping binary asset generation: {filepath}")
            # Initialize it in the state so other files know it "exists"
            global_state[filepath] = "Binary asset placeholder."
            continue

        print(f"\n⚙️ Generating: {filepath}")
        success = False

        for generation_attempt in range(
            1,
            MAX_FILE_GENERATION_RETRIES + 1,
        ):

            file_messages = get_file_generation_messages(
                requirements=user_prompt,
                target_file=filepath,
                shared_context=global_state,
            )

            # File-type-specific instructions
            if filepath.lower().endswith(".md"):
                file_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Generate complete Markdown documentation. "
                            "Do NOT generate source code. "
                            "Do NOT place full implementation code in the README."
                        ),
                    }
                )

            elif filepath.lower().endswith(".gitignore"):
                file_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Generate only valid .gitignore contents. "
                            "Do not generate explanations or source code."
                        ),
                    }
                )

            if generation_attempt > 1:
                file_messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"The previous generation for "
                            f"{filepath} did not contain "
                            f"complete source code.\n\n"
                            f"Generate the COMPLETE file again.\n"
                            f"Do not provide placeholders.\n"
                            f"Do not provide descriptions.\n"
                            f"Do not summarize code.\n"
                            f"Return actual executable source code."
                        ),
                    }
                )

            raw_file_response = call_llm(file_messages)

            try:

                parsed_response = extract_json_from_response(
                    raw_file_response
                )

                if not isinstance(parsed_response, dict):
                    raise ValueError(
                        f"Expected JSON object, got "
                        f"{type(parsed_response).__name__}"
                    )

                file_code = parsed_response.get("code")
                file_summary = parsed_response.get(
                    "summary",
                    "No summary provided."
                )

                if file_code is None:
                    raise ValueError(
                        "Missing required field: code"
                    )

                if not looks_like_real_code(
                    filepath,
                    file_code,
                ):
                    raise ValueError(
                        "Generated content does not appear "
                        "to be executable source code."
                    )

                workspace.write_file(
                    filepath,
                    file_code,
                )

                global_state[filepath] = file_summary

                print(f"✅ Saved {filepath}")

                success = True
                break

            except Exception as e:

                print(
                    f"⚠️ Generation attempt "
                    f"{generation_attempt}/"
                    f"{MAX_FILE_GENERATION_RETRIES} "
                    f"failed for {filepath}: {e}"
                )

                if (
                    generation_attempt
                    == MAX_FILE_GENERATION_RETRIES
                ):
                    print(
                        f"❌ Could not generate "
                        f"{filepath} after "
                        f"{MAX_FILE_GENERATION_RETRIES} "
                        f"attempts."
                    )

                    print(
                        "\nResponse Preview:\n"
                    )

                    print(
                        raw_file_response[:500]
                    )

        if not success:
            print(
                f"⚠️ Skipping file due to "
                f"generation failures: {filepath}"
            )

    # # ------------------------------------------------------------------
    # # 5. Phase 3: Execution + Auto Fix Loop
    # # ------------------------------------------------------------------

    # if execution_command:

    #     print(
    #         f"\n🖥️ Phase 3: Running execution command: "
    #         f"`{execution_command}`"
    #     )

    #     max_fix_attempts = MAX_FIX_ATTEMPTS
    #     patched_file_this_cycle = False
    #     for attempt in range(1, max_fix_attempts + 1):

    #     # Execution command is immutable after planning
    #         execution_command = original_execution_command

    #         exit_code, terminal_output = workspace.execute_command(
    #             execution_command
    #         )

    #         failure_markers = [
    #             "Traceback",
    #             "SyntaxError",
    #             "ModuleNotFoundError",
    #             "ImportError",
    #             "ValueError",
    #             "TypeError",
    #             "AttributeError",
    #         ]

    #         execution_success = (
    #             exit_code == 0
    #             and not any(
    #                 marker in terminal_output
    #                 for marker in failure_markers
    #             )
    #         )

    #         if execution_success:

    #             print(
    #                 f"✅ Execution successful!\n\n"
    #                 f"Terminal Output:\n{terminal_output}"
    #             )

    #             break

    #         print(
    #             f"⚠️ Execution failed "
    #             f"(Attempt {attempt}/{max_fix_attempts})"
    #         )

    #         preview = (
    #             terminal_output[-2000:]
    #             if len(terminal_output) > 2000
    #             else terminal_output
    #         )

    #         print(
    #             f"\nTerminal Output (last 2000 chars):\n"
    #             f"{preview}\n"
    #         )

    #         if attempt == max_fix_attempts:
    #             print(
    #                 "🛑 Max fix attempts reached. "
    #                 "Manual intervention required."
    #             )
    #             break

    #         print(
    #             "🛠️ Asking agent to analyze logs and "
    #             "generate a fix..."
    #         )

    #         fix_messages = get_error_fix_messages(
    #             requirements=user_prompt,
    #             tech_stack=tech_stack,
    #             execution_command=original_execution_command,
    #             error_log=terminal_output[-10000:],
    #             shared_context=global_state,
    #         )

    #         raw_fix_response = call_llm(fix_messages)

    #         try:
    #             fix_data = extract_json_from_response(
    #                 raw_fix_response
    #             )

    #             file_to_fix = fix_data.get("file_to_fix")
    #             fixed_code = fix_data.get("code")
    #             fix_summary = fix_data.get(
    #                 "summary",
    #                 "Auto-generated fix."
    #             )
    #             # new_cmd = fix_data.get("new_execution_command")

    #             # Apply File Fixes
    #             if file_to_fix and fixed_code:

    #                 workspace.write_file(
    #                     file_to_fix,
    #                     fixed_code
    #                 )

    #                 global_state[file_to_fix] = fix_summary

    #                 patched_file_this_cycle = True

    #                 print(
    #                     f"🩹 Patched {file_to_fix}\n"
    #                     f"Reason: {fix_summary}"
    #                 )

    #                 if STOP_AFTER_FIRST_FILE_PATCH:
    #                     print(
    #                         "\n⏹️ STOP_AFTER_FIRST_FILE_PATCH=True"
    #                         "\nStopping execution loop after first successful patch."
    #                     )
    #                     break
                
    #             # Apply Command Fixes
    #             # if new_cmd and new_cmd != execution_command:
    #             #     print(f"🔄 Agent updated execution command: `{execution_command}` -> `{new_cmd}`")
    #             #     execution_command = new_cmd
                
    #             # if not file_to_fix and not new_cmd:
    #             #     print("❌ Agent did not return a valid file to fix or a new command.")
    #             if not file_to_fix:
    #                 print(
    #                     "❌ Agent did not identify a file to fix."
    #                 )

    #         except Exception as e:
    #             print(
    #                 f"❌ Failed to apply auto-fix: {e}"
    #             )
    #         if patched_file_this_cycle:
    #             if not AUTO_RERUN_AFTER_FIX:

    #                 print(
    #                     "\n⏹️ AUTO_RERUN_AFTER_FIX=False"
    #                     "\nStopping after successful patch."
    #                 )

    #                 break

    # else:
    #     print(
    #         "\n⚠️ No execution command provided by planner. "
    #         "Skipping Phase 3."
    #     )


    if ENABLE_CODE_INDEXING:
        print(
            "\n🧠 Phase 4: Building Code Intelligence Index..."
        )

        try:

            editor = CodeEditor(workspace_dir)

            source_extensions = (
                ".py", ".js", ".ts", ".tsx", ".java", ".sql", 
                ".html", ".css", ".json", ".toml", ".md"
            )

            for filepath in files_to_build:

                if filepath.lower().endswith(
                    source_extensions
                ):

                    try:
                        editor.index_file(filepath)

                    except Exception as e:
                        print(
                            f"⚠️ Failed to index "
                            f"{filepath}: {e}"
                        )

        except Exception as e:
            print(
                f"⚠️ Code intelligence indexing failed: {e}"
            )


    # ------------------------------------------------------------------
    # Done
    # ------------------------------------------------------------------

    print("\n🎉 Agent Workflow Complete!")


# ----------------------------
# EDIT WORKFLOW
# ----------------------------
def run_code_editor():

    print(
        "🛠️ Supervisor routed to: "
        "RAG CODE EDITOR"
    )

    editor = CodeEditor(
        workspace_dir
    )

    editor.apply_edit(
        user_prompt
    )

# ----------------------------
# SUPERVISOR SWITCH
# ----------------------------
if intent == "CREATE":

    run_project_generation()

elif intent == "EDIT":

    run_code_editor()

else:

    print(
        f"❌ Unknown intent state: {intent}"
    )
