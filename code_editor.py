import ast
from sentence_transformers import SentenceTransformer
from db_manager import DatabaseManager
from ast_chunker import get_ast_chunks
from prompt import get_planner_messages, get_verification_messages, get_edit_messages, get_chunk_summary_messages
from llm_manager import call_llm
from workspace_manager import WorkspaceManager
from utils.json_utils import extract_json_from_response

class CodeEditor:
    def __init__(self, workspace_dir: str):
        self.db = DatabaseManager()
        self.workspace = WorkspaceManager(workspace_dir)
        self.encoder = SentenceTransformer('BAAI/bge-large-en-v1.5')

    def index_file(self, file_path: str):
        source_code = self.workspace.read_file(file_path)
        chunks = get_ast_chunks(file_path, source_code)
        seen_chunk_ids = set()

        for chunk in chunks:
            seen_chunk_ids.add(chunk["chunk_id"])
            if self.db.get_chunk_hash(chunk["chunk_id"]) == chunk["content_hash"]:
                continue 

            print(f"🔄 Indexing: {chunk['chunk_id']}")
            summary_msg = get_chunk_summary_messages(chunk['content'])
            chunk['summary'] = call_llm(summary_msg).strip()
            chunk['embedding'] = self.encoder.encode(chunk['summary'] + " " + chunk['content']).tolist()
            self.db.upsert_chunk(chunk)

        self.db.prune_stale_chunks(file_path, seen_chunk_ids)

    def get_edit_context(self, file_path: str, target_chunk: dict) -> str:
        full_source = self.workspace.read_file(file_path).splitlines()
        import_lines = [l for l in full_source[:30] if l.startswith(("import ", "from ", "#")) or not l.strip()]
        return "\n".join(import_lines)

    def apply_edit(self, user_query: str, trigger_config: dict = None):
        print(f"🔍 Analyzing: '{user_query}'")
        
        # 1. PLANNER PHASE
        workspace_map = self.workspace.sync_state()
        raw_plan = call_llm(get_planner_messages(user_query, workspace_map))
        try:
            target_files = extract_json_from_response(raw_plan)
        except:
            print("⚠️ Planner mapping failed. Proceeding without file constraints.")
            target_files = [None] # Fallback to standard global search

        print(f"🗺️ Target files: {target_files}")

        # 2. SEQUENTIAL EDITOR PHASE
        for target_file in target_files:
            if target_file:
                print(f"\n🎯 Focusing on {target_file}...")
                query_emb = self.encoder.encode(f"{user_query} Target file: {target_file}").tolist()
                candidates = [c for c in self.db.search_similar_chunks(query_emb, limit=10) if c['file_path'] == target_file]
            else:
                query_emb = self.encoder.encode(user_query).tolist()
                candidates = self.db.search_similar_chunks(query_emb, limit=10)

            target_chunk = None
            for candidate in candidates:
                verify_msgs = get_verification_messages(user_query, candidate)
                try:
                    ver = extract_json_from_response(call_llm(verify_msgs))
                    if ver.get("relevant") and ver.get("confidence", 0) >= 0.7:
                        target_chunk = candidate
                        break
                except: continue

            if not target_chunk:
                print(f"⏭️ No semantic targets verified in {target_file}.")
                continue

            # 3. ACTOR-CRITIC LOOP
            file_path = target_chunk['file_path']
            full_source = self.workspace.read_file(file_path).splitlines()
            start, end = target_chunk['start_line'] - 1, target_chunk['end_line']
            file_context = self.get_edit_context(file_path, target_chunk)
            
            feedback = ""
            execution_log = "No previous runs."
            
            for attempt in range(1, 4):
                if feedback:
                    print(f"⚠️ Attempt {attempt - 1} failed. Re-evaluating with feedback.")
                
                edit_msgs = get_edit_messages(user_query, target_chunk, file_context, execution_log)
                if feedback:
                    edit_msgs.append({"role": "user", "content": f"Previous attempt rejected: {feedback}. Fix and retry."})

                try:
                    edit_data = extract_json_from_response(call_llm(edit_msgs))
                    candidate_code = edit_data.get("updated_chunk", "").replace("\\n", "\n").replace("\\t", "\t")
                except Exception as e:
                    feedback = f"JSON extraction failed: {e}"
                    continue

                # Critic Phase A: Syntax Check
                if file_path.endswith('.py'):
                    try:
                        ast.parse(candidate_code)
                        test_splice = full_source[:start] + candidate_code.splitlines() + full_source[end:]
                        ast.parse("\n".join(test_splice))
                    except SyntaxError as e:
                        feedback = f"SyntaxError line {e.lineno}: {e.msg}"
                        continue

                # Critic Phase B: Execution Validation
                new_source = full_source[:start] + candidate_code.splitlines() + full_source[end:]
                final_code = "\n".join(new_source)
                self.workspace.write_file(file_path, final_code) # Temporarily write to disk

                if trigger_config:
                    print("🧪 Running execution trigger...")
                    exit_code, log = self.workspace.execute_command(trigger_config.get("cmd"), trigger_config.get("cwd", "."))
                    execution_log = f"Exit Code: {exit_code}\nOutput:\n{log}"
                    
                    if exit_code != 0:
                        feedback = "Trigger execution failed. Read the execution logs."
                        self.workspace.write_file(file_path, "\n".join(full_source)) # Rollback
                        continue

                print(f"✅ Successfully patched {file_path}. Justification: {edit_data.get('justification')}")
                self.index_file(file_path)
                break