import os
import json
from pathlib import Path
from typing import Dict, Any, Optional

class WorkspaceManager:
    def __init__(self, root_dir: str = "./agent_workspace"):
        """Initializes the workspace and state file."""
        self.root_dir = Path(root_dir).resolve()
        self.state_file = self.root_dir / ".workspace_state.json"
        
        # Ensure root directory exists
        self.root_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize or load the state
        if not self.state_file.exists():
            self.sync_state()

    def _get_safe_path(self, relative_path: str) -> Path:
        """Prevents path traversal attacks by ensuring paths stay within root."""
        target_path = (self.root_dir / relative_path).resolve()
        if self.root_dir not in target_path.parents and target_path != self.root_dir:
            raise PermissionError(f"Access denied: {relative_path} is outside the workspace.")
        return target_path

    def sync_state(self) -> Dict[str, Any]:
        """Crawls the directory to build a tree representation and saves it to JSON."""
        def build_tree(dir_path: Path) -> Dict[str, Any]:
            tree = {}
            for item in dir_path.iterdir():
                # Ignore the state file itself and hidden Git/env folders
                if item.name == ".workspace_state.json" or item.name.startswith((".git", "__pycache__")):
                    continue
                if item.is_dir():
                    tree[item.name] = build_tree(item)
                else:
                    tree[item.name] = "file"
            return tree

        current_state = build_tree(self.root_dir)
        
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(current_state, f, indent=4)
            
        return current_state

    def create_structure(self, structure: Dict[str, Any], base_path: Optional[Path] = None):
        """
        Recursively creates folders and files from a dictionary.
        Expected format: {"src": {"main.py": "print('hello')", "utils": {}}}
        """
        target_base = base_path or self.root_dir

        for name, content in structure.items():
            path = target_base / name
            
            if isinstance(content, dict):
                # It's a directory
                path.mkdir(parents=True, exist_ok=True)
                self.create_structure(content, path)
            elif isinstance(content, str):
                # It's a file
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)

        self.sync_state()

    def read_file(self, relative_path: str) -> str:
        """Reads a file's content to feed back to the LLM."""
        safe_path = self._get_safe_path(relative_path)
        if not safe_path.is_file():
            raise FileNotFoundError(f"File not found: {relative_path}")
        
        with open(safe_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, relative_path: str, content: str):
        """Overwrites or creates a new file, then updates state."""
        safe_path = self._get_safe_path(relative_path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        self.sync_state()