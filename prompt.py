# Phase 1: Architecture Planning
PLANNING_SYSTEM_PROMPT = """
You are a software architect. Convert the user's requirements into a JSON project structure.
Do NOT write the actual code. The values for all files in the structure should simply be the string "file".

You must output a single JSON object with three keys:
1. "tech_stack": A brief description of the technologies used.
2. "execution_command": The terminal command to run or validate the project (e.g., "node src/index.js", "python src/main.py").
3. "structure": The directory tree mapping.

Example:
{{
    "tech_stack": "Node.js",
    "execution_command": "node index.js",
    "structure": {{
        "src": {{
            "index.js": "file",
            "utils.js": "file"
        }},
        "package.json": "file"
    }}
}}
"""

def get_planning_messages(requirements: str) -> list:
    return [
        {"role": "system", "content": PLANNING_SYSTEM_PROMPT},
        {"role": "user", "content": f"Requirements: {requirements}"}
    ]

# Phase 2: Stateful File Generation
FILE_GENERATION_PROMPT = """
You are an expert developer building a project piece by piece.
Return ONLY valid JSON. Do not wrap the response in markdown.

The response schema is:
{{
    "code": "...",
    "summary": "..."
}}

Context of what has been built so far:
{shared_context}

Project Requirements:
{requirements}

Target File to Write:
{target_file}
"""

def get_file_generation_messages(requirements: str, target_file: str, shared_context: dict) -> list:
    context_str = "\n".join([f"- {path}: {summary}" for path, summary in shared_context.items()])
    if not context_str:
        context_str = "No files built yet. You are the first file."

    system_content = FILE_GENERATION_PROMPT.format(
        shared_context=context_str,
        requirements=requirements,
        target_file=target_file
    )
    
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": f"Generate the code and summary for {target_file}."}
    ]

# Phase 3: Error Fixing
ERROR_FIX_PROMPT = """
You are an expert debugger. The code we generated failed when we ran the execution command.

Project Requirements: {requirements}
Tech Stack: {tech_stack}
Command Run: {execution_command}

Terminal Output / Error Log (Truncated):
{error_log}

Context of files built so far:
{shared_context}

Analyze the error. If a file is broken, rewrite the file. If the execution command is wrong (e.g. pointing to the wrong directory), provide a corrected command.

Output ONLY valid JSON matching this schema. Do not include markdown blocks.
{{
    "file_to_fix": "path/to/the/broken/file.ext", 
    "code": "The COMPLETE rewritten code for this file. Leave empty if only the command needs changing.",
    "summary": "Brief explanation of what you fixed",
    "new_execution_command": "Provide a new terminal command ONLY IF the current one is wrong. Otherwise, leave empty."
}}
"""

def get_error_fix_messages(requirements: str, tech_stack: str, execution_command: str, error_log: str, shared_context: dict) -> list:
    # 1. Truncate the shared context to the last 10 files to prevent 413 limits
    recent_context = dict(list(shared_context.items())[-10:])
    context_str = "\n".join([f"- {path}: {summary}" for path, summary in recent_context.items()])
    
    # 2. Truncate the error log to the last 2000 characters to prevent 413 limits
    truncated_log = error_log[-2000:] if len(error_log) > 2000 else error_log

    system_content = ERROR_FIX_PROMPT.format(
        requirements=requirements,
        tech_stack=tech_stack,
        execution_command=execution_command,
        error_log=truncated_log,
        shared_context=context_str
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": "Fix the error and return the JSON payload."}
    ]