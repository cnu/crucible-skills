"""
Search API Routes
FastAPI endpoints for document search functionality.
"""

from typing import Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from search_indexer import get_search_indexer, queue_document_indexing
from document_store import get_document_store

# Create router
search_router = APIRouter(prefix="/api/search", tags=["search"])


# Request/Response models
class SearchRequest(BaseModel):
    query: str
    file_type: Optional[str] = None
    account_id: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = 20


class SearchResult(BaseModel):
    document_id: str
    filename: str
    file_type: str
    account_name: Optional[str]
    uploaded_at: str
    score: float
    highlight: str


class SearchResponse(BaseModel):
    success: bool
    query: str
    total: int
    results: list[SearchResult]
    filters: Dict[str, Any]
    processing_time_ms: float


class FilterOptionsResponse(BaseModel):
    success: bool
    file_types: list[Dict[str, Any]]
    accounts: list[Dict[str, Any]]


# Dependency for tenant extraction
async def get_tenant_id(request: Request) -> str:
    """
    Extract tenant ID from request.
    In production, this would come from JWT token or API key metadata.
    For demo, use a default tenant or extract from header.
    """
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        # Default tenant for demo
        tenant_id = "default"
    return tenant_id


@search_router.get("/", response_model=SearchResponse)
async def search_documents(
    q: str = Query(..., min_length=1, description="Search query"),
    type: Optional[str] = Query(None, description="Filter by file type"),
    account: Optional[str] = Query(None, description="Filter by account ID"),
    date_from: Optional[str] = Query(None, description="Start date (ISO format)"),
    date_to: Optional[str] = Query(None, description="End date (ISO format)"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Search documents with full-text search.
    
    Returns documents matching the query with highlighted snippets.
    Results are filtered by tenant for isolation.
    """
    try:
        indexer = get_search_indexer()
        
        result = indexer.search(
            query=q,
            tenant_id=tenant_id,
            file_type=type,
            account_id=account,
            date_from=date_from,
            date_to=date_to,
            limit=limit
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Search failed"))
        
        # Get filter options for the response
        filters = indexer.get_filter_options(tenant_id)
        
        return SearchResponse(
            success=True,
            query=result["query"],
            total=result["total"],
            results=[SearchResult(**r) for r in result["results"]],
            filters=filters,
            processing_time_ms=result["processing_time_ms"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@search_router.post("/", response_model=SearchResponse)
async def search_documents_post(
    request: SearchRequest,
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Search documents with POST request (for complex queries).
    """
    return await search_documents(
        q=request.query,
        type=request.file_type,
        account=request.account_id,
        date_from=request.date_from,
        date_to=request.date_to,
        limit=request.limit,
        tenant_id=tenant_id
    )


@search_router.get("/filters", response_model=FilterOptionsResponse)
async def get_filter_options(
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Get available filter options for the tenant.
    
    Returns list of file types and accounts with document counts.
    """
    try:
        indexer = get_search_indexer()
        options = indexer.get_filter_options(tenant_id)
        
        return FilterOptionsResponse(
            success=True,
            file_types=options["file_types"],
            accounts=options["accounts"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get filters: {str(e)}")


@search_router.get("/suggest")
async def get_search_suggestions(
    q: str = Query(..., min_length=2, description="Partial query"),
    limit: int = Query(5, ge=1, le=10),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Get search suggestions based on partial query.
    
    Returns suggested completions based on indexed content.
    """
    try:
        indexer = get_search_indexer()
        
        # Search with the partial query
        result = indexer.search(
            query=q,
            tenant_id=tenant_id,
            limit=limit
        )
        
        if not result["success"]:
            return {"success": False, "suggestions": []}
        
        # Extract unique terms from results
        suggestions = []
        seen = set()
        
        for doc in result["results"]:
            # Add filename as suggestion
            if doc["filename"] and doc["filename"] not in seen:
                suggestions.append({
                    "text": doc["filename"],
                    "type": "filename",
                    "document_id": doc["document_id"]
                })
                seen.add(doc["filename"])
            
            # Add account name as suggestion
            if doc["account_name"] and doc["account_name"] not in seen:
                suggestions.append({
                    "text": doc["account_name"],
                    "type": "account",
                    "document_id": doc["document_id"]
                })
                seen.add(doc["account_name"])
        
        return {
            "success": True,
            "query": q,
            "suggestions": suggestions[:limit]
        }
        
    except Exception as e:
        return {"success": False, "error": str(e), "suggestions": []}


@search_router.get("/recent")
async def get_recent_documents(
    limit: int = Query(10, ge=1, le=50),
    file_type: Optional[str] = None,
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Get recently uploaded documents.
    
    Useful for "recent files" section in search UI.
    """
    try:
        store = get_document_store()
        
        documents = store.list_documents(
            tenant_id=tenant_id,
            file_type=file_type,
            limit=limit
        )
        
        results = []
        for doc in documents:
            results.append({
                "document_id": doc.document_id,
                "filename": doc.filename,
                "file_type": doc.file_type,
                "account_name": doc.account_name,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None
            })
        
        return {
            "success": True,
            "total": len(results),
            "documents": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get recent documents: {str(e)}")


@search_router.get("/stats")
async def get_search_stats(
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Get search statistics for the tenant.
    """
    try:
        store = get_document_store()
        stats = store.get_statistics(tenant_id)
        
        return {
            "success": True,
            "statistics": stats
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")
