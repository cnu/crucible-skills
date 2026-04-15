"""
Database migrations for file search functionality.
Creates search_documents table with FTS support for both SQLite and PostgreSQL.
"""

import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./api_keys.db")
IS_POSTGRES = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")


def run_migrations():
    """Run all database migrations for file search."""
    logger.info("Running file search database migrations...")
    
    if IS_POSTGRES:
        _run_postgres_migrations()
    else:
        _run_sqlite_migrations()
    
    logger.info("Migrations completed successfully")


def _run_postgres_migrations():
    """Run PostgreSQL-specific migrations."""
    import psycopg2
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    try:
        # Create search_documents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_documents (
                id SERIAL PRIMARY KEY,
                document_id VARCHAR(36) UNIQUE NOT NULL,
                tenant_id VARCHAR(36) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                file_type VARCHAR(50) NOT NULL,
                content_type VARCHAR(100),
                file_size INTEGER,
                extracted_text TEXT,
                parsed_data JSONB DEFAULT '{}',
                account_id VARCHAR(36),
                account_name VARCHAR(255),
                uploaded_by VARCHAR(36),
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                indexed_at TIMESTAMP,
                is_deleted BOOLEAN DEFAULT FALSE,
                search_vector tsvector
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_docs_tenant ON search_documents(tenant_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_docs_type ON search_documents(file_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_docs_account ON search_documents(account_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_docs_uploaded ON search_documents(uploaded_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_docs_doc_id ON search_documents(document_id)")
        
        # Create GIN index for full-text search
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_docs_fts 
            ON search_documents USING GIN(search_vector)
        """)
        
        # Create function to update search vector
        cursor.execute("""
            CREATE OR REPLACE FUNCTION update_search_vector()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.search_vector := 
                    setweight(to_tsvector('english', COALESCE(NEW.filename, '')), 'A') ||
                    setweight(to_tsvector('english', COALESCE(NEW.extracted_text, '')), 'B') ||
                    setweight(to_tsvector('english', COALESCE(NEW.account_name, '')), 'C');
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        
        # Create trigger to auto-update search vector
        cursor.execute("""
            DROP TRIGGER IF EXISTS trigger_update_search_vector ON search_documents;
            CREATE TRIGGER trigger_update_search_vector
                BEFORE INSERT OR UPDATE ON search_documents
                FOR EACH ROW
                EXECUTE FUNCTION update_search_vector();
        """)
        
        # Create search history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id SERIAL PRIMARY KEY,
                tenant_id VARCHAR(36) NOT NULL,
                user_id VARCHAR(36),
                query VARCHAR(500) NOT NULL,
                filters JSONB DEFAULT '{}',
                result_count INTEGER,
                clicked_result_id VARCHAR(36),
                searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_history_tenant ON search_history(tenant_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_history_searched ON search_history(searched_at)")
        
        conn.commit()
        logger.info("PostgreSQL migrations completed")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"PostgreSQL migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def _run_sqlite_migrations():
    """Run SQLite-specific migrations."""
    import sqlite3
    
    # Convert sqlite:///./path to proper path
    db_path = DATABASE_URL.replace("sqlite:///", "")
    
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Create search_documents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT UNIQUE NOT NULL,
                tenant_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                content_type TEXT,
                file_size INTEGER,
                extracted_text TEXT,
                parsed_data TEXT DEFAULT '{}',
                account_id TEXT,
                account_name TEXT,
                uploaded_by TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                indexed_at TIMESTAMP,
                is_deleted INTEGER DEFAULT 0
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_docs_tenant ON search_documents(tenant_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_docs_type ON search_documents(file_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_docs_account ON search_documents(account_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_docs_uploaded ON search_documents(uploaded_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_docs_doc_id ON search_documents(document_id)")
        
        # Check if FTS5 is available
        try:
            cursor.execute("SELECT fts5 FROM sqlite_master WHERE type='module' AND name='fts5'")
            fts5_available = cursor.fetchone() is not None
            
            if not fts5_available:
                # Try to enable FTS5
                cursor.execute("PRAGMA compile_options")
                compile_options = [row[0] for row in cursor.fetchall()]
                fts5_available = any('FTS5' in opt for opt in compile_options)
        except:
            fts5_available = False
        
        if fts5_available:
            # Create FTS5 virtual table for full-text search
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS search_documents_fts USING fts5(
                    filename,
                    extracted_text,
                    account_name,
                    content='search_documents',
                    content_rowid='id'
                )
            """)
            
            # Create triggers to keep FTS index in sync
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS search_docs_fts_insert 
                AFTER INSERT ON search_documents
                BEGIN
                    INSERT INTO search_documents_fts(rowid, filename, extracted_text, account_name)
                    VALUES (NEW.id, NEW.filename, NEW.extracted_text, NEW.account_name);
                END
            """)
            
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS search_docs_fts_update
                AFTER UPDATE ON search_documents
                BEGIN
                    INSERT INTO search_documents_fts(search_documents_fts, rowid, filename, extracted_text, account_name)
                    VALUES ('delete', OLD.id, OLD.filename, OLD.extracted_text, OLD.account_name);
                    INSERT INTO search_documents_fts(rowid, filename, extracted_text, account_name)
                    VALUES (NEW.id, NEW.filename, NEW.extracted_text, NEW.account_name);
                END
            """)
            
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS search_docs_fts_delete
                AFTER DELETE ON search_documents
                BEGIN
                    INSERT INTO search_documents_fts(search_documents_fts, rowid, filename, extracted_text, account_name)
                    VALUES ('delete', OLD.id, OLD.filename, OLD.extracted_text, OLD.account_name);
                END
            """)
            
            logger.info("FTS5 virtual table created for full-text search")
        else:
            logger.warning("FTS5 not available, using LIKE-based search fallback")
        
        # Create search history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                user_id TEXT,
                query TEXT NOT NULL,
                filters TEXT DEFAULT '{}',
                result_count INTEGER,
                clicked_result_id TEXT,
                searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_history_tenant ON search_history(tenant_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_history_searched ON search_history(searched_at)")
        
        conn.commit()
        logger.info("SQLite migrations completed")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"SQLite migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def verify_migrations():
    """Verify that all migrations have been applied."""
    if IS_POSTGRES:
        return _verify_postgres_migrations()
    else:
        return _verify_sqlite_migrations()


def _verify_postgres_migrations():
    """Verify PostgreSQL migrations."""
    import psycopg2
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    try:
        # Check if search_documents table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'search_documents'
            )
        """)
        search_docs_exists = cursor.fetchone()[0]
        
        # Check if indexes exist
        cursor.execute("""
            SELECT COUNT(*) FROM pg_indexes 
            WHERE tablename = 'search_documents'
        """)
        index_count = cursor.fetchone()[0]
        
        return {
            "search_documents_table": search_docs_exists,
            "index_count": index_count,
            "migrations_complete": search_docs_exists and index_count >= 5
        }
        
    finally:
        cursor.close()
        conn.close()


def _verify_sqlite_migrations():
    """Verify SQLite migrations."""
    import sqlite3
    
    db_path = DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    
    try:
        # Check if search_documents table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='search_documents'
        """)
        search_docs_exists = cursor.fetchone() is not None
        
        # Check if FTS table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='search_documents_fts'
        """)
        fts_exists = cursor.fetchone() is not None
        
        # Check index count
        cursor.execute("""
            SELECT COUNT(*) FROM sqlite_master 
            WHERE type='index' AND tbl_name='search_documents'
        """)
        index_count = cursor.fetchone()[0]
        
        return {
            "search_documents_table": search_docs_exists,
            "fts_table": fts_exists,
            "index_count": index_count,
            "migrations_complete": search_docs_exists and index_count >= 5
        }
        
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
    
    # Verify
    status = verify_migrations()
    print(f"\nMigration status: {status}")
