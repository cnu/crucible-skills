"""
Document Store Module
Handles saving and retrieving documents for search functionality.
Supports both SQLite and PostgreSQL with tenant isolation.
"""

import os
import uuid
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./api_keys.db")
IS_POSTGRES = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")


@dataclass
class StoredDocument:
    """Represents a stored document."""
    id: int
    document_id: str
    tenant_id: str
    filename: str
    file_type: str
    content_type: Optional[str]
    file_size: Optional[int]
    extracted_text: Optional[str]
    parsed_data: Dict[str, Any]
    account_id: Optional[str]
    account_name: Optional[str]
    uploaded_by: Optional[str]
    uploaded_at: datetime
    indexed_at: Optional[datetime]
    is_deleted: bool


class DocumentStore:
    """Manages document storage and retrieval with tenant isolation."""
    
    def __init__(self, db_url: str = None):
        self.db_url = db_url or DATABASE_URL
        self.is_postgres = self.db_url.startswith(("postgresql://", "postgres://"))
        self._connection = None
    
    def _get_connection(self):
        """Get or create database connection."""
        if self._connection is None:
            if self.is_postgres:
                import psycopg2
                self._connection = psycopg2.connect(self.db_url)
            else:
                import sqlite3
                db_path = self.db_url.replace("sqlite:///", "")
                self._connection = sqlite3.connect(db_path, check_same_thread=False)
                self._connection.row_factory = sqlite3.Row
        return self._connection
    
    def save_document(self,
                     tenant_id: str,
                     filename: str,
                     file_type: str,
                     extracted_text: str,
                     parsed_data: Dict[str, Any],
                     content_type: str = None,
                     file_size: int = None,
                     account_id: str = None,
                     account_name: str = None,
                     uploaded_by: str = None) -> str:
        """
        Save a document to the database.
        
        Args:
            tenant_id: Tenant identifier for isolation
            filename: Original filename
            file_type: Type of file (contract, invoice, call_transcript, note, pdf)
            extracted_text: Full text extracted from document
            parsed_data: Structured data extracted (JSON serializable)
            content_type: MIME type
            file_size: File size in bytes
            account_id: Associated account ID
            account_name: Account name for display/search
            uploaded_by: User ID who uploaded
            
        Returns:
            document_id: Unique identifier for the document
        """
        document_id = str(uuid.uuid4())
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if self.is_postgres:
                cursor.execute("""
                    INSERT INTO search_documents 
                    (document_id, tenant_id, filename, file_type, content_type, file_size,
                     extracted_text, parsed_data, account_id, account_name, uploaded_by, indexed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """, (document_id, tenant_id, filename, file_type, content_type, file_size,
                      extracted_text, json.dumps(parsed_data), account_id, account_name, uploaded_by))
            else:
                cursor.execute("""
                    INSERT INTO search_documents 
                    (document_id, tenant_id, filename, file_type, content_type, file_size,
                     extracted_text, parsed_data, account_id, account_name, uploaded_by, indexed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (document_id, tenant_id, filename, file_type, content_type, file_size,
                      extracted_text, json.dumps(parsed_data), account_id, account_name, uploaded_by))
            
            conn.commit()
            logger.info(f"Document saved: {document_id} ({filename})")
            return document_id
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save document: {e}")
            raise
        finally:
            cursor.close()
    
    def get_document(self, document_id: str, tenant_id: str) -> Optional[StoredDocument]:
        """
        Get a document by ID with tenant isolation.
        
        Args:
            document_id: Document UUID
            tenant_id: Tenant identifier for isolation
            
        Returns:
            StoredDocument or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if self.is_postgres:
                cursor.execute("""
                    SELECT id, document_id, tenant_id, filename, file_type, content_type,
                           file_size, extracted_text, parsed_data, account_id, account_name,
                           uploaded_by, uploaded_at, indexed_at, is_deleted
                    FROM search_documents
                    WHERE document_id = %s AND tenant_id = %s AND is_deleted = FALSE
                """, (document_id, tenant_id))
            else:
                cursor.execute("""
                    SELECT id, document_id, tenant_id, filename, file_type, content_type,
                           file_size, extracted_text, parsed_data, account_id, account_name,
                           uploaded_by, uploaded_at, indexed_at, is_deleted
                    FROM search_documents
                    WHERE document_id = ? AND tenant_id = ? AND is_deleted = 0
                """, (document_id, tenant_id))
            
            row = cursor.fetchone()
            
            if row:
                return StoredDocument(
                    id=row[0],
                    document_id=row[1],
                    tenant_id=row[2],
                    filename=row[3],
                    file_type=row[4],
                    content_type=row[5],
                    file_size=row[6],
                    extracted_text=row[7],
                    parsed_data=json.loads(row[8]) if row[8] else {},
                    account_id=row[9],
                    account_name=row[10],
                    uploaded_by=row[11],
                    uploaded_at=row[12],
                    indexed_at=row[13],
                    is_deleted=bool(row[14])
                )
            return None
            
        finally:
            cursor.close()
    
    def delete_document(self, document_id: str, tenant_id: str, soft_delete: bool = True) -> bool:
        """
        Delete a document (soft or hard delete).
        
        Args:
            document_id: Document UUID
            tenant_id: Tenant identifier for isolation
            soft_delete: If True, mark as deleted; if False, permanently delete
            
        Returns:
            True if deleted, False if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if soft_delete:
                if self.is_postgres:
                    cursor.execute("""
                        UPDATE search_documents 
                        SET is_deleted = TRUE 
                        WHERE document_id = %s AND tenant_id = %s
                    """, (document_id, tenant_id))
                else:
                    cursor.execute("""
                        UPDATE search_documents 
                        SET is_deleted = 1 
                        WHERE document_id = ? AND tenant_id = ?
                    """, (document_id, tenant_id))
            else:
                if self.is_postgres:
                    cursor.execute("""
                        DELETE FROM search_documents 
                        WHERE document_id = %s AND tenant_id = %s
                    """, (document_id, tenant_id))
                else:
                    cursor.execute("""
                        DELETE FROM search_documents 
                        WHERE document_id = ? AND tenant_id = ?
                    """, (document_id, tenant_id))
            
            conn.commit()
            deleted = cursor.rowcount > 0
            
            if deleted:
                logger.info(f"Document {'soft ' if soft_delete else ''}deleted: {document_id}")
            
            return deleted
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete document: {e}")
            raise
        finally:
            cursor.close()
    
    def list_documents(self, 
                      tenant_id: str,
                      file_type: str = None,
                      account_id: str = None,
                      limit: int = 100,
                      offset: int = 0) -> List[StoredDocument]:
        """
        List documents with optional filtering.
        
        Args:
            tenant_id: Tenant identifier for isolation
            file_type: Filter by file type (optional)
            account_id: Filter by account ID (optional)
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            List of StoredDocument objects
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            query = """
                SELECT id, document_id, tenant_id, filename, file_type, content_type,
                       file_size, extracted_text, parsed_data, account_id, account_name,
                       uploaded_by, uploaded_at, indexed_at, is_deleted
                FROM search_documents
                WHERE tenant_id = ? AND is_deleted = 0
            """
            params = [tenant_id]
            
            if file_type:
                query += " AND file_type = ?"
                params.append(file_type)
            
            if account_id:
                query += " AND account_id = ?"
                params.append(account_id)
            
            query += " ORDER BY uploaded_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            if self.is_postgres:
                query = query.replace("?", "%s")
                query = query.replace("is_deleted = 0", "is_deleted = FALSE")
            
            cursor.execute(query, params)
            
            documents = []
            for row in cursor.fetchall():
                documents.append(StoredDocument(
                    id=row[0],
                    document_id=row[1],
                    tenant_id=row[2],
                    filename=row[3],
                    file_type=row[4],
                    content_type=row[5],
                    file_size=row[6],
                    extracted_text=row[7],
                    parsed_data=json.loads(row[8]) if row[8] else {},
                    account_id=row[9],
                    account_name=row[10],
                    uploaded_by=row[11],
                    uploaded_at=row[12],
                    indexed_at=row[13],
                    is_deleted=bool(row[14])
                ))
            
            return documents
            
        finally:
            cursor.close()
    
    def update_document(self,
                       document_id: str,
                       tenant_id: str,
                       **kwargs) -> bool:
        """
        Update a document's metadata.
        
        Args:
            document_id: Document UUID
            tenant_id: Tenant identifier for isolation
            **kwargs: Fields to update (filename, account_name, etc.)
            
        Returns:
            True if updated, False if not found
        """
        allowed_fields = ['filename', 'account_name', 'account_id', 'file_type', 'parsed_data']
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates:
            return False
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            set_clauses = []
            params = []
            
            for field, value in updates.items():
                if field == 'parsed_data' and isinstance(value, dict):
                    value = json.dumps(value)
                set_clauses.append(f"{field} = ?")
                params.append(value)
            
            params.extend([document_id, tenant_id])
            
            query = f"""
                UPDATE search_documents 
                SET {', '.join(set_clauses)}, indexed_at = CURRENT_TIMESTAMP
                WHERE document_id = ? AND tenant_id = ?
            """
            
            if self.is_postgres:
                query = query.replace("?", "%s")
            
            cursor.execute(query, params)
            conn.commit()
            
            updated = cursor.rowcount > 0
            if updated:
                logger.info(f"Document updated: {document_id}")
            
            return updated
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update document: {e}")
            raise
        finally:
            cursor.close()
    
    def get_statistics(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get document statistics for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary with statistics
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if self.is_postgres:
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN is_deleted THEN 1 END) as deleted,
                        COUNT(DISTINCT file_type) as file_types,
                        COUNT(DISTINCT account_id) as accounts,
                        SUM(file_size) as total_size
                    FROM search_documents
                    WHERE tenant_id = %s
                """, (tenant_id,))
            else:
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN is_deleted = 1 THEN 1 ELSE 0 END) as deleted,
                        COUNT(DISTINCT file_type) as file_types,
                        COUNT(DISTINCT account_id) as accounts,
                        SUM(file_size) as total_size
                    FROM search_documents
                    WHERE tenant_id = ?
                """, (tenant_id,))
            
            row = cursor.fetchone()
            
            return {
                "total_documents": row[0],
                "deleted_documents": row[1] or 0,
                "file_types": row[2] or 0,
                "accounts": row[3] or 0,
                "total_size_bytes": row[4] or 0
            }
            
        finally:
            cursor.close()


# Singleton instance for reuse
_document_store = None


def get_document_store() -> DocumentStore:
    """Get or create singleton DocumentStore instance."""
    global _document_store
    if _document_store is None:
        _document_store = DocumentStore()
    return _document_store
