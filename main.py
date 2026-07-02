import os
import sys
import argparse
from code_editor import CodeEditor
from workspace_manager import WorkspaceManager

# Simplified: We only care about file mapping now
def get_source_files(directory: str) -> list:
    source_files = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "venv", "__pycache__"} and not d.startswith('.')]
        for file in files:
            if file.startswith('.') or file in {"corvid.json", "package-lock.json"}: continue
            if file.lower().endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".html")):
                source_files.append(os.path.relpath(os.path.join(root, file), directory).replace("\\", "/"))
    return source_files

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Corvid Local")
    parser.add_argument("command", choices=["start"])
    args = parser.parse_args()

    current_workspace = os.environ.get("TARGET_WORKSPACE", os.getcwd())
    workspace = WorkspaceManager(current_workspace)
    config = workspace.load_corvid_config()
    
    # Spin up background services
    if "services" in config:
        for s_name, s_conf in config["services"].items():
            workspace.start_service(s_name, s_conf.get("cmd"), s_conf.get("cwd", "."))

    editor = CodeEditor(current_workspace)
    print(f"\n🦅 Corvid Local active in: {current_workspace}")
    
    try:
        while True:
            user_input = input("\n💬 What changes should I make?\n> ")
            if user_input.lower().strip() in ['exit', 'quit']: break
            editor.apply_edit(user_input, trigger_config=config.get("trigger"))
    finally:
        workspace.stop_all_services()