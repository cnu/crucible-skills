"""
FastAPI Demo Application for Document Parsing
Provides public-facing API endpoints for interactive prospect demos with enhanced security and reliability.
"""

import os
import time
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Import security modules
from auth import init_auth_db, get_current_api_key
from auth.file_validation import validate_file_upload, validate_contract_file, validate_invoice_file
from auth.security_headers import SecurityHeadersMiddleware, get_cors_origins
from document_parser import DocumentProcessingPipeline

# Import reliability features
from reliability import (
    create_error_response, ErrorResponse, get_timeout, ErrorCode,
    classify_error, CircuitBreakerRegistry
)

# Import search functionality
from search_routes import search_router
from migrations.file_search_migrations import run_migrations, verify_migrations
from document_store import get_document_store, DocumentStore
from search_indexer import queue_document_indexing

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Store for request logging (in production, use proper logging/database)
request_logs = []

# Global pipeline instance
doc_pipeline: Optional[DocumentProcessingPipeline] = None

# Configuration
ALLOW_DEMO_MODE = os.getenv("ALLOW_DEMO_MODE", "false").lower() == "true"
REQUIRE_API_KEY = os.getenv("REQUIRE_API_KEY", "false").lower() == "true"


def save_document_to_search(
    store: DocumentStore,
    tenant_id: str,
    filename: str,
    file_type: str,
    content_type: str,
    file_content: bytes,
    extracted_text: str,
    parsed_data: dict,
    uploaded_by: str = None
) -> str:
    """
    Save processed document to search index.
    
    Args:
        store: DocumentStore instance
        tenant_id: Tenant identifier
        filename: Original filename
        file_type: Document type (contract, invoice, etc.)
        content_type: MIME type
        file_content: Raw file bytes
        extracted_text: Full extracted text
        parsed_data: Structured extracted data
        uploaded_by: User identifier
        
    Returns:
        document_id: UUID of stored document
    """
    try:
        # Save document to database
        document_id = store.save_document(
            tenant_id=tenant_id,
            filename=filename,
            file_type=file_type,
            extracted_text=extracted_text,
            parsed_data=parsed_data,
            content_type=content_type,
            file_size=len(file_content),
            uploaded_by=uploaded_by
        )
        
        # Queue for indexing (async or sync)
        queue_document_indexing(document_id, tenant_id)
        
        return document_id
    except Exception as e:
        # Log but don't fail the request - search is secondary
        print(f"⚠ Warning: Could not save document to search index: {e}")
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    global doc_pipeline
    
    # Initialize auth database
    try:
        init_auth_db()
        print("✓ Authentication database initialized")
    except Exception as e:
        print(f"⚠ Warning: Could not initialize auth database: {e}")
    
    # Initialize search database migrations
    try:
        run_migrations()
        status = verify_migrations()
        print(f"✓ Search database migrations completed")
        print(f"  - search_documents table: {status.get('search_documents_table', False)}")
        print(f"  - FTS index: {status.get('fts_table', 'N/A')}")
    except Exception as e:
        print(f"⚠ Warning: Search migrations failed: {e}")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("WARNING: OPENAI_API_KEY not set. Document parsing will fail.")
    doc_pipeline = DocumentProcessingPipeline(api_key=api_key)
    print("✓ Document processing pipeline initialized")
    
    print(f"✓ Demo mode: {ALLOW_DEMO_MODE}")
    print(f"✓ API key required: {REQUIRE_API_KEY}")
    
    yield
    # Shutdown
    print("Shutting down application")


# Create FastAPI app
app = FastAPI(
    title="AI Document Parsing Demo API",
    description=f"""
    Public-facing API endpoints for interactive prospect demos.
    
    ## Features
    
    - **Contract Parsing**: Upload PDF contracts and get structured JSON extraction
    - **Invoice Parsing**: Upload invoice documents and get structured data extraction
    - **Health Monitoring**: Health check endpoint for monitoring
    - **Interactive Demo**: Built-in HTML demo pages for testing
    
    ## Security
    
    - **API Key Authentication**: {'Required' if REQUIRE_API_KEY else 'Optional in demo mode'}
    - **Rate Limiting**: Demo endpoints limited to 10 requests per minute per IP
    - **File Upload Validation**: Magic number validation, 10MB limit, PDF integrity checks
    - **Security Headers**: HSTS, CSP, X-Frame-Options, X-Content-Type-Options
    - **CORS**: Whitelist-based origin validation
    
    ## Authentication
    
    {'All endpoints require a valid X-API-Key header.' if REQUIRE_API_KEY else 
     'Demo mode allows access without API key. Set REQUIRE_API_KEY=true to enforce authentication.'}
    File uploads limited to 10MB with content type validation.
    """,
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add security headers middleware (before CORS)
app.add_middleware(
    SecurityHeadersMiddleware,
    hsts_max_age=31536000,
    hsts_include_subdomains=True,
    hsts_preload=True,
    allowed_frame_ancestors=["'self'"] if ALLOW_DEMO_MODE else ["'none'"]
)

# Add CORS middleware with whitelist (not wildcard)
allowed_origins = get_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type", "X-Request-ID", "X-Tenant-ID"],
)

# Include search routes
app.include_router(search_router)

# Middleware for request logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]
    
    # Add request ID to headers
    request.state.request_id = request_id
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    
    log_entry = {
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat(),
        "method": request.method,
        "path": request.url.path,
        "client_ip": get_remote_address(request),
        "status_code": response.status_code,
        "process_time_ms": round(process_time * 1000, 2)
    }
    request_logs.append(log_entry)
    
    # Keep only last 1000 logs
    if len(request_logs) > 1000:
        request_logs.pop(0)
    
    # Add headers to response
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = str(round(process_time, 3))
    
    return response


# Pydantic models for responses
class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    pipeline_ready: bool
    features: Dict[str, bool]
    security: Dict[str, Any]


class ContractParseResponse(BaseModel):
    success: bool
    request_id: str
    filename: str
    document_type: str
    extraction_method: str
    page_count: Optional[int]
    extracted_text_preview: str
    parsed_data: Dict[str, Any]
    processing_metadata: Dict[str, Any]
    processing_time_ms: float


class InvoiceParseResponse(BaseModel):
    success: bool
    request_id: str
    filename: str
    document_type: str
    extraction_method: str
    page_count: Optional[int]
    extracted_text_preview: str
    parsed_data: Dict[str, Any]
    processing_metadata: Dict[str, Any]
    processing_time_ms: float


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    request_id: str
    details: Optional[str] = None


class APIKeyInfoResponse(BaseModel):
    success: bool
    key_prefix: str
    name: str
    scopes: list
    is_demo: bool


# Dependency for optional API key
async def optional_api_key(request: Request):
    """Get API key info if provided, or allow demo mode."""
    api_key = request.headers.get("X-API-Key")
    
    if api_key:
        try:
            return await get_current_api_key(api_key)
        except HTTPException:
            if REQUIRE_API_KEY:
                raise
            # In demo mode, continue without valid key
            return {"is_demo": True, "name": "Invalid Key - Demo Mode"}
    
    if REQUIRE_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="API key required. Provide X-API-Key header or set REQUIRE_API_KEY=false for demo mode."
        )
    
    return {"is_demo": True, "name": "Demo Mode", "scopes": ["read", "demo"]}


# Endpoints
@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint returns demo landing page."""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI Document Parsing Demo API</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; line-height: 1.6; }
            h1 { color: #2563eb; }
            h2 { color: #1e40af; margin-top: 30px; }
            .endpoint { background: #f3f4f6; padding: 15px; margin: 10px 0; border-radius: 8px; }
            .method { display: inline-block; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; margin-right: 10px; }
            .get { background: #10b981; color: white; }
            .post { background: #3b82f6; color: white; }
            code { background: #e5e7eb; padding: 2px 6px; border-radius: 4px; font-family: monospace; }
            a { color: #2563eb; text-decoration: none; }
            a:hover { text-decoration: underline; }
            .demo-link { display: inline-block; margin-top: 10px; padding: 10px 20px; background: #2563eb; color: white; border-radius: 6px; }
            .security-badge { display: inline-block; padding: 4px 8px; background: #dcfce7; color: #166534; border-radius: 4px; font-size: 12px; margin-right: 5px; }
        </style>
    </head>
    <body>
        <h1>AI Document Parsing Demo API</h1>
        <p>Welcome to the AI Document Parsing Demo API. This service provides intelligent document extraction capabilities for contracts and invoices.</p>
        
        <div style="margin: 20px 0;">
            <span class="security-badge">🔒 HSTS Enabled</span>
            <span class="security-badge">🔒 API Key Auth</span>
            <span class="security-badge">🔒 File Validation</span>
            <span class="security-badge">🔒 Rate Limited</span>
        </div>
        
        <h2>Available Endpoints</h2>
        
        <div class="endpoint">
            <span class="method get">GET</span>
            <code>/health</code> - Health check endpoint
        </div>
        
        <div class="endpoint">
            <span class="method post">POST</span>
            <code>/demo/contract-parse</code> - Upload PDF contract, get structured JSON
            <br><small>Headers: <code>X-API-Key: your-api-key</code></small>
        </div>
        
        <div class="endpoint">
            <span class="method post">POST</span>
            <code>/demo/invoice-parse</code> - Upload invoice document, get extraction
            <br><small>Headers: <code>X-API-Key: your-api-key</code></small>
        </div>
        
        <div class="endpoint">
            <span class="method get">GET</span>
            <code>/docs</code> - Auto-generated Swagger documentation
        </div>
        
        <h2>Interactive Demo</h2>
        <p>Try the live demo pages:</p>
        <a href="/demo" class="demo-link">Launch Demo Interface</a>
        
        <h2>API Documentation</h2>
        <p>View the full API documentation at <a href="/docs">/docs</a> (Swagger UI) or <a href="/redoc">/redoc</a> (ReDoc).</p>
        
        <h2>Rate Limits</h2>
        <p>Demo endpoints are limited to <strong>10 requests per minute</strong> per IP address.</p>
        
        <h2>File Requirements</h2>
        <ul>
            <li>Maximum file size: 10MB</li>
            <li>Supported formats: PDF, JPEG, PNG, GIF, BMP, TIFF, WEBP</li>
            <li>Files validated using magic number detection</li>
            <li>PDFs validated for proper structure</li>
            <li>For best results, use text-based PDFs rather than scanned images</li>
        </ul>
        
        <h2>Security</h2>
        <ul>
            <li>All connections use TLS 1.3 (HSTS enforced)</li>
            <li>API key authentication required (X-API-Key header)</li>
            <li>Content Security Policy (CSP) enabled</li>
            <li>X-Frame-Options: DENY (clickjacking protection)</li>
            <li>X-Content-Type-Options: nosniff</li>
            <li>CORS whitelist validation</li>
        </ul>
    </body>
    </html>
    """)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for monitoring with reliability status."""
    # Get circuit breaker states
    llm_cb = CircuitBreakerRegistry.get("llm_api")
    wiki_cb = CircuitBreakerRegistry.get("wikipedia")
    
    reliability_status = {
        "llm_api_circuit_breaker": llm_cb.state.value if llm_cb else "unknown",
        "wikipedia_circuit_breaker": wiki_cb.state.value if wiki_cb else "unknown",
        "retry_enabled": True,
        "timeout_configured": True
    }
    
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="1.1.0",
        pipeline_ready=doc_pipeline is not None,
        features={
            "contract_parsing": True,
            "invoice_parsing": True,
            "pdf_processing": True,
            "image_processing": True,
            "rate_limiting": True,
            "api_key_auth": True,
            "file_validation": True,
            "security_headers": True,
            "retry_logic": True,
            "circuit_breaker": True,
            "timeout_handling": True
        },
        security={
            "api_key_required": REQUIRE_API_KEY,
            "demo_mode_allowed": ALLOW_DEMO_MODE,
            "hsts_enabled": True,
            "csp_enabled": True,
            "cors_whitelist": True,
            **reliability_status
        }
    )


@app.get("/auth/verify", response_model=APIKeyInfoResponse)
async def verify_api_key(api_key_info: dict = Depends(get_current_api_key)):
    """
    Verify an API key and return key information.
    Useful for testing authentication.
    """
    return APIKeyInfoResponse(
        success=True,
        key_prefix=api_key_info.get("key_prefix", api_key_info.get("name", "unknown")[:8]),
        name=api_key_info.get("name", "Unknown"),
        scopes=api_key_info.get("scopes", []),
        is_demo=api_key_info.get("is_demo", False)
    )


@app.post("/demo/contract-parse", response_model=ContractParseResponse)
@limiter.limit("10/minute")
async def parse_contract(
    request: Request,
    file: UploadFile = File(..., description="Contract document (PDF or image)"),
    api_key_info: dict = Depends(optional_api_key)
):
    """
    Upload a contract document (PDF or image) and receive structured JSON extraction.
    
    **Authentication**: Requires X-API-Key header (unless in demo mode)
    
    **Features**:
    - Extracts key contract information
    - Identifies parties, dates, terms, and clauses
    - Returns structured data with confidence scores
    - Magic number validation for file security
    - Retry logic with exponential backoff for transient errors
    - 30 second timeout per document
    """
    import signal
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
    
    start_time = time.time()
    request_id = getattr(request.state, 'request_id', str(uuid.uuid4())[:8])
    
    def process_with_timeout():
        """Process document with timeout enforcement."""
        # Validate file with security checks
        # Note: file validation happens in async context, so we pass content
        return doc_pipeline.process_contract(
            file_content=content,
            content_type=content_type,
            filename=file.filename
        )
    
    try:
        # Validate file with security checks
        content, content_type = await validate_contract_file(file)
        
        # Process the document with timeout
        timeout_seconds = get_timeout("per_document")
        
        # Use ThreadPoolExecutor for timeout handling
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(process_with_timeout)
            try:
                result = future.result(timeout=timeout_seconds)
            except FutureTimeoutError:
                # Create structured timeout error
                error_response = ErrorResponse(
                    success=False,
                    error=f"Document processing timeout: exceeded {timeout_seconds}s limit",
                    error_code=ErrorCode.TIMEOUT.value,
                    request_id=request_id,
                    trace_id=str(uuid.uuid4())[:16],
                    retryable=True,
                    details={"timeout_seconds": timeout_seconds, "partial": True}
                )
                raise HTTPException(status_code=504, detail=error_response.to_dict())
        
        process_time = time.time() - start_time
        
        # Save to search index for future retrieval
        try:
            store = get_document_store()
            doc_id = save_document_to_search(
                store=store,
                tenant_id="default",  # TODO: Extract from API key metadata
                filename=result["filename"],
                file_type="contract",
                content_type=content_type,
                file_content=content,
                extracted_text=result["extracted_text_preview"],
                parsed_data=result["parsed_data"],
                uploaded_by=api_key_info.get("name") if api_key_info else None
            )
            if doc_id:
                result["processing_metadata"]["search_document_id"] = doc_id
        except Exception as e:
            # Don't fail the request if search indexing fails
            print(f"⚠ Search indexing failed: {e}")
        
        return ContractParseResponse(
            success=True,
            request_id=request_id,
            filename=result["filename"],
            document_type=result["document_type"],
            extraction_method=result["extraction_method"],
            page_count=result["page_count"],
            extracted_text_preview=result["extracted_text_preview"],
            parsed_data=result["parsed_data"],
            processing_metadata=result["processing_metadata"],
            processing_time_ms=round(process_time * 1000, 2)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        process_time = time.time() - start_time
        
        # Create structured error response
        error_response = create_error_response(e, request_id)
        
        raise HTTPException(
            status_code=500,
            detail=error_response.to_dict()
        )


@app.post("/demo/invoice-parse", response_model=InvoiceParseResponse)
@limiter.limit("10/minute")
async def parse_invoice(
    request: Request,
    file: UploadFile = File(..., description="Invoice document (PDF or image)"),
    api_key_info: dict = Depends(optional_api_key)
):
    """
    Upload an invoice document (PDF or image) and receive structured extraction.
    
    **Authentication**: Requires X-API-Key header (unless in demo mode)
    
    **Features**:
    - Extracts invoice number, dates, vendor, customer
    - Identifies line items, quantities, prices
    - Calculates totals, taxes, and payment terms
    - Magic number validation for file security
    - Retry logic with exponential backoff for transient errors
    - 30 second timeout per document
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
    
    start_time = time.time()
    request_id = getattr(request.state, 'request_id', str(uuid.uuid4())[:8])
    
    def process_with_timeout():
        """Process document with timeout enforcement."""
        return doc_pipeline.process_invoice(
            file_content=content,
            content_type=content_type,
            filename=file.filename
        )
    
    try:
        # Validate file with security checks
        content, content_type = await validate_invoice_file(file)
        
        # Process the document with timeout
        timeout_seconds = get_timeout("per_document")
        
        # Use ThreadPoolExecutor for timeout handling
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(process_with_timeout)
            try:
                result = future.result(timeout=timeout_seconds)
            except FutureTimeoutError:
                # Create structured timeout error
                error_response = ErrorResponse(
                    success=False,
                    error=f"Document processing timeout: exceeded {timeout_seconds}s limit",
                    error_code=ErrorCode.TIMEOUT.value,
                    request_id=request_id,
                    trace_id=str(uuid.uuid4())[:16],
                    retryable=True,
                    details={"timeout_seconds": timeout_seconds, "partial": True}
                )
                raise HTTPException(status_code=504, detail=error_response.to_dict())
        
        process_time = time.time() - start_time
        
        # Save to search index for future retrieval
        try:
            store = get_document_store()
            doc_id = save_document_to_search(
                store=store,
                tenant_id="default",  # TODO: Extract from API key metadata
                filename=result["filename"],
                file_type="invoice",
                content_type=content_type,
                file_content=content,
                extracted_text=result["extracted_text_preview"],
                parsed_data=result["parsed_data"],
                uploaded_by=api_key_info.get("name") if api_key_info else None
            )
            if doc_id:
                result["processing_metadata"]["search_document_id"] = doc_id
        except Exception as e:
            # Don't fail the request if search indexing fails
            print(f"⚠ Search indexing failed: {e}")
        
        return InvoiceParseResponse(
            success=True,
            request_id=request_id,
            filename=result["filename"],
            document_type=result["document_type"],
            extraction_method=result["extraction_method"],
            page_count=result["page_count"],
            extracted_text_preview=result["extracted_text_preview"],
            parsed_data=result["parsed_data"],
            processing_metadata=result["processing_metadata"],
            processing_time_ms=round(process_time * 1000, 2)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        process_time = time.time() - start_time
        
        # Create structured error response
        error_response = create_error_response(e, request_id)
        
        raise HTTPException(
            status_code=500,
            detail=error_response.to_dict()
        )


@app.get("/demo", response_class=HTMLResponse)
async def demo_page():
    """Interactive HTML demo page for testing the API."""
    api_key_input = """
    <div style="background: #eff6ff; border: 1px solid #3b82f6; padding: 15px; margin-bottom: 20px; border-radius: 8px;">
        <h4 style="margin-top: 0; color: #1e40af;">API Key Required</h4>
        <p style="margin-bottom: 10px; font-size: 14px;">Enter your API key to test the endpoints:</p>
        <input type="text" id="api-key" placeholder="cru_xxxxx..." style="width: 100%; padding: 10px; border: 1px solid #cbd5e1; border-radius: 4px; font-family: monospace; font-size: 14px;">
        <p style="margin-top: 10px; font-size: 12px; color: #64748b;">
            Generate API keys with: <code>python api_key_cli.py create --name "Demo Key"</code>
        </p>
    </div>
    """ if REQUIRE_API_KEY else """
    <div style="background: #f0fdf4; border: 1px solid #22c55e; padding: 15px; margin-bottom: 20px; border-radius: 8px;">
        <h4 style="margin-top: 0; color: #15803d;">Demo Mode Enabled</h4>
        <p style="margin: 0; font-size: 14px;">No API key required. Set REQUIRE_API_KEY=true to enforce authentication.</p>
    </div>
    """
    
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Document Parsing Demo</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                max-width: 900px;
                margin: 0 auto;
                padding: 40px 20px;
                background: #f8fafc;
                line-height: 1.6;
            }}
            h1 {{ color: #1e293b; margin-bottom: 10px; }}
            .subtitle {{ color: #64748b; margin-bottom: 30px; }}
            .tabs {{
                display: flex;
                gap: 10px;
                margin-bottom: 30px;
                border-bottom: 2px solid #e2e8f0;
            }}
            .tab {{
                padding: 12px 24px;
                background: none;
                border: none;
                cursor: pointer;
                font-size: 16px;
                color: #64748b;
                border-bottom: 2px solid transparent;
                margin-bottom: -2px;
                transition: all 0.2s;
            }}
            .tab:hover {{ color: #3b82f6; }}
            .tab.active {{
                color: #3b82f6;
                border-bottom-color: #3b82f6;
                font-weight: 600;
            }}
            .demo-section {{
                background: white;
                padding: 30px;
                border-radius: 12px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                display: none;
            }}
            .demo-section.active {{ display: block; }}
            .upload-area {{
                border: 2px dashed #cbd5e1;
                border-radius: 8px;
                padding: 40px;
                text-align: center;
                transition: all 0.2s;
                cursor: pointer;
            }}
            .upload-area:hover, .upload-area.dragover {{
                border-color: #3b82f6;
                background: #eff6ff;
            }}
            .upload-area input {{ display: none; }}
            .upload-icon {{
                font-size: 48px;
                margin-bottom: 16px;
            }}
            .btn {{
                background: #3b82f6;
                color: white;
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-size: 16px;
                font-weight: 500;
                transition: background 0.2s;
            }}
            .btn:hover {{ background: #2563eb; }}
            .btn:disabled {{
                background: #94a3b8;
                cursor: not-allowed;
            }}
            .result {{
                margin-top: 30px;
                padding: 20px;
                background: #f1f5f9;
                border-radius: 8px;
                display: none;
            }}
            .result.show {{ display: block; }}
            .result h3 {{ margin-top: 0; color: #1e293b; }}
            pre {{
                background: #1e293b;
                color: #e2e8f0;
                padding: 20px;
                border-radius: 8px;
                overflow-x: auto;
                font-size: 13px;
                line-height: 1.5;
            }}
            .error {{
                background: #fef2f2;
                border: 1px solid #fecaca;
                color: #dc2626;
                padding: 16px;
                border-radius: 8px;
                margin-top: 20px;
            }}
            .loading {{
                display: none;
                text-align: center;
                padding: 40px;
            }}
            .loading.show {{ display: block; }}
            .spinner {{
                border: 3px solid #f3f4f6;
                border-top: 3px solid #3b82f6;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 0 auto 16px;
            }}
            @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
            .file-info {{
                background: #eff6ff;
                padding: 12px 16px;
                border-radius: 6px;
                margin: 16px 0;
                display: none;
            }}
            .file-info.show {{ display: block; }}
            .info-box {{
                background: #eff6ff;
                border-left: 4px solid #3b82f6;
                padding: 16px;
                margin-bottom: 24px;
                border-radius: 0 8px 8px 0;
            }}
            .info-box h4 {{ margin: 0 0 8px; color: #1e40af; }}
            .info-box p {{ margin: 0; color: #475569; font-size: 14px; }}
            .endpoint-url {{
                background: #1e293b;
                color: #22c55e;
                padding: 12px 16px;
                border-radius: 6px;
                font-family: monospace;
                font-size: 14px;
                margin: 16px 0;
            }}
            .security-notice {{
                background: #fefce8;
                border: 1px solid #fbbf24;
                padding: 12px;
                border-radius: 6px;
                margin-bottom: 20px;
                font-size: 14px;
                color: #854d0e;
            }}
        </style>
    </head>
    <body>
        <h1>Document Parsing Demo</h1>
        <p class="subtitle">Upload contract or invoice documents to see AI-powered extraction in action</p>
        
        <div class="security-notice">
            🔒 <strong>Security Features:</strong> Files validated using magic number detection • Max 10MB • TLS 1.3 required
        </div>
        
        {api_key_input}
        
        <div class="tabs">
            <button class="tab active" onclick="switchTab('contract')">Contract Parser</button>
            <button class="tab" onclick="switchTab('invoice')">Invoice Parser</button>
        </div>
        
        <!-- Contract Demo Section -->
        <div id="contract-section" class="demo-section active">
            <div class="info-box">
                <h4>Contract Parsing</h4>
                <p>Extracts: Parties, dates, key terms, payment terms, termination conditions, governing law, and key clauses.</p>
            </div>
            
            <div class="endpoint-url">POST /demo/contract-parse</div>
            
            <div class="upload-area" id="contract-upload" onclick="document.getElementById('contract-file').click()">
                <input type="file" id="contract-file" accept=".pdf,.jpg,.jpeg,.png,.gif,.bmp,.tiff,.webp" onchange="handleFileSelect('contract', this)">
                <div class="upload-icon">&#128196;</div>
                <p><strong>Click to upload</strong> or drag and drop</p>
                <p style="color: #94a3b8; font-size: 14px;">PDF or images up to 10MB</p>
            </div>
            
            <div class="file-info" id="contract-file-info">
                <strong>Selected:</strong> <span id="contract-filename"></span>
            </div>
            
            <button class="btn" id="contract-btn" onclick="uploadFile('contract')" disabled>Parse Contract</button>
            
            <div class="loading" id="contract-loading">
                <div class="spinner"></div>
                <p>Processing document with AI...</p>
                <p style="color: #64748b; font-size: 14px;">This may take 10-30 seconds</p>
            </div>
            
            <div class="result" id="contract-result">
                <h3>Extraction Result</h3>
                <div id="contract-error"></div>
                <pre id="contract-output"></pre>
            </div>
        </div>
        
        <!-- Invoice Demo Section -->
        <div id="invoice-section" class="demo-section">
            <div class="info-box">
                <h4>Invoice Parsing</h4>
                <p>Extracts: Invoice number, dates, vendor, customer, line items, quantities, prices, totals, taxes, and payment terms.</p>
            </div>
            
            <div class="endpoint-url">POST /demo/invoice-parse</div>
            
            <div class="upload-area" id="invoice-upload" onclick="document.getElementById('invoice-file').click()">
                <input type="file" id="invoice-file" accept=".pdf,.jpg,.jpeg,.png,.gif,.bmp,.tiff,.webp" onchange="handleFileSelect('invoice', this)">
                <div class="upload-icon">&#128230;</div>
                <p><strong>Click to upload</strong> or drag and drop</p>
                <p style="color: #94a3b8; font-size: 14px;">PDF or images up to 10MB</p>
            </div>
            
            <div class="file-info" id="invoice-file-info">
                <strong>Selected:</strong> <span id="invoice-filename"></span>
            </div>
            
            <button class="btn" id="invoice-btn" onclick="uploadFile('invoice')" disabled>Parse Invoice</button>
            
            <div class="loading" id="invoice-loading">
                <div class="spinner"></div>
                <p>Processing document with AI...</p>
                <p style="color: #64748b; font-size: 14px;">This may take 10-30 seconds</p>
            </div>
            
            <div class="result" id="invoice-result">
                <h3>Extraction Result</h3>
                <div id="invoice-error"></div>
                <pre id="invoice-output"></pre>
            </div>
        </div>
        
        <script>
            const selectedFiles = {{ contract: null, invoice: null }};
            const requireApiKey = {'true' if REQUIRE_API_KEY else 'false'};
            
            function getApiKey() {{
                if (!requireApiKey) return '';
                const key = document.getElementById('api-key')?.value?.trim();
                return key || '';
            }}
            
            function switchTab(tab) {{
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.demo-section').forEach(s => s.classList.remove('active'));
                
                document.querySelector(`.tab:nth-child(${{tab === 'contract' ? 1 : 2}})`).classList.add('active');
                document.getElementById(`${{tab}}-section`).classList.add('active');
            }}
            
            function handleFileSelect(type, input) {{
                if (input.files && input.files[0]) {{
                    selectedFiles[type] = input.files[0];
                    document.getElementById(`${{type}}-filename`).textContent = input.files[0].name;
                    document.getElementById(`${{type}}-file-info`).classList.add('show');
                    document.getElementById(`${{type}}-btn`).disabled = false;
                }}
            }}
            
            async function uploadFile(type) {{
                const file = selectedFiles[type];
                if (!file) return;
                
                const apiKey = getApiKey();
                if (requireApiKey && !apiKey) {{
                    alert('Please enter an API key first');
                    return;
                }}
                
                const btn = document.getElementById(`${{type}}-btn`);
                const loading = document.getElementById(`${{type}}-loading`);
                const result = document.getElementById(`${{type}}-result`);
                const output = document.getElementById(`${{type}}-output`);
                const errorDiv = document.getElementById(`${{type}}-error`);
                
                btn.disabled = true;
                loading.classList.add('show');
                result.classList.remove('show');
                errorDiv.innerHTML = '';
                
                const formData = new FormData();
                formData.append('file', file);
                
                const headers = {{}};
                if (apiKey) headers['X-API-Key'] = apiKey;
                
                try {{
                    const response = await fetch(`/demo/${{type}}-parse`, {{
                        method: 'POST',
                        headers: headers,
                        body: formData
                    }});
                    
                    const data = await response.json();
                    
                    if (!response.ok) {{
                        throw new Error(data.detail || data.error || `HTTP error! status: ${{response.status}}`);
                    }}
                    
                    output.textContent = JSON.stringify(data, null, 2);
                    result.classList.add('show');
                }} catch (error) {{
                    errorDiv.innerHTML = `<div class="error"><strong>Error:</strong> ${{error.message}}</div>`;
                    result.classList.add('show');
                }} finally {{
                    loading.classList.remove('show');
                    btn.disabled = false;
                }}
            }}
            
            // Drag and drop support
            ['contract', 'invoice'].forEach(type => {{
                const uploadArea = document.getElementById(`${{type}}-upload`);
                
                uploadArea.addEventListener('dragover', (e) => {{
                    e.preventDefault();
                    uploadArea.classList.add('dragover');
                }});
                
                uploadArea.addEventListener('dragleave', () => {{
                    uploadArea.classList.remove('dragover');
                }});
                
                uploadArea.addEventListener('drop', (e) => {{
                    e.preventDefault();
                    uploadArea.classList.remove('dragover');
                    
                    if (e.dataTransfer.files && e.dataTransfer.files[0]) {{
                        const input = document.getElementById(`${{type}}-file`);
                        selectedFiles[type] = e.dataTransfer.files[0];
                        document.getElementById(`${{type}}-filename`).textContent = e.dataTransfer.files[0].name;
                        document.getElementById(`${{type}}-file-info`).classList.add('show');
                        document.getElementById(`${{type}}-btn`).disabled = false;
                    }}
                }});
            }});
        </script>
    </body>
    </html>
    """)


@app.get("/demo/logs")
@limiter.limit("30/minute")
async def get_request_logs(request: Request, limit: int = 100, api_key_info: dict = Depends(optional_api_key)):
    """Get recent request logs (for monitoring)."""
    return {
        "logs": request_logs[-limit:],
        "total_count": len(request_logs)
    }


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom HTTP exception handler with structured error responses."""
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    # Classify error to determine retryability
    error_code, retryable = classify_error(exc, exc.status_code)
    
    response = ErrorResponse(
        success=False,
        error=exc.detail,
        error_code=error_code.value,
        request_id=request_id,
        trace_id=str(uuid.uuid4())[:16],
        retryable=retryable
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=response.to_dict()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler with structured error responses."""
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    # Create structured error response
    error_response = create_error_response(exc, request_id)
    
    # Include details only in debug mode
    if os.getenv("DEBUG"):
        error_response.details = {"exception_type": type(exc).__name__, "message": str(exc)}
    
    return JSONResponse(
        status_code=500,
        content=error_response.to_dict()
    )


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    uvicorn.run(app, host=host, port=port)
