# File Search Feature Specification

## Overview
Real-time file search functionality for the Ridgehold document parsing platform with instant, as-you-type results.

## Architecture

### Database Schema

**search_documents table:**
```sql
CREATE TABLE search_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id VARCHAR(36) UNIQUE NOT NULL,  -- UUID for external reference
    tenant_id VARCHAR(36) NOT NULL,             -- Multi-tenant isolation
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL,              -- 'pdf', 'contract', 'invoice', 'call_transcript', 'note'
    content_type VARCHAR(100),                 -- MIME type
    file_size INTEGER,
    extracted_text TEXT,                        -- Full text content for search
    parsed_data JSON,                           -- Structured extracted data
    account_id VARCHAR(36),                     -- Associated account (optional)
    account_name VARCHAR(255),                  -- Denormalized for search
    uploaded_by VARCHAR(36),                    -- User who uploaded
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    indexed_at TIMESTAMP,                       -- When search index was updated
    is_deleted BOOLEAN DEFAULT 0,
    
    -- Full-text search virtual table (SQLite FTS5 or PostgreSQL tsvector)
    search_vector TSVECTOR  -- PostgreSQL only
);

-- Indexes for performance
CREATE INDEX idx_search_docs_tenant ON search_documents(tenant_id);
CREATE INDEX idx_search_docs_type ON search_documents(file_type);
CREATE INDEX idx_search_docs_account ON search_documents(account_id);
CREATE INDEX idx_search_docs_uploaded ON search_documents(uploaded_at);

-- Full-text search index (PostgreSQL)
CREATE INDEX idx_search_docs_fts ON search_documents USING GIN(search_vector);

-- FTS5 virtual table (SQLite)
CREATE VIRTUAL TABLE search_documents_fts USING fts5(
    document_id, filename, extracted_text, account_name,
    content='search_documents',
    content_rowid='id'
);
```

### Components

**1. Document Store Module (`document_store.py`)**
- Store document metadata and extracted text
- Handle database operations with tenant isolation
- Provide CRUD operations for documents

**2. Search Indexer (`search_indexer.py`)**
- Celery task for async document indexing
- Update full-text search indexes
- Handle re-indexing on updates

**3. Search API (`search_routes.py`)**
- `GET /api/search?q={query}&type={type}&account={account}&date_from={date}&date_to={date}&limit={limit}`
- Real-time search endpoint with debouncing support
- Filter support: file_type, date_range, account_id

**4. Search UI (`SearchModal.tsx`)**
- Keyboard shortcut: Cmd/Ctrl+K
- Real-time search as user types (debounced 200ms)
- Highlight matching text in results
- Filter sidebar
- Click to navigate to document/account

### API Specification

**Search Endpoint:**
```
GET /api/search?q={query}&type={type}&account={account}&date_from={date}&date_to={date}&limit={limit}

Query Parameters:
- q: Search query string (required)
- type: Filter by file type (optional) - 'contract', 'invoice', 'call_transcript', 'note', 'pdf'
- account: Filter by account_id (optional)
- date_from: Start date filter (optional, ISO format)
- date_to: End date filter (optional, ISO format)
- limit: Max results (default 20, max 100)

Response:
{
  "success": true,
  "query": "contract terms",
  "total": 45,
  "results": [
    {
      "document_id": "uuid",
      "filename": "Service_Agreement_Acme.pdf",
      "file_type": "contract",
      "account_name": "Acme Corp",
      "uploaded_at": "2026-01-15T10:30:00Z",
      "highlights": ["...contract terms specify that...", "...agreement contract..."],
      "score": 0.95
    }
  ],
  "filters": {
    "types": ["contract", "invoice", "call_transcript"],
    "accounts": [{"id": "uuid", "name": "Acme Corp", "count": 12}]
  },
  "processing_time_ms": 45
}
```

**Document Store Endpoint:**
```
POST /api/documents/store
Authorization: Bearer {api_key}
Content-Type: multipart/form-data

Form Fields:
- file: Uploaded file (PDF, image)
- account_id: Associated account (optional)
- account_name: Account name for indexing (optional)
- metadata: JSON string with additional metadata

Response:
{
  "success": true,
  "document_id": "uuid",
  "filename": "contract.pdf",
  "file_type": "pdf",
  "indexed": true,
  "search_available": true
}
```

### Implementation Phases

**Phase 1: Core Search (Priority: High)**
1. Database migrations - Create search_documents table with FTS
2. Document store module - Save extracted documents
3. Celery indexer task - Async indexing with retry logic
4. Search API endpoint - Basic search with filters
5. Simple search UI - Command palette style modal

**Phase 2: Enhanced UX (Priority: Medium)**
1. Keyboard shortcut (Cmd/Ctrl+K) registration
2. Text highlighting in search results
3. Advanced filters UI (file type, date range, account)
4. Search history tracking
5. Recent documents section

**Phase 3: Advanced Features (Priority: Low)**
1. Fuzzy matching with trigram similarity
2. Saved searches functionality
3. Search analytics dashboard
4. Bulk re-indexing admin tool

## Performance Requirements

- Search latency: < 200ms for queries returning < 100 results
- Indexing latency: < 5 seconds per document (async)
- Concurrent searches: Support 100+ concurrent users
- Database: Handle 1M+ documents with sub-second search

## Security Requirements

- Tenant isolation: Users only see their tenant's documents
- RBAC: Read/search permissions per document type
- Input sanitization: Prevent SQL injection in search queries
- Rate limiting: 30 searches per minute per API key
- Audit logging: Log all search queries for compliance

## Testing Plan

1. Unit tests for search indexer
2. API integration tests for search endpoints
3. Performance tests with 100k+ documents
4. Security tests for tenant isolation
5. E2E tests for search UI

## Definition of Done

- [ ] Users can open search with Cmd/Ctrl+K
- [ ] Real-time results appear as user types (< 200ms)
- [ ] Results show highlighted matching text
- [ ] Users can filter by file type and account
- [ ] Clicking result navigates to file/account
- [ ] All existing file types searchable
- [ ] Search respects tenant isolation and RBAC
- [ ] Performance meets requirements
- [ ] Documentation complete
- [ ] Tests passing
