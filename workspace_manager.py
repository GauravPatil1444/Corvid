import os
import json
import subprocess
import threading
import queue
from pathlib import Path
from typing import Dict, Any, Optional

class WorkspaceManager:
    def __init__(self, root_dir: str = "."):
        """Initializes the workspace and state file."""
        self.root_dir = Path(root_dir).resolve()
        self.state_file = self.root_dir / ".workspace_state.json"
        self.active_services = {}
        self.log_queue = queue.Queue()
        
        self.root_dir.mkdir(parents=True, exist_ok=True)
        if not self.state_file.exists():
            self.sync_state()

    def _get_safe_path(self, relative_path: str) -> Path:
        target_path = (self.root_dir / relative_path).resolve()
        if self.root_dir not in target_path.parents and target_path != self.root_dir:
            raise PermissionError(f"Access denied: {relative_path} is outside the workspace.")
        return target_path

    def load_corvid_config(self) -> dict:
        """Loads corvid.json for automated services and triggers."""
        config_path = self.root_dir / "corvid.json"
        if config_path.exists():
            with open(config_path, "r") as f:
                return json.load(f)
        return {}

    def sync_state(self) -> Dict[str, Any]:
        """Crawls the directory to build a tree representation and saves it to JSON."""
        def build_tree(dir_path: Path) -> Dict[str, Any]:
            tree = {}
            for item in dir_path.iterdir():
                if item.name.startswith(".") or item.name in ["node_modules", "__pycache__", "venv"]:
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

    def _stream_reader(self, pipe, service_name: str):
        with pipe:
            for line in iter(pipe.readline, ''):
                self.log_queue.put(f"[{service_name}] {line.strip()}")

    def start_service(self, service_name: str, command: str, relative_cwd: str = "."):
        """Spawns a non-blocking background service."""
        target_dir = self._get_safe_path(relative_cwd)
        print(f"🚀 Starting {service_name} in {target_dir}...")
        
        process = subprocess.Popen(
            command, cwd=target_dir, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        self.active_services[service_name] = process
        
        thread = threading.Thread(target=self._stream_reader, args=(process.stdout, service_name))
        thread.daemon = True
        thread.start()

    def stop_all_services(self):
        for name, process in self.active_services.items():
            print(f"🛑 Stopping {name}...")
            process.terminate()
        self.active_services.clear()

    def get_recent_logs(self) -> str:
        logs = []
        while not self.log_queue.empty():
            logs.append(self.log_queue.get_nowait())
        return "\n".join(logs)

    def execute_command(self, command: str, relative_cwd: str = ".", timeout: int = 15) -> tuple[int, str]:
        """Executes a blocking terminal command (Trigger)."""
        target_dir = self._get_safe_path(relative_cwd)
        try:
            result = subprocess.run(
                command, cwd=target_dir, shell=True,
                capture_output=True, text=True, timeout=timeout
            )
            return result.returncode, (result.stdout + "\n" + result.stderr).strip()
        except subprocess.TimeoutExpired as e:
            return 0, f"[Process timed out after {timeout}s]\n{(e.stdout or '') + (e.stderr or '')}".strip()
        except Exception as e:
            return -1, str(e)

    def read_file(self, relative_path: str) -> str:
        with open(self._get_safe_path(relative_path), "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, relative_path: str, content: str):
        safe_path = self._get_safe_path(relative_path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(content)
        self.sync_state()