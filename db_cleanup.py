#!/usr/bin/env python3
"""DB Cleanup Script for Stuck SDR Routine Execution

Routine ID: 254e1aa5-b177-4bb4-9591-cb5ec0bf5f0f
Issue: duplicate key value violates unique constraint issues_open_routine_execution_uq
"""

import sys
import os

# Try to import psycopg2, if not available, provide instructions
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("ERROR: psycopg2 not installed.")
    print("Install with: pip3 install psycopg2-binary --break-system-packages")
    sys.exit(1)

# Database connection config (to be filled in when credentials provided)
DB_CONFIG = {
    "host": "localhost",
    "port": 54329,
    "database": "paperclip",  # Assuming default database name
    "user": None,  # To be provided
    "password": None,  # To be provided
}

ROUTINE_ID = "254e1aa5-b177-4bb4-9591-cb5ec0bf5f0f"


def get_connection():
    """Create database connection."""
    if not DB_CONFIG["user"] or not DB_CONFIG["password"]:
        print("ERROR: Database credentials not configured.")
        print("Set DB_CONFIG user and password variables.")
        sys.exit(1)
    
    return psycopg2.connect(**DB_CONFIG)


def diagnostic_query(conn):
    """Step 1: Find stuck open execution records."""
    print("\n=== STEP 1: Diagnostic Query ===")
    print(f"Finding stuck records for routine: {ROUTINE_ID}")
    
    query = """
        SELECT id, routine_id, status, triggered_at, created_at, updated_at
        FROM routine_runs
        WHERE routine_id = %s
          AND status NOT IN ('failed', 'completed', 'cancelled')
    """
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (ROUTINE_ID,))
        rows = cur.fetchall()
        
        if not rows:
            print("No stuck open records found.")
            return None
        
        print(f"\nFound {len(rows)} stuck record(s):")
        for row in rows:
            print(f"  ID: {row['id']}")
            print(f"  Status: {row['status']}")
            print(f"  Triggered: {row['triggered_at']}")
            print(f"  Created: {row['created_at']}")
            print()
        
        return rows[0]['id']  # Return first stuck record ID


def cleanup_record(conn, record_id):
    """Step 2: Mark stuck record as cancelled."""
    print("\n=== STEP 2: Cleanup ===")
    print(f"Marking record {record_id} as cancelled...")
    
    query = """
        UPDATE routine_runs
        SET status = 'cancelled',
            completed_at = NOW(),
            updated_at = NOW()
        WHERE id = %s
        RETURNING id, status, completed_at, updated_at
    """
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (record_id,))
        result = cur.fetchone()
        conn.commit()
        
        print(f"✓ Record updated:")
        print(f"  ID: {result['id']}")
        print(f"  New status: {result['status']}")
        print(f"  Completed at: {result['completed_at']}")
        print(f"  Updated at: {result['updated_at']}")


def verification_query(conn):
    """Step 3: Verify no open records remain."""
    print("\n=== STEP 3: Verification ===")
    print("Checking for remaining open records...")
    
    query = """
        SELECT COUNT(*) as open_count
        FROM routine_runs
        WHERE routine_id = %s
          AND status NOT IN ('failed', 'completed', 'cancelled')
    """
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (ROUTINE_ID,))
        result = cur.fetchone()
        open_count = result['open_count']
        
        if open_count == 0:
            print(f"✓ SUCCESS: No open records found (count: {open_count})")
            print("  Constraint violation should be resolved.")
            return True
        else:
            print(f"✗ WARNING: {open_count} open record(s) still exist")
            return False


def main():
    """Execute DB cleanup workflow."""
    print("=" * 60)
    print("DB Cleanup for Stuck SDR Routine Execution")
    print("=" * 60)
    print(f"Routine ID: {ROUTINE_ID}")
    print(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print()
    
    try:
        conn = get_connection()
        print("✓ Database connection established")
        
        # Step 1: Diagnostic
        stuck_record_id = diagnostic_query(conn)
        
        if not stuck_record_id:
            print("\nNo cleanup needed. Exiting.")
            conn.close()
            return 0
        
        # Step 2: Cleanup
        cleanup_record(conn, stuck_record_id)
        
        # Step 3: Verification
        success = verification_query(conn)
        
        conn.close()
        
        print("\n" + "=" * 60)
        if success:
            print("✓ CLEANUP COMPLETE")
            print("=" * 60)
            print("\nNext routine run should succeed.")
            print("Monitor routine execution at next :00, :15, :30, :45 interval.")
            return 0
        else:
            print("✗ CLEANUP INCOMPLETE")
            print("=" * 60)
            print("\nAdditional stuck records found. Manual review needed.")
            return 1
            
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
