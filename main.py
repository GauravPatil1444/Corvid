import os
import sys
from code_editor import CodeEditor

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
# WORKSPACE_DIR = "./my_existing_project" # Point this to the codebase you want to debug

# Directories we absolutely do NOT want to vectorize
IGNORE_DIRS = {
    "node_modules", "__pycache__", "venv", "env", "dist", 
    "build", "public","coverage", "out", "target", "bin", "obj", "tmp"
}

# ---------------------------------------------------------
# NEW: Specific auto-generated or heavy files to ignore
# ---------------------------------------------------------
IGNORE_FILES = {
    "package-lock.json", "package.json","yarn.lock", "pnpm-lock.yaml", 
    "poetry.lock", "Pipfile.lock", "Cargo.lock", 
    ".DS_Store", "thumbs.db"
}

# Only parse files that contain human-readable code
VALID_EXTENSIONS = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".sql", 
    ".html", ".css", ".toml", ".yaml", ".yml"
)

def get_source_files(directory: str) -> list:
    """Crawls the directory and returns a list of valid source code files."""
    if not os.path.exists(directory):
        print(f"❌ Error: Directory '{directory}' does not exist.")
        sys.exit(1)

    source_files = []
    for root, dirs, files in os.walk(directory):
        # Aggressively prune the directory tree in-place
        dirs[:] = [
            d for d in dirs 
            if d not in IGNORE_DIRS 
            and not d.startswith('.')
        ]
        
        for file in files:
            if file.startswith('.') or file in IGNORE_FILES:
                continue
                
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
    import argparse
    
    # 1. Setup command line arguments
    parser = argparse.ArgumentParser(description="Corvid AI Debugger")
    parser.add_argument("command", choices=["start", "init"], help="Initialize the AI in the current directory")
    args = parser.parse_args()

    import os
    
    # 2. Dynamically grab the directory passed from the batch file!
    # (If run directly via python without the .bat, it safely falls back to os.getcwd)
    current_workspace = os.environ.get("TARGET_WORKSPACE", os.getcwd())
    
    print(f"\n🦅 Corvid AI initializing in: {current_workspace}")
    
    # 3. Vectorize the current directory (skips unchanged files automatically!)
    run_indexer(current_workspace)
    
    # 4. Start the interactive chat loop
    print("\n" + "="*50)
    print("Ready! Type your bug or feature request below.")
    print("Type 'exit' or 'quit' to close the assistant.")
    print("="*50)
    
    while True:
        try:
            # Get the user prompt
            user_input = input("\n💬 What changes should I make?\n> ")
            
            # Handle exit commands
            if user_input.lower().strip() in ['exit', 'quit']:
                print("🦅 Corvid powering down. Goodbye!")
                break
                
            # Skip empty inputs
            if not user_input.strip():
                continue
                
            # Trigger the debugger
            run_debugger(current_workspace, user_input)
            
        except KeyboardInterrupt:
            # Gracefully handle Ctrl+C
            print("\n🦅 Corvid powering down. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ An unexpected error occurred: {e}")