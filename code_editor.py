import ast
import re
from prompt import get_architect_messages, get_edit_messages
from llm_manager import call_llm_structured, call_local_llm
from schemas import ArchitectPlan, EditorAction
from workspace_manager import WorkspaceManager

class CodeEditor:
    def __init__(self, workspace_dir: str):
        self.workspace = WorkspaceManager(workspace_dir)

    def apply_edit(self, user_query: str, trigger_config: dict = None):
        # 1. ARCHITECT PHASE
        workspace_map = self.workspace.sync_state()
        plan = call_llm_structured(get_architect_messages(user_query, workspace_map), ArchitectPlan)

        # 2. FULL-FILE EXECUTION PHASE
        for task in plan.tasks:
            print(f"\n🎯 Task: {task.task_description}")
            full_source = self.workspace.read_file(task.filepath)
            
            # Use local Qwen 3b for editing (Full Context)
            edit_msgs = get_edit_messages(task.task_description, full_source)
            
            # ReAct Loop
            success = False
            for attempt in range(5):
                action = call_local_llm(edit_msgs) # Returns EditorAction object
                
                if action.action == "patch":
                    new_code = action.updated_chunk
                    
                    # Atomic Syntax Critic (Python)
                    if task.filepath.endswith('.py'):
                        try: ast.parse(new_code)
                        except SyntaxError as e:
                            edit_msgs.append({"role": "user", "content": f"Syntax Error: {e}. Fix it."})
                            continue
                            
                    self.workspace.write_file(task.filepath, new_code)
                    
                    # Execution Validation
                    if trigger_config:
                        code, log = self.workspace.execute_command(trigger_config['cmd'])
                        if code != 0:
                            edit_msgs.append({"role": "user", "content": f"Trigger failed: {log}. Rollback."})
                            continue
                    
                    print(f"✅ Applied changes to {task.filepath}")
                    success = True
                    break
            
            if not success: print(f"❌ Failed to fix {task.filepath}")