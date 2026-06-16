import ast
import hashlib
import os
import re
from typing import List, Dict

def get_ast_chunks(file_path: str, source_code: str) -> List[Dict]:
    """Parses a file and returns chunks based on the language."""
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.py':
        try:
            return _get_python_ast_chunks(file_path, source_code)
        except SyntaxError:
            return _get_generic_chunks(file_path, source_code)
            
    elif ext in ['.js', '.jsx', '.ts', '.tsx']:
        return _get_js_ts_chunks(file_path, source_code)
        
    else:
        return _get_generic_chunks(file_path, source_code)

def _get_python_ast_chunks(file_path: str, source_code: str) -> List[Dict]:
    tree = ast.parse(source_code)
    lines = source_code.splitlines()
    chunks = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", len(lines)) 
            content = "\n".join(lines[start - 1:end])
            content_hash = hashlib.md5(content.encode()).hexdigest()

            symbol_type = "class" if isinstance(node, ast.ClassDef) else "function"

            chunks.append({
                "chunk_id": f"{file_path}::{node.name}",
                "file_path": file_path,
                "language": "python",
                "start_line": start,
                "end_line": end,
                "symbol_name": node.name,
                "symbol_type": symbol_type,
                "content": content,
                "content_hash": content_hash
            })

            if isinstance(node, ast.ClassDef):
                for sub_node in node.body:
                    if isinstance(sub_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_start = sub_node.lineno
                        m_end = getattr(sub_node, "end_lineno", len(lines))
                        m_content = "\n".join(lines[m_start - 1:m_end])
                        m_hash = hashlib.md5(m_content.encode()).hexdigest()

                        chunks.append({
                            "chunk_id": f"{file_path}::{node.name}.{sub_node.name}",
                            "file_path": file_path,
                            "language": "python",
                            "start_line": m_start,
                            "end_line": m_end,
                            "symbol_name": f"{node.name}.{sub_node.name}",
                            "symbol_type": "method",
                            "content": m_content,
                            "content_hash": m_hash
                        })
    
    if not chunks:
        return _get_generic_chunks(file_path, source_code)
        
    return chunks

def _get_js_ts_chunks(file_path: str, source_code: str) -> List[Dict]:
    """Heuristic Brace-Matching parser for JavaScript, TypeScript, and React."""
    lines = source_code.splitlines()
    chunks = []
    
    # Matches: function name(), class Name, const name = () =>
    declaration_pattern = re.compile(
        r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class)\s+([a-zA-Z0-9_]+)'
        r'|^\s*(?:export\s+)?(?:default\s+)?(?:const|let|var)\s+([a-zA-Z0-9_]+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[^=]*)\s*=>'
    )
    
    i = 0
    global_start = None
    
    def push_global_chunk(end_idx):
        """Groups loose lines (like variable declarations/event listeners) into editable chunks."""
        nonlocal global_start
        if global_start is not None:
            start_line = global_start + 1
            end_line = end_idx
            content = "\n".join(lines[start_line-1:end_line]).strip()
            if content:
                chunks.append({
                    "chunk_id": f"{file_path}::global_scope_{start_line}_{end_line}",
                    "file_path": file_path,
                    "language": "javascript",
                    "start_line": start_line,
                    "end_line": end_line,
                    "symbol_name": f"global_{start_line}",
                    "symbol_type": "global_scope",
                    "content": "\n".join(lines[start_line-1:end_line]), # Keep original whitespace
                    "content_hash": hashlib.md5(content.encode()).hexdigest()
                })
            global_start = None

    while i < len(lines):
        line = lines[i]
        match = declaration_pattern.search(line)
        
        if match:
            # Package up any global variables we found BEFORE this function
            push_global_chunk(i) 
            
            symbol_name = match.group(1) or match.group(2)
            symbol_type = "class" if "class " in line else "function"
            
            start_line = i + 1
            open_braces = 0
            started = False
            end_line = start_line
            
            # Brace matcher to find the end of the function/class
            for j in range(i, len(lines)):
                # Strip strings and comments so we don't count fake braces
                clean_line = re.sub(r'//.*|/\*.*?\*/|".*?"|\'.*?\'|`.*?`', '', lines[j])
                
                open_braces += clean_line.count('{')
                open_braces -= clean_line.count('}')
                
                if '{' in clean_line:
                    started = True
                    
                if started and open_braces <= 0:
                    end_line = j + 1
                    break
            
            content = "\n".join(lines[start_line-1:end_line])
            chunks.append({
                "chunk_id": f"{file_path}::{symbol_name}",
                "file_path": file_path,
                "language": "javascript",
                "start_line": start_line,
                "end_line": end_line,
                "symbol_name": symbol_name,
                "symbol_type": symbol_type,
                "content": content,
                "content_hash": hashlib.md5(content.encode()).hexdigest()
            })
            i = end_line # Jump to the end of the function
        else:
            if global_start is None:
                global_start = i
            i += 1
            
    # Package up any leftover global variables at the bottom of the file
    push_global_chunk(i) 
    
    if not chunks:
        return _get_generic_chunks(file_path, source_code)
        
    return chunks

def _get_generic_chunks(file_path: str, source_code: str) -> List[Dict]:
    """Fallback chunker for unknown files (HTML, CSS, JSON)."""
    lines = source_code.splitlines()
    if not lines:
        return []
        
    content_hash = hashlib.md5(source_code.encode()).hexdigest()
    ext = os.path.splitext(file_path)[1].lower().replace('.', '')
    
    return [{
        "chunk_id": f"{file_path}::main",
        "file_path": file_path,
        "language": ext if ext else "unknown",
        "start_line": 1,
        "end_line": len(lines),
        "symbol_name": "main",
        "symbol_type": "file",
        "content": source_code,
        "content_hash": content_hash
    }]