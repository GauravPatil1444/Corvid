# Phase 1: Architecture Planning
PLANNING_SYSTEM_PROMPT = """
You are a software architect. Convert the user's requirements into a JSON project structure.
Do NOT write the actual code. The values for all files should simply be the string "file".

Example:
{
    "src": {
        "main.py": "file",
        "utils.py": "file"
    },
    "requirements.txt": "file"
}
"""

def get_planning_messages(requirements: str) -> list:
    return [
        {"role": "system", "content": PLANNING_SYSTEM_PROMPT},
        {"role": "user", "content": f"Requirements: {requirements}"}
    ]

# Phase 2: Stateful File Generation
FILE_GENERATION_PROMPT = """
You are an expert developer building a project piece by piece.

Return ONLY valid JSON.

Do not wrap the response in markdown.
Do not include explanations.
Do not include code fences.

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
    # Convert context dict to a readable string for the LLM
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