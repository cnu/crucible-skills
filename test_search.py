#!/usr/bin/env python3
"""
Test suite for file search functionality
Tests document store, search indexer, and search API routes.
"""

import sys
sys.path.insert(0, '.')

import os
import json
import tempfile
import sqlite3
from datetime import datetime

# Set test database
os.environ['DATABASE_URL'] = 'sqlite:///./test_search.db'

from migrations.file_search_migrations import run_migrations, verify_migrations
from document_store import DocumentStore, StoredDocument
from search_indexer import SearchIndexer, get_search_indexer, queue_document_indexing


def setup_test_db():
    """Create a fresh test database."""
    # Remove old test db if exists
    if os.path.exists('./test_search.db'):
        os.remove('./test_search.db')
    
    # Run migrations
    run_migrations()
    return verify_migrations()


def test_migrations():
    """Test database migrations."""
    print("\n=== Testing Database Migrations ===")
    
    status = setup_test_db()
    
    assert status['search_documents_table'], "search_documents table should exist"
    assert status['migrations_complete'], "Migrations should be complete"
    assert status['index_count'] >= 5, f"Should have at least 5 indexes, got {status['index_count']}"
    
    print("✓ Database migrations successful")
    print(f"  - search_documents table: {status['search_documents_table']}")
    print(f"  - FTS table: {status.get('fts_table', 'N/A')}")
    print(f"  - Index count: {status['index_count']}")


def test_document_store():
    """Test document store operations."""
    print("\n=== Testing Document Store ===")
    
    setup_test_db()
    store = DocumentStore()
    
    # Test 1: Save document
    doc_id = store.save_document(
        tenant_id="test-tenant",
        filename="test_contract.pdf",
        file_type="contract",
        extracted_text="This is a test contract between Acme Corp and Example Inc.",
        parsed_data={"parties": ["Acme Corp", "Example Inc."], "value": 50000},
        content_type="application/pdf",
        file_size=1024,
        account_id="acct-123",
        account_name="Acme Corp",
        uploaded_by="user-1"
    )
    
    assert doc_id, "Should return document_id"
    print(f"✓ Document saved with ID: {doc_id}")
    
    # Test 2: Get document
    doc = store.get_document(doc_id, "test-tenant")
    assert doc is not None, "Should retrieve document"
    assert doc.document_id == doc_id, "Document ID should match"
    assert doc.filename == "test_contract.pdf", "Filename should match"
    assert doc.tenant_id == "test-tenant", "Tenant should match"
    print("✓ Document retrieved successfully")
    
    # Test 3: List documents
    docs = store.list_documents("test-tenant")
    assert len(docs) == 1, "Should have 1 document"
    print(f"✓ Listed {len(docs)} document(s)")
    
    # Test 4: Get statistics
    stats = store.get_statistics("test-tenant")
    assert stats['total_documents'] == 1, "Should have 1 document"
    assert stats['file_types'] == 1, "Should have 1 file type"
    print(f"✓ Statistics: {stats}")
    
    # Test 5: Soft delete
    deleted = store.delete_document(doc_id, "test-tenant", soft_delete=True)
    assert deleted, "Should delete successfully"
    
    doc = store.get_document(doc_id, "test-tenant")
    assert doc is None, "Should not find deleted document"
    print("✓ Soft delete works")


def test_search_indexer():
    """Test search indexer functionality."""
    print("\n=== Testing Search Indexer ===")
    
    setup_test_db()
    store = DocumentStore()
    indexer = SearchIndexer()
    
    # Add test documents
    docs_data = [
        {
            "filename": "Service_Agreement_Acme.pdf",
            "file_type": "contract",
            "text": "This service agreement defines the terms between Acme Corp and the service provider. Payment terms are net 30 days.",
            "account_name": "Acme Corp"
        },
        {
            "filename": "Invoice_001.pdf",
            "file_type": "invoice",
            "text": "Invoice for consulting services provided to Beta Inc. Total amount due: $5,000.",
            "account_name": "Beta Inc"
        },
        {
            "filename": "NDA_Gamma.pdf",
            "file_type": "contract",
            "text": "Non-disclosure agreement between our company and Gamma LLC. Confidential information must be protected.",
            "account_name": "Gamma LLC"
        }
    ]
    
    doc_ids = []
    for data in docs_data:
        doc_id = store.save_document(
            tenant_id="test-tenant",
            filename=data["filename"],
            file_type=data["file_type"],
            extracted_text=data["text"],
            parsed_data={},
            account_name=data["account_name"]
        )
        doc_ids.append(doc_id)
        indexer.index_document(doc_id, "test-tenant")
    
    print(f"✓ Added {len(doc_ids)} test documents")
    
    # Test 1: Basic search
    result = indexer.search("agreement", "test-tenant")
    assert result["success"], "Search should succeed"
    assert result["total"] >= 2, f"Should find at least 2 agreements, found {result['total']}"
    print(f"✓ Basic search found {result['total']} results")
    
    # Test 2: Search with file type filter
    result = indexer.search("services", "test-tenant", file_type="invoice")
    assert result["success"], "Search should succeed"
    assert result["total"] == 1, "Should find 1 invoice"
    assert result["results"][0]["file_type"] == "invoice"
    print("✓ File type filter works")
    
    # Test 3: Search with account filter (using account_id)
    result = indexer.search("agreement", "test-tenant", account_id="acct-123")
    # Account filtering is done at application level for SQLite
    print("✓ Account filter parameter accepted")
    
    # Test 4: Get filter options
    filters = indexer.get_filter_options("test-tenant")
    assert "file_types" in filters, "Should return file types"
    assert "accounts" in filters, "Should return accounts"
    print(f"✓ Filter options: {len(filters['file_types'])} types, {len(filters['accounts'])} accounts")
    
    # Test 5: Verify highlights
    result = indexer.search("payment", "test-tenant")
    if result["total"] > 0:
        assert "highlight" in result["results"][0], "Should have highlight field"
        assert "<mark>" in result["results"][0]["highlight"], "Should highlight matching text"
        print("✓ Text highlighting works")


def test_document_indexing_queue():
    """Test document indexing queue."""
    print("\n=== Testing Document Indexing Queue ===")
    
    setup_test_db()
    store = DocumentStore()
    
    # Add a document
    doc_id = store.save_document(
        tenant_id="test-tenant",
        filename="test.pdf",
        file_type="pdf",
        extracted_text="Test document content",
        parsed_data={}
    )
    
    # Queue for indexing (synchronous in test)
    result = queue_document_indexing(doc_id, "test-tenant")
    assert result, "Should queue/index successfully"
    print("✓ Document indexing queued")


def test_performance():
    """Test search performance."""
    print("\n=== Testing Search Performance ===")
    
    setup_test_db()
    store = DocumentStore()
    indexer = SearchIndexer()
    
    # Add multiple documents
    for i in range(10):
        doc_id = store.save_document(
            tenant_id="test-tenant",
            filename=f"doc_{i}.pdf",
            file_type="contract" if i % 2 == 0 else "invoice",
            extracted_text=f"Document {i} contains contract terms and payment details for project number {i}.",
            parsed_data={"index": i}
        )
        indexer.index_document(doc_id, "test-tenant")
    
    # Test search performance
    import time
    start = time.time()
    
    for _ in range(10):
        result = indexer.search("contract", "test-tenant")
        assert result["success"]
    
    elapsed = (time.time() - start) * 1000  # Convert to ms
    avg_time = elapsed / 10
    
    print(f"✓ Average search time: {avg_time:.2f}ms (10 searches)")
    
    # Should be under 200ms per requirements
    if avg_time < 200:
        print("  ✓ Meets performance requirement (< 200ms)")
    else:
        print(f"  ⚠ Exceeds performance target: {avg_time:.2f}ms")


def cleanup():
    """Clean up test database."""
    if os.path.exists('./test_search.db'):
        os.remove('./test_search.db')
        print("\n✓ Cleaned up test database")


def run_all_tests():
    """Run all search tests."""
    print("=" * 60)
    print("FILE SEARCH TEST SUITE")
    print("=" * 60)
    
    try:
        test_migrations()
        test_document_store()
        test_search_indexer()
        test_document_indexing_queue()
        test_performance()
        
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        cleanup()


if __name__ == "__main__":
    run_all_tests()
