from sentence_transformers import SentenceTransformer
from db_manager import DatabaseManager
from ast_chunker import get_ast_chunks
from prompt import get_verification_messages, get_edit_messages, get_chunk_summary_messages
from llm_manager import call_llm
from workspace_manager import WorkspaceManager
from utils.json_utils import extract_json_from_response

class CodeEditor:
    def __init__(self, workspace_dir: str):
        self.db = DatabaseManager()
        self.workspace = WorkspaceManager(workspace_dir)
        # Using a fast, local 1024-dimension embedding model
        self.encoder = SentenceTransformer('BAAI/bge-large-en-v1.5') 

    def index_file(self, file_path: str):
        """Extracts AST chunks, summarizes, embeds, and stores them in PGVector."""
        source_code = self.workspace.read_file(file_path)
        chunks = get_ast_chunks(file_path, source_code)

        for chunk in chunks:
            existing_hash = self.db.get_chunk_hash(chunk["chunk_id"])
            if existing_hash == chunk["content_hash"]:
                print(f"⏭️ Skipping (Unchanged): {chunk['chunk_id']}")
                continue 

            print(f"🔄 Embedding changed/new chunk: {chunk['chunk_id']}")
            # 1. Generate Summary
            summary_msg = get_chunk_summary_messages(chunk['content'])
            chunk['summary'] = call_llm(summary_msg).strip()
            
            # 2. Generate Embedding
            chunk['embedding'] = self.encoder.encode(chunk['summary'] + " " + chunk['content']).tolist()
            
            # 3. Upsert
            self.db.upsert_chunk(chunk)
            print(f"Indexed chunk: {chunk['chunk_id']}")

    def apply_edit(self, user_query: str):
        """The full retrieval, verification, and patching pipeline."""
        print(f"🔍 Embedding query: '{user_query}'")
        query_emb = self.encoder.encode(user_query).tolist()
        
        # 1. Vector Search
        candidates = self.db.search_similar_chunks(query_emb, limit=5)
        
        # 2. Relevance Verification Layer
        target_chunk = None
        for candidate in candidates:
            verify_msgs = get_verification_messages(user_query, candidate)
            raw_response = call_llm(verify_msgs)
            try:
                verification = extract_json_from_response(raw_response)
            except ValueError as e:
                print(f"⚠️ Verification LLM failed to return valid JSON. Skipping chunk")
                continue # Safely skip to the next chunk instead of crashing!
            
            if verification.get("relevant") and verification.get("confidence", 0) > 0.8:
                print(f"🎯 LLM verified chunk {candidate['chunk_id']} as target.")
                target_chunk = candidate
                break
        
        if not target_chunk:
            print("❌ No relevant chunks found to edit.")
            return

        # 3. Patch Generation
        print(f"✍️ Generating patch for {target_chunk['chunk_id']}...")
        edit_msgs = get_edit_messages(user_query, target_chunk)
        
        MAX_RETRIES = 3
        edit_data = None
        
        for attempt in range(1, MAX_RETRIES + 1):
            raw_edit = call_llm(edit_msgs)
            
            # Safely extract JSON
            try:
                edit_data = extract_json_from_response(raw_edit)
                break  # Success! Escape the retry loop.
            except ValueError as e:
                print(f"⚠️ Attempt {attempt}/{MAX_RETRIES} failed: Invalid JSON. Retrying...")
                if attempt == MAX_RETRIES:
                    print("❌ Max retries reached. Aborting edit.")
                    return
            
        updated_code = edit_data.get("updated_chunk")
        
        if not updated_code:
            print("❌ Failed to extract 'updated_chunk' from JSON payload.")
            return
            
        # Unescape flattened LLM strings BEFORE splicing
        if "\\n" in updated_code:
            updated_code = updated_code.replace("\\n", "\n").replace("\\t", "\t")
      
        # 4. Patch Application (Line Splicing)
        file_path = target_chunk['file_path']
        full_source = self.workspace.read_file(file_path).splitlines()
        
        start = target_chunk['start_line'] - 1
        end = target_chunk['end_line']
        
        # Splice the new chunk in place of the old lines
        new_source = full_source[:start] + updated_code.splitlines() + full_source[end:]
        final_code = "\n".join(new_source)
        
        self.workspace.write_file(file_path, final_code)
        print(f"✅ Successfully patched {file_path}")

        # 5. Re-index the modified file to sync AST line numbers
        print("🔄 Re-indexing modified file...")
        self.index_file(file_path)