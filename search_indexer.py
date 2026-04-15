"""
Search Indexer Module
Handles asynchronous indexing of documents for full-text search.
Uses Celery for background task processing.
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Celery configuration
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# Try to import Celery, but provide fallback if not available
try:
    from celery import Celery
    celery_app = Celery('search_indexer', broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    celery_app = None
    logger.warning("Celery not available, using synchronous indexing fallback")


class SearchIndexer:
    """Manages search indexing operations."""
    
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL", "sqlite:///./api_keys.db")
        self.is_postgres = self.db_url.startswith(("postgresql://", "postgres://"))
    
    def _get_connection(self):
        """Get database connection."""
        if self.is_postgres:
            import psycopg2
            return psycopg2.connect(self.db_url)
        else:
            import sqlite3
            db_path = self.db_url.replace("sqlite:///", "")
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return conn
    
    def index_document(self, document_id: str, tenant_id: str) -> bool:
        """
        Index a document for search (synchronous version).
        
        Args:
            document_id: Document UUID
            tenant_id: Tenant identifier
            
        Returns:
            True if indexed successfully
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Update indexed_at timestamp
            if self.is_postgres:
                cursor.execute("""
                    UPDATE search_documents 
                    SET indexed_at = CURRENT_TIMESTAMP
                    WHERE document_id = %s AND tenant_id = %s
                """, (document_id, tenant_id))
            else:
                cursor.execute("""
                    UPDATE search_documents 
                    SET indexed_at = CURRENT_TIMESTAMP
                    WHERE document_id = ? AND tenant_id = ?
                """, (document_id, tenant_id))
            
            conn.commit()
            
            indexed = cursor.rowcount > 0
            if indexed:
                logger.info(f"Document indexed: {document_id}")
            
            cursor.close()
            conn.close()
            
            return indexed
            
        except Exception as e:
            logger.error(f"Failed to index document {document_id}: {e}")
            return False
    
    def search(self,
             query: str,
             tenant_id: str,
             file_type: str = None,
             account_id: str = None,
             date_from: str = None,
             date_to: str = None,
             limit: int = 20) -> Dict[str, Any]:
        """
        Search documents using full-text search.
        
        Args:
            query: Search query string
            tenant_id: Tenant identifier for isolation
            file_type: Filter by file type
            account_id: Filter by account ID
            date_from: Start date (ISO format)
            date_to: End date (ISO format)
            limit: Maximum results
            
        Returns:
            Dictionary with results and metadata
        """
        start_time = datetime.utcnow()
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Build search query based on database type
            if self.is_postgres:
                results = self._search_postgres(
                    cursor, query, tenant_id, file_type, account_id,
                    date_from, date_to, limit
                )
            else:
                results = self._search_sqlite(
                    cursor, query, tenant_id, file_type, account_id,
                    date_from, date_to, limit
                )
            
            cursor.close()
            conn.close()
            
            processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            return {
                "success": True,
                "query": query,
                "total": len(results),
                "results": results,
                "processing_time_ms": round(processing_time, 2)
            }
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return {
                "success": False,
                "query": query,
                "error": str(e),
                "total": 0,
                "results": [],
                "processing_time_ms": 0
            }
    
    def _search_postgres(self, cursor, query: str, tenant_id: str,
                        file_type: str = None, account_id: str = None,
                        date_from: str = None, date_to: str = None,
                        limit: int = 20) -> list:
        """Execute search using PostgreSQL full-text search."""
        
        # Convert query to tsquery
        tsquery = ' & '.join(query.split())
        
        sql = """
            SELECT 
                document_id,
                filename,
                file_type,
                account_name,
                uploaded_at,
                ts_rank(search_vector, plainto_tsquery('english', %s)) as score,
                ts_headline('english', extracted_text, plainto_tsquery('english', %s),
                    'StartSel=<mark>, StopSel=</mark>, MaxWords=50, MinWords=10'
                ) as highlight
            FROM search_documents
            WHERE tenant_id = %s
                AND is_deleted = FALSE
                AND search_vector @@ plainto_tsquery('english', %s)
        """
        params = [query, query, tenant_id, query]
        
        if file_type:
            sql += " AND file_type = %s"
            params.append(file_type)
        
        if account_id:
            sql += " AND account_id = %s"
            params.append(account_id)
        
        if date_from:
            sql += " AND uploaded_at >= %s"
            params.append(date_from)
        
        if date_to:
            sql += " AND uploaded_at <= %s"
            params.append(date_to)
        
        sql += " ORDER BY score DESC LIMIT %s"
        params.append(limit)
        
        cursor.execute(sql, params)
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "document_id": row[0],
                "filename": row[1],
                "file_type": row[2],
                "account_name": row[3],
                "uploaded_at": row[4].isoformat() if row[4] else None,
                "score": float(row[5]) if row[5] else 0,
                "highlight": row[6] or ""
            })
        
        return results
    
    def _search_sqlite(self, cursor, query: str, tenant_id: str,
                      file_type: str = None, account_id: str = None,
                      date_from: str = None, date_to: str = None,
                      limit: int = 20) -> list:
        """Execute search using SQLite FTS or LIKE fallback."""
        
        # Check if FTS5 is available
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='search_documents_fts'")
            fts_available = cursor.fetchone() is not None
        except:
            fts_available = False
        
        if fts_available:
            # Use FTS5 for full-text search
            sql = """
                SELECT 
                    d.document_id,
                    d.filename,
                    d.file_type,
                    d.account_name,
                    d.uploaded_at,
                    d.extracted_text,
                    rank
                FROM search_documents_fts fts
                JOIN search_documents d ON d.id = fts.rowid
                WHERE fts MATCH ?
                    AND d.tenant_id = ?
                    AND d.is_deleted = 0
            """
            params = [query, tenant_id]
            
            if file_type:
                sql += " AND d.file_type = ?"
                params.append(file_type)
            
            if account_id:
                sql += " AND d.account_id = ?"
                params.append(account_id)
            
            if date_from:
                sql += " AND d.uploaded_at >= ?"
                params.append(date_from)
            
            if date_to:
                sql += " AND d.uploaded_at <= ?"
                params.append(date_to)
            
            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)
            
            cursor.execute(sql, params)
            
            results = []
            for row in cursor.fetchall():
                # Create simple highlight from extracted_text
                text = row[5] or ""
                highlight = self._create_highlight(text, query)
                
                results.append({
                    "document_id": row[0],
                    "filename": row[1],
                    "file_type": row[2],
                    "account_name": row[3],
                    "uploaded_at": row[4],
                    "score": 1.0,  # FTS5 doesn't provide score
                    "highlight": highlight
                })
            
            return results
        
        else:
            # Fallback to LIKE-based search
            sql = """
                SELECT 
                    document_id,
                    filename,
                    file_type,
                    account_name,
                    uploaded_at,
                    extracted_text
                FROM search_documents
                WHERE tenant_id = ?
                    AND is_deleted = 0
                    AND (
                        filename LIKE ? 
                        OR extracted_text LIKE ?
                        OR account_name LIKE ?
                    )
            """
            
            search_pattern = f"%{query}%"
            params = [tenant_id, search_pattern, search_pattern, search_pattern]
            
            if file_type:
                sql += " AND file_type = ?"
                params.append(file_type)
            
            if account_id:
                sql += " AND account_id = ?"
                params.append(account_id)
            
            if date_from:
                sql += " AND uploaded_at >= ?"
                params.append(date_from)
            
            if date_to:
                sql += " AND uploaded_at <= ?"
                params.append(date_to)
            
            sql += " ORDER BY uploaded_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(sql, params)
            
            results = []
            for row in cursor.fetchall():
                text = row[5] or ""
                highlight = self._create_highlight(text, query)
                
                results.append({
                    "document_id": row[0],
                    "filename": row[1],
                    "file_type": row[2],
                    "account_name": row[3],
                    "uploaded_at": row[4],
                    "score": 0.5,  # Default score for LIKE search
                    "highlight": highlight
                })
            
            return results
    
    def _create_highlight(self, text: str, query: str, max_length: int = 200) -> str:
        """Create a highlighted snippet from text."""
        if not text:
            return ""
        
        # Find query position
        query_lower = query.lower()
        text_lower = text.lower()
        pos = text_lower.find(query_lower)
        
        if pos == -1:
            # Query not found, return beginning
            return text[:max_length] + "..." if len(text) > max_length else text
        
        # Extract snippet around match
        start = max(0, pos - 50)
        end = min(len(text), pos + len(query) + 150)
        
        snippet = text[start:end]
        
        # Add ellipsis if truncated
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        
        # Highlight the query
        highlighted = snippet.replace(
            text[pos:pos+len(query)],
            f"<mark>{text[pos:pos+len(query)]}</mark>"
        )
        
        return highlighted
    
    def get_filter_options(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get available filter options for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary with filter options
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Get file types
            if self.is_postgres:
                cursor.execute("""
                    SELECT DISTINCT file_type, COUNT(*) as count
                    FROM search_documents
                    WHERE tenant_id = %s AND is_deleted = FALSE
                    GROUP BY file_type
                    ORDER BY count DESC
                """, (tenant_id,))
            else:
                cursor.execute("""
                    SELECT DISTINCT file_type, COUNT(*) as count
                    FROM search_documents
                    WHERE tenant_id = ? AND is_deleted = 0
                    GROUP BY file_type
                    ORDER BY count DESC
                """, (tenant_id,))
            
            file_types = [{"type": row[0], "count": row[1]} for row in cursor.fetchall()]
            
            # Get accounts
            if self.is_postgres:
                cursor.execute("""
                    SELECT DISTINCT account_id, account_name, COUNT(*) as count
                    FROM search_documents
                    WHERE tenant_id = %s 
                        AND is_deleted = FALSE
                        AND account_id IS NOT NULL
                    GROUP BY account_id, account_name
                    ORDER BY count DESC
                    LIMIT 100
                """, (tenant_id,))
            else:
                cursor.execute("""
                    SELECT DISTINCT account_id, account_name, COUNT(*) as count
                    FROM search_documents
                    WHERE tenant_id = ? 
                        AND is_deleted = 0
                        AND account_id IS NOT NULL
                    GROUP BY account_id, account_name
                    ORDER BY count DESC
                    LIMIT 100
                """, (tenant_id,))
            
            accounts = [{"id": row[0], "name": row[1], "count": row[2]} for row in cursor.fetchall()]
            
            cursor.close()
            conn.close()
            
            return {
                "file_types": file_types,
                "accounts": accounts
            }
            
        except Exception as e:
            logger.error(f"Failed to get filter options: {e}")
            return {"file_types": [], "accounts": []}


# Celery tasks
if CELERY_AVAILABLE:
    @celery_app.task(bind=True, max_retries=3)
    def index_document_task(self, document_id: str, tenant_id: str):
        """Celery task to index a document asynchronously."""
        indexer = SearchIndexer()
        
        try:
            success = indexer.index_document(document_id, tenant_id)
            if success:
                return {"status": "success", "document_id": document_id}
            else:
                raise Exception("Indexing failed")
        except Exception as exc:
            logger.error(f"Index task failed for {document_id}: {exc}")
            # Retry with exponential backoff
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


# Singleton instance
_indexer = None


def get_search_indexer() -> SearchIndexer:
    """Get or create singleton SearchIndexer instance."""
    global _indexer
    if _indexer is None:
        _indexer = SearchIndexer()
    return _indexer


def queue_document_indexing(document_id: str, tenant_id: str) -> bool:
    """
    Queue a document for indexing.
    Uses Celery if available, otherwise indexes synchronously.
    
    Args:
        document_id: Document UUID
        tenant_id: Tenant identifier
        
    Returns:
        True if queued/indexed successfully
    """
    if CELERY_AVAILABLE:
        try:
            index_document_task.delay(document_id, tenant_id)
            logger.info(f"Document indexing queued: {document_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to queue indexing: {e}")
            # Fall back to synchronous
            indexer = get_search_indexer()
            return indexer.index_document(document_id, tenant_id)
    else:
        indexer = get_search_indexer()
        return indexer.index_document(document_id, tenant_id)
