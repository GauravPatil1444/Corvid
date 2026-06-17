import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2 import sql
from urllib.parse import urlparse
from pgvector.psycopg2 import register_vector
from typing import List, Dict, Any

class DatabaseManager:
    def __init__(self, db_url="postgresql://postgres:postgres@localhost:5433/code_db"):
        self.db_url = db_url
        self._ensure_database_exists()
        
        # Now connect to the actual target database
        self.conn = psycopg2.connect(self.db_url)
        
        # 1. Initialize tables and CREATE EXTENSION vector FIRST
        self.init_db()
        
        # 2. THEN register the vector type with psycopg2
        register_vector(self.conn)

    def get_chunk_hash(self, chunk_id: str) -> str:
        """Retrieves the hash of an existing chunk to see if it changed."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT content_hash FROM code_chunks WHERE chunk_id = %s", (chunk_id,))
            result = cur.fetchone()
            return result[0] if result else None

    def _ensure_database_exists(self):
        """
        Connects to the default 'postgres' database to check if the target 
        database exists, and creates it if it doesn't.
        """
        parsed = urlparse(self.db_url)
        db_name = parsed.path.lstrip('/')
        
        # Swap the target database for the default 'postgres' database to issue the CREATE command
        default_db_url = parsed._replace(path='/postgres').geturl()
        
        try:
            # Connect to the default database
            conn = psycopg2.connect(default_db_url)
            
            # CREATE DATABASE cannot run inside a transaction block, so we must enable autocommit
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            
            with conn.cursor() as cur:
                # Check if our target database exists
                cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (db_name,))
                exists = cur.fetchone()
                
                if not exists:
                    print(f"🛠️ Database '{db_name}' does not exist. Creating it automatically...")
                    # Safe parameterization for database names
                    cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
            
            conn.close()
        except Exception as e:
            print(f"⚠️ Warning: Could not auto-create database '{db_name}'. Error: {e}")

    def init_db(self):
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS code_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    language TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    symbol_name TEXT,
                    symbol_type TEXT,
                    summary TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    embedding VECTOR(1024),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS code_symbols (
                    symbol_id TEXT PRIMARY KEY,
                    symbol_name TEXT NOT NULL,
                    symbol_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    parent_symbol TEXT,
                    dependencies JSONB
                );
            """)
        self.conn.commit()

    def upsert_chunk(self, chunk_data: Dict[str, Any]):
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO code_chunks 
                (chunk_id, file_path, language, start_line, end_line, symbol_name, symbol_type, summary, content, content_hash, embedding)
                VALUES (%(chunk_id)s, %(file_path)s, %(language)s, %(start_line)s, %(end_line)s, %(symbol_name)s, %(symbol_type)s, %(summary)s, %(content)s, %(content_hash)s, %(embedding)s)
                ON CONFLICT (chunk_id) DO UPDATE SET
                    start_line = EXCLUDED.start_line,
                    end_line = EXCLUDED.end_line,
                    summary = EXCLUDED.summary,
                    content = EXCLUDED.content,
                    content_hash = EXCLUDED.content_hash,
                    embedding = EXCLUDED.embedding,
                    updated_at = CURRENT_TIMESTAMP;
            """, chunk_data)
        self.conn.commit()

    def search_similar_chunks(self, query_embedding: List[float], limit: int = 10) -> List[Dict]:
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT chunk_id, file_path, start_line, end_line, symbol_name, summary, content 
                FROM code_chunks 
                ORDER BY embedding <=> %s::vector 
                LIMIT %s;
            """, (query_embedding, limit))
            
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]