import os
import sys
from code_editor import CodeEditor

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
WORKSPACE_DIR = "./my_existing_project" # Point this to the codebase you want to debug

# Directories we absolutely do NOT want to vectorize
IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", 
    "env", "dist", "build", ".idea", ".vscode", "coverage"
}

# Only parse files that contain human-readable code
VALID_EXTENSIONS = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".sql", 
    ".html", ".css", ".json", ".yaml", ".yml"
)

def get_source_files(directory: str) -> list:
    """Crawls the directory and returns a list of valid source code files."""
    if not os.path.exists(directory):
        print(f"❌ Error: Directory '{directory}' does not exist.")
        sys.exit(1)

    source_files = []
    for root, dirs, files in os.walk(directory):
        # Mutate the dirs list in-place to ignore heavy folders like node_modules
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        for file in files:
            if file.lower().endswith(VALID_EXTENSIONS):
                # Get the full path first
                full_path = os.path.join(root, file)
                
                # Strip the base workspace directory so CodeEditor gets a clean relative path
                rel_path = os.path.relpath(full_path, directory)
                
                # Normalize slashes for consistency in the DB
                clean_path = rel_path.replace("\\", "/")
                source_files.append(clean_path)
                
    return source_files

def run_indexer(workspace_dir: str):
    """Phase 1: Maps the existing project and updates the Vector DB."""
    print(f"\n🔍 Phase 1: Crawling workspace '{workspace_dir}'...")
    files_to_index = get_source_files(workspace_dir)
    print(f"📋 Found {len(files_to_index)} source files.")
    
    print("\n🧠 Phase 2: Building/Updating Code Intelligence Index...")
    editor = CodeEditor(workspace_dir)
    for filepath in files_to_index:
        try:
            editor.index_file(filepath)
        except Exception as e:
            print(f"⚠️ Failed to index {filepath}: {e}")
    print("✅ Codebase indexed successfully!")

def run_debugger(workspace_dir: str, bug_report: str):
    """Phase 3: Finds the relevant chunks and applies the fix."""
    print(f"\n🛠️ Phase 3: AI Debugger activated...")
    print(f"🐞 User Query/Error Log:\n{bug_report}\n")
    
    editor = CodeEditor(workspace_dir)
    editor.apply_edit(bug_report)

if __name__ == "__main__":
    # ------------------------------------------------------------------
    # 1. Update the index with the latest state of your local files
    # ------------------------------------------------------------------
    # (Note: Because your DB uses UPSERT, running this repeatedly is fast and safe. 
    # It will only update chunks that have actually changed.)
    run_indexer(WORKSPACE_DIR)
    
    # ------------------------------------------------------------------
    # 2. Feed the error log or change request to the RAG Editor
    # ------------------------------------------------------------------
    bug_request = """
    Choice: 7
Report exported
Report exported
why is this printed two times only display single time
    """
    
    run_debugger(WORKSPACE_DIR, bug_request)