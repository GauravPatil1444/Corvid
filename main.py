import os
import sys
import argparse
from code_editor import CodeEditor
from workspace_manager import WorkspaceManager

IGNORE_DIRS = {"node_modules", "__pycache__", "venv", "env", "dist", "build", "coverage", ".git"}
IGNORE_FILES = {"package-lock.json", "yarn.lock", "poetry.lock", "corvid.json"}
VALID_EXTENSIONS = (".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".html", ".css", ".json")

def get_source_files(directory: str) -> list:
    source_files = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith('.')]
        for file in files:
            if file.startswith('.') or file in IGNORE_FILES: continue
            if file.lower().endswith(VALID_EXTENSIONS):
                source_files.append(os.path.relpath(os.path.join(root, file), directory).replace("\\", "/"))
    return source_files

def run_indexer(workspace_dir: str):
    print(f"\n🔍 Phase 1: Crawling workspace...")
    files = get_source_files(workspace_dir)
    print("\n🧠 Phase 2: Updating Code Intelligence Index...")
    editor = CodeEditor(workspace_dir)
    for f in files: editor.index_file(f)
    print("✅ Indexing complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Corvid AI Debugger")
    parser.add_argument("command", choices=["start", "init"])
    args = parser.parse_args()

    current_workspace = os.environ.get("TARGET_WORKSPACE", os.getcwd())
    print(f"\n🦅 Corvid AI initializing in: {current_workspace}")
    
    workspace = WorkspaceManager(current_workspace)
    config = workspace.load_corvid_config()
    
    # Spin up background services
    if "services" in config:
        for s_name, s_conf in config["services"].items():
            workspace.start_service(s_name, s_conf.get("cmd"), s_conf.get("cwd", "."))

    run_indexer(current_workspace)
    editor = CodeEditor(current_workspace)

    print("\n" + "="*50)
    print("Ready! Type your bug or feature request below.")
    print("="*50)
    
    try:
        while True:
            user_input = input("\n💬 What changes should I make?\n> ")
            if user_input.lower().strip() in ['exit', 'quit']: break
            if not user_input.strip(): continue
            
            # Pass the trigger dynamically to the editor
            editor.apply_edit(user_input, trigger_config=config.get("trigger"))
            
    except KeyboardInterrupt: pass
    finally:
        print("\n🦅 Corvid powering down. Stopping services...")
        workspace.stop_all_services()