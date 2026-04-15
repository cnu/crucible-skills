/**
 * SearchModal Component
 * Real-time file search with keyboard shortcut (Cmd/Ctrl+K)
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import './SearchModal.css';

interface SearchResult {
  document_id: string;
  filename: string;
  file_type: string;
  account_name?: string;
  uploaded_at: string;
  score: number;
  highlight: string;
}

interface FilterOptions {
  file_types: Array<{ type: string; count: number }>;
  accounts: Array<{ id: string; name: string; count: number }>;
}

export const SearchModal: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [processingTime, setProcessingTime] = useState(0);
  const [filters, setFilters] = useState<FilterOptions>({ file_types: [], accounts: [] });
  const [selectedFilters, setSelectedFilters] = useState<{
    file_type?: string;
    account?: string;
  }>({});
  const [error, setError] = useState<string | null>(null);
  
  const searchTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Keyboard shortcut: Cmd/Ctrl + K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsOpen(true);
      }
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  // Debounced search
  const performSearch = useCallback(async (searchQuery: string) => {
    if (!searchQuery.trim()) {
      setResults([]);
      setTotal(0);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({
        q: searchQuery,
        limit: '20',
        ...(selectedFilters.file_type && { type: selectedFilters.file_type }),
        ...(selectedFilters.account && { account: selectedFilters.account }),
      });

      const response = await fetch(`/api/search/?${params}`);
      const data = await response.json();

      if (data.success) {
        setResults(data.results);
        setTotal(data.total);
        setProcessingTime(data.processing_time_ms);
        setFilters(data.filters);
      } else {
        setError(data.error || 'Search failed');
      }
    } catch (err) {
      setError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [selectedFilters]);

  // Handle query change with debounce
  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    searchTimeoutRef.current = setTimeout(() => {
      performSearch(query);
    }, 200); // 200ms debounce

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, [query, performSearch]);

  const handleResultClick = (result: SearchResult) => {
    // Navigate to document or account
    console.log('Navigate to:', result.document_id);
    setIsOpen(false);
  };

  const toggleFilter = (type: 'file_type' | 'account', value: string) => {
    setSelectedFilters(prev => ({
      ...prev,
      [type]: prev[type] === value ? undefined : value,
    }));
  };

  const clearFilters = () => {
    setSelectedFilters({});
  };

  // Format file size (placeholder - would come from API)
  const formatFileType = (type: string) => {
    const typeMap: Record<string, string> = {
      'pdf': '📄 PDF',
      'contract': '📝 Contract',
      'invoice': '💰 Invoice',
      'call_transcript': '🎙️ Transcript',
      'note': '📋 Note',
    };
    return typeMap[type] || type;
  };

  // Format date
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  if (!isOpen) {
    return (
      <div className="search-shortcut-hint">
        <kbd>Cmd</kbd>+<kbd>K</kbd> to search
      </div>
    );
  }

  return (
    <div className="search-modal-overlay" onClick={() => setIsOpen(false)}>
      <div className="search-modal" onClick={(e) => e.stopPropagation()}>
        {/* Search Header */}
        <div className="search-header">
          <div className="search-input-wrapper">
            <svg className="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <circle cx="11" cy="11" r="8" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
            <input
              ref={inputRef}
              type="text"
              className="search-input"
              placeholder="Search documents, contracts, invoices..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {query && (
              <button
                className="clear-button"
                onClick={() => setQuery('')}
                aria-label="Clear search"
              >
                ×
              </button>
            )}
          </div>
          <button className="close-button" onClick={() => setIsOpen(false)}>
            <kbd>ESC</kbd>
          </button>
        </div>

        {/* Filters */}
        {(filters.file_types.length > 0 || filters.accounts.length > 0) && (
          <div className="search-filters">
            <div className="filter-section">
              <span className="filter-label">Type:</span>
              {filters.file_types.map((ft) => (
                <button
                  key={ft.type}
                  className={`filter-chip ${selectedFilters.file_type === ft.type ? 'active' : ''}`}
                  onClick={() => toggleFilter('file_type', ft.type)}
                >
                  {formatFileType(ft.type)}
                  <span className="count">{ft.count}</span>
                </button>
              ))}
            </div>

            {filters.accounts.length > 0 && (
              <div className="filter-section">
                <span className="filter-label">Account:</span>
                {filters.accounts.slice(0, 5).map((account) => (
                  <button
                    key={account.id}
                    className={`filter-chip ${selectedFilters.account === account.id ? 'active' : ''}`}
                    onClick={() => toggleFilter('account', account.id)}
                  >
                    {account.name}
                    <span className="count">{account.count}</span>
                  </button>
                ))}
              </div>
            )}

            {(selectedFilters.file_type || selectedFilters.account) && (
              <button className="clear-filters" onClick={clearFilters}>
                Clear filters
              </button>
            )}
          </div>
        )}

        {/* Results */}
        <div className="search-results">
          {loading && (
            <div className="search-loading">
              <div className="spinner"></div>
              <span>Searching...</span>
            </div>
          )}

          {error && (
            <div className="search-error">
              <span className="error-icon">⚠️</span>
              {error}
            </div>
          )}

          {!loading && !error && query && results.length === 0 && (
            <div className="search-empty">
              <div className="empty-icon">🔍</div>
              <p>No results for "{query}"</p>
              <span>Try different keywords or filters</span>
            </div>
          )}

          {!loading && !error && results.length > 0 && (
            <>
              <div className="results-header">
                <span className="results-count">
                  {total} result{total !== 1 ? 's' : ''}
                </span>
                <span className="results-time">{processingTime}ms</span>
              </div>

              <div className="results-list">
                {results.map((result) => (
                  <div
                    key={result.document_id}
                    className="result-item"
                    onClick={() => handleResultClick(result)}
                  >
                    <div className="result-icon">
                      {formatFileType(result.file_type)}
                    </div>
                    <div className="result-content">
                      <div className="result-title">{result.filename}</div>
                      <div
                        className="result-highlight"
                        dangerouslySetInnerHTML={{ __html: result.highlight }}
                      />
                      <div className="result-meta">
                        {result.account_name && (
                          <span className="result-account">{result.account_name}</span>
                        )}
                        <span className="result-date">
                          {formatDate(result.uploaded_at)}
                        </span>
                      </div>
                    </div>
                    <div className="result-score">
                      {Math.round(result.score * 100)}%
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {!query && !loading && (
            <div className="search-placeholder">
              <div className="placeholder-icon">🔎</div>
              <p>Start typing to search</p>
              <div className="search-tips">
                <span>Search across contracts, invoices, transcripts, and notes</span>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="search-footer">
          <div className="footer-shortcuts">
            <span><kbd>↑</kbd><kbd>↓</kbd> to navigate</span>
            <span><kbd>↵</kbd> to select</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SearchModal;
