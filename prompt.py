# Phase 0: Supervisor / Intent Routing

INTENT_PROMPT = """
Analyze the user's request and determine their intent.
If they want to build, scaffold, or create a new project/script from scratch, return "CREATE".
If they are asking to change, modify, fix, update, or refactor an existing project, return "EDIT".

Output ONLY a JSON object matching this schema. Do not include markdown fences. Ensure the key is wrapped in double quotes.
{{
    "intent": "CREATE" | "EDIT"
}}

User Request: {user_prompt}
"""

def get_intent_messages(user_prompt: str) -> list:
    return [
        {"role": "system", "content": "You are an intent router. Output only valid JSON."},
        {"role": "user", "content": INTENT_PROMPT.format(user_prompt=user_prompt)}
    ]


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

CRITICAL JSON RULES:
1. Output ONLY a single, valid JSON object. Do NOT output a JSON array/list.
2. The "code" value MUST have all internal double quotes escaped (e.g., \\"string\\").
3. The "code" value MUST have all newlines explicitly escaped as \\n. Do not output literal newlines inside the JSON string.
4. If writing Python, use explicit relative imports (e.g., `from .utils import X`) or absolute imports from the root.

The response schema is:
{{
    "code": "The complete, properly escaped source code for this file.",
    "summary": "Brief technical summary of what was written."
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
        {"role": "user", "content": f"Generate the code and summary for {target_file}. Remember to explicitly escape all quotes and newlines inside the JSON."}
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

Analyze the error and determine which file is causing the failure.

IMPORTANT RULES:
1. The execution command is LOCKED and must NEVER be changed.
2. Do NOT suggest changes to the workspace structure.
3. Do NOT suggest uv init, npm init, pip install, uv add, poetry install, or any environment setup commands.
4. Fix ONLY project source files or configuration files already present in the generated project.
5. If multiple files may be involved, choose the file most likely responsible for the error.

Output ONLY valid JSON matching this schema. Do not include markdown blocks.

{{
    "file_to_fix": "path/to/the/broken/file.ext",
    "code": "The COMPLETE rewritten code for this file",
    "summary": "Brief explanation of what was fixed"
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

# Safety Layer: Context Summarization
CONTEXT_SUMMARIZATION_PROMPT = """
You are an AI context compressor. The input text exceeds token limits and must be aggressively summarized without losing critical technical data.

CRITICAL RULES:
1. Preserve all file paths, class names, function signatures, and exact error tracebacks.
2. Remove conversational filler, redundant instructions, and obvious boilerplate descriptions.
3. Condense the history of generated files into a dense technical map.

Output ONLY the compressed text.
"""

def get_summarization_messages(long_text: str) -> list:
    return [
        {"role": "system", "content": CONTEXT_SUMMARIZATION_PROMPT},
        {"role": "user", "content": f"COMPRESS THIS TEXT:\n\n{long_text}"}
    ]


# 1. Chunk Summarization (For indexing)
CHUNK_SUMMARY_PROMPT = """
Analyze this code chunk and provide a brief technical summary.
Describe its purpose, business role, and side effects.
Return ONLY the summary string, no markdown.
Code:
{content}
"""

def get_chunk_summary_messages(content: str) -> list:
    return [{"role": "user", "content": CHUNK_SUMMARY_PROMPT.format(content=content)}]

# 2. Relevance Verification Layer
VERIFICATION_PROMPT = """
User Request: {query}
Retrieved Chunk ({chunk_id}):
{content}
Summary: {summary}

Determine whether this specific chunk MUST be modified to fulfill the user request.
Output JSON format:
{{
    "relevant": true/false,
    "confidence": 0.0-1.0,
    "reason": "..."
}}
"""

def get_verification_messages(query: str, chunk: dict) -> list:
    return [{"role": "user", "content": VERIFICATION_PROMPT.format(
        query=query, chunk_id=chunk['chunk_id'], content=chunk['content'], summary=chunk['summary']
    )}]

# 3. Patch Editing
EDIT_CHUNK_PROMPT = """
User Request: {query}
Chunk ID: {chunk_id}
File: {file_path}

Current Chunk:
{content}

RULES:
1. Modify ONLY this chunk to satisfy the request.
2. Preserve external interfaces and indentation.
3. Output ONLY valid JSON containing the complete replacement code. 
4. CRITICAL: You MUST return the ENTIRE, complete replacement chunk. Do NOT use placeholders like `// ... rest of code` or ``. If the chunk is an entire file, you must output the entire updated file.

Output JSON format:
{{
    "chunk_id": "{chunk_id}",
    "updated_chunk": "..."
}}
"""

def get_edit_messages(query: str, chunk: dict) -> list:
    return [{"role": "user", "content": EDIT_CHUNK_PROMPT.format(
        query=query, chunk_id=chunk['chunk_id'], file_path=chunk['file_path'], content=chunk['content']
    )}]

