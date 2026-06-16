import json
import re

# from llm_manager import call_llm
# from prompt import get_intent_messages


def extract_json_from_response(text: str):
    """
    Extract the first valid JSON object or array from an LLM response.

    Handles:
    - Markdown code fences
    - Explanatory text
    - Literal newlines inside JSON string values
    - Large source code payloads
    """

    # ---------------------------------------------------------
    # Helper: sanitize invalid control characters inside strings
    # ---------------------------------------------------------
    def sanitize_json_text(raw_text: str) -> str:
        result = []

        in_string = False
        escaped = False

        for ch in raw_text:

            if escaped:
                result.append(ch)
                escaped = False
                continue

            if ch == "\\":
                result.append(ch)
                escaped = True
                continue

            if ch == '"':
                result.append(ch)
                in_string = not in_string
                continue

            if in_string:
                if ch == "\n":
                    result.append("\\n")
                    continue

                if ch == "\r":
                    continue

                if ch == "\t":
                    result.append("\\t")
                    continue

            result.append(ch)

        return "".join(result)

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

        sanitized = sanitize_json_text(block)

        try:
            return json.loads(sanitized)
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

                # NEW: sanitize invalid control chars
                candidate = sanitize_json_text(candidate)

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


def is_documentation_file(filepath: str) -> bool:
    """
    Files that should contain documentation rather than source code.
    """
    filepath = filepath.lower()

    return filepath.endswith(
        (
            ".md",
            ".rst",
            ".txt",
        )
    )


def looks_like_real_code(filepath: str, code: str) -> bool:
    """
    Lightweight heuristic to determine whether generated content
    is likely actual source code rather than a description.
    """

    if not code:
        return False

    filename = filepath.split("/")[-1]

    # Documentation files
    if is_documentation_file(filepath):
        return (
            "#" in code
            or "##" in code
            or len(code.splitlines()) >= 5
        )

    # Gitignore files
    if filename == ".gitignore":
        return len(code.strip()) > 0
    

    # Allow empty __init__.py files
    if filename == "__init__.py":
        return True

    code = code.strip()

    if len(code) < 50:
        return False

    extension = filepath.split(".")[-1].lower()

    indicators = {
        "py": [
            "def ",
            "class ",
            "import ",
            "from ",
            "if __name__",
            "=",
        ],
        "js": [
            "function ",
            "const ",
            "let ",
            "export ",
            "import ",
            "=>",
        ],
        "html": [
            "<html",
            "<body",
            "<head",
            "<div",
            "<!DOCTYPE",
        ],
        "css": [
            "{",
            "}",
            ":",
            ";",
        ],
        "json": [
            "{",
            "}",
        ],
        "toml": [
            "[",
            "=",
        ],
    }

    expected = indicators.get(extension)

    if expected:
        return any(token in code for token in expected)

    return len(code.splitlines()) >= 3
