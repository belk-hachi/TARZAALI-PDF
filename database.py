import sqlite3
import os
import json
from datetime import datetime

import sys

# For the DB, we want it to live in the same folder as the EXE/Script
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "lab.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")  # Ensure cascade delete works
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Ensure listes table exists (needed for metadata migration)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS listes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        list_number TEXT UNIQUE,
        liste_date TEXT,
        print_date TEXT,
        original_filename TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Migration: Add original_filename column if it doesn't exist
    try:
        cursor.execute("ALTER TABLE listes ADD COLUMN original_filename TEXT")
    except sqlite3.OperationalError:
        pass

    # 2. Handle patient_metadata migration (State A, B, or C)
    table_exists = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='patient_metadata'"
    ).fetchone()

    if table_exists:
        columns = [row[1] for row in cursor.execute("PRAGMA table_info(patient_metadata)").fetchall()]
        if 'liste_date' not in columns:
            # State B: Migrate from 3-field key to 4-field key
            cursor.execute("ALTER TABLE patient_metadata RENAME TO patient_metadata_old")
            cursor.execute('''
            CREATE TABLE patient_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                last_name TEXT NOT NULL,
                first_name TEXT NOT NULL,
                date_of_birth TEXT NOT NULL,
                liste_date TEXT NOT NULL,
                notes TEXT DEFAULT NULL,
                printed_at TIMESTAMP DEFAULT NULL,
                UNIQUE(last_name, first_name, date_of_birth, liste_date)
            )
            ''')
            # Populating liste_date by joining with existing patient rows
            cursor.execute("""
                INSERT OR IGNORE INTO patient_metadata (last_name, first_name, date_of_birth, liste_date, notes, printed_at)
                SELECT m.last_name, m.first_name, m.date_of_birth, l.liste_date, m.notes, m.printed_at
                FROM patient_metadata_old m
                JOIN patients p ON m.last_name = p.last_name AND m.first_name = p.first_name AND m.date_of_birth = p.date_of_birth
                JOIN listes l ON p.liste_id = l.id
            """)
            cursor.execute("DROP TABLE patient_metadata_old")
    else:
        # State A: Fresh creation
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS patient_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            last_name TEXT NOT NULL,
            first_name TEXT NOT NULL,
            date_of_birth TEXT NOT NULL,
            liste_date TEXT NOT NULL,
            notes TEXT DEFAULT NULL,
            printed_at TIMESTAMP DEFAULT NULL,
            UNIQUE(last_name, first_name, date_of_birth, liste_date)
        )
        ''')

    # 3. Handle patients table migration (remove notes and printed_at)
    patients_columns = [row[1] for row in cursor.execute("PRAGMA table_info(patients)").fetchall()]
    if 'notes' in patients_columns or 'printed_at' in patients_columns:
        # Move any leftover data from patients table to metadata before dropping columns
        cursor.execute("""
            INSERT OR IGNORE INTO patient_metadata (last_name, first_name, date_of_birth, liste_date, notes, printed_at)
            SELECT p.last_name, p.first_name, p.date_of_birth, l.liste_date, p.notes, p.printed_at
            FROM patients p
            JOIN listes l ON p.liste_id = l.id
            WHERE p.notes IS NOT NULL OR p.printed_at IS NOT NULL
        """)

        # Recreate patients table without the redundant columns
        cursor.execute('''
        CREATE TABLE patients_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            liste_id INTEGER,
            last_name TEXT,
            first_name TEXT,
            date_of_birth TEXT,
            status TEXT,
            test_count INTEGER,
            patient_json TEXT,
            FOREIGN KEY (liste_id) REFERENCES listes (id) ON DELETE CASCADE
        )
        ''')
        cursor.execute("""
            INSERT INTO patients_new (id, liste_id, last_name, first_name, date_of_birth, status, test_count, patient_json)
            SELECT id, liste_id, last_name, first_name, date_of_birth, status, test_count, patient_json
            FROM patients
        """)
        cursor.execute("DROP TABLE patients")
        cursor.execute("ALTER TABLE patients_new RENAME TO patients")
    else:
        # Standard creation/check
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            liste_id INTEGER,
            last_name TEXT,
            first_name TEXT,
            date_of_birth TEXT,
            status TEXT,
            test_count INTEGER,
            patient_json TEXT,
            FOREIGN KEY (liste_id) REFERENCES listes (id) ON DELETE CASCADE
        )
        ''')
    
    conn.commit()
    conn.close()

def update_patient_notes(patient_id, notes):
    """Update a patient's notes in the patient_metadata table (visit-isolated)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Upsert into patient_metadata using 4-field identity key (includes liste_date)
    cursor.execute("""
        INSERT INTO patient_metadata (last_name, first_name, date_of_birth, liste_date, notes)
        SELECT p.last_name, p.first_name, p.date_of_birth, l.liste_date, ?
        FROM patients p
        JOIN listes l ON p.liste_id = l.id
        WHERE p.id = ?
        ON CONFLICT(last_name, first_name, date_of_birth, liste_date)
        DO UPDATE SET notes = excluded.notes
    """, (notes.strip() if notes else None, patient_id))
    
    conn.commit()
    conn.close()

def mark_patient_printed(patient_id):
    """Mark a patient as printed/delivered in patient_metadata table (visit-isolated)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO patient_metadata (last_name, first_name, date_of_birth, liste_date, printed_at)
        SELECT p.last_name, p.first_name, p.date_of_birth, l.liste_date, ?
        FROM patients p
        JOIN listes l ON p.liste_id = l.id
        WHERE p.id = ?
        ON CONFLICT(last_name, first_name, date_of_birth, liste_date)
        DO UPDATE SET printed_at = excluded.printed_at
    """, (now, patient_id))
    
    conn.commit()
    conn.close()

def unmark_patient_printed(patient_id):
    """Unmark a patient as printed/delivered in patient_metadata table (visit-isolated)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE patient_metadata
        SET printed_at = NULL
        WHERE (last_name, first_name, date_of_birth, liste_date) = (
            SELECT p.last_name, p.first_name, p.date_of_birth, l.liste_date
            FROM patients p
            JOIN listes l ON p.liste_id = l.id
            WHERE p.id = ?
        )
    """, (patient_id,))
    
    conn.commit()
    conn.close()

def get_dashboard_stats(liste_id=None):
    """Get aggregate stats for patients, optionally filtered by liste_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    params = []
    where_clause = ""
    if liste_id:
        where_clause = "WHERE p.liste_id = ?"
        params.append(liste_id)
        
    query_base = f"""
        FROM patients p
        JOIN listes l ON p.liste_id = l.id
        LEFT JOIN patient_metadata m 
          ON m.last_name = p.last_name 
          AND m.first_name = p.first_name 
          AND m.date_of_birth = p.date_of_birth
          AND m.liste_date = l.liste_date
        {where_clause}
    """
    
    cursor.execute(f"SELECT COUNT(*) {query_base}", params)
    total = cursor.fetchone()[0]
    
    status_filter = "AND p.status = ?" if where_clause else "WHERE p.status = ?"
    cursor.execute(f"SELECT COUNT(*) {query_base} {status_filter}", params + ["pending"])
    pending = cursor.fetchone()[0]
    
    cursor.execute(f"SELECT COUNT(*) {query_base} {status_filter}", params + ["completed"])
    completed = cursor.fetchone()[0]
    
    not_printed_filter = "AND p.status = 'completed' AND m.printed_at IS NULL" if where_clause else "WHERE p.status = 'completed' AND m.printed_at IS NULL"
    cursor.execute(f"SELECT COUNT(*) {query_base} {not_printed_filter}", params)
    not_printed = cursor.fetchone()[0]
    
    printed_filter = "AND m.printed_at IS NOT NULL" if where_clause else "WHERE m.printed_at IS NOT NULL"
    cursor.execute(f"SELECT COUNT(*) {query_base} {printed_filter}", params)
    printed = cursor.fetchone()[0]
    
    conn.close()
    return {
        "total": total,
        "pending": pending,
        "completed": completed,
        "not_printed": not_printed,
        "printed": printed
    }

def save_extraction_result(extraction_result, original_filename=None):
    """
    Save the AI extraction result (list + patients) to DB.
    Overwrites if list_number already exists.
    """
    list_number = extraction_result.get("list_number") or extraction_result.get("listNumber")
    if not list_number:
        return None

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Delete if exists (Cascade will handle patients)
    cursor.execute("DELETE FROM listes WHERE list_number = ?", (list_number,))
    
    # 2. Insert list
    cursor.execute(
        "INSERT INTO listes (list_number, liste_date, print_date, original_filename) VALUES (?, ?, ?, ?)",
        (
            list_number,
            extraction_result.get("liste_date") or extraction_result.get("listeDate"),
            extraction_result.get("print_date") or extraction_result.get("printDate"),
            original_filename
        )
    )
    liste_id = cursor.lastrowid
    
    # 3. Insert patients
    patients = extraction_result.get("patients", [])
    for p in patients:
        # Calculate summary info
        # logic duplicated from app.py to keep database.py self-contained
        statuses = set()
        tests = p.get("tests", [])
        for test in tests:
            for sub in test.get("subTests", []):
                statuses.add(sub.get("status", "completed"))
        
        if "pending" in statuses:
            status = "pending"
        elif "rejected" in statuses:
            status = "rejected"
        else:
            status = "completed"
        test_count = len(tests)
        
        cursor.execute(
            """INSERT INTO patients 
               (liste_id, last_name, first_name, date_of_birth, status, test_count, patient_json) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                liste_id,
                p.get("lastName"),
                p.get("firstName"),
                p.get("dateOfBirth"),
                status,
                test_count,
                json.dumps(p, ensure_ascii=False)
            )
        )
    
    conn.commit()
    conn.close()
    return liste_id

def get_all_listes():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Joined query to get patient counts per list
    # Sorting DD/MM/YYYY correctly requires substr manipulation
    cursor.execute("""
        SELECT l.*, COUNT(p.id) as patient_count 
        FROM listes l 
        LEFT JOIN patients p ON l.id = p.liste_id 
        GROUP BY l.id 
        ORDER BY 
            substr(l.liste_date, 7, 4) DESC, 
            substr(l.liste_date, 4, 2) DESC, 
            substr(l.liste_date, 1, 2) DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_patients(liste_id=None, search_query=None, status_filter=None, limit=None, offset=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT p.*, l.list_number, l.liste_date,
               m.notes, m.printed_at
        FROM patients p 
        JOIN listes l ON p.liste_id = l.id
        LEFT JOIN patient_metadata m 
          ON m.last_name = p.last_name 
          AND m.first_name = p.first_name 
          AND m.date_of_birth = p.date_of_birth
          AND m.liste_date = l.liste_date
    """
    params = []
    conditions = []
    
    if liste_id:
        conditions.append("p.liste_id = ?")
        params.append(liste_id)
    
    if search_query:
        # Search in first_name, last_name, or within the patient_json (for test names)
        conditions.append("(p.last_name LIKE ? OR p.first_name LIKE ? OR p.patient_json LIKE ?)")
        search_term = f"%{search_query}%"
        params.extend([search_term, search_term, search_term])
        
    if status_filter:
        if status_filter in ['pending', 'completed']:
            conditions.append("p.status = ?")
            params.append(status_filter)
        elif status_filter == 'not_printed':
            conditions.append("p.status = 'completed' AND m.printed_at IS NULL")
        elif status_filter == 'printed':
            conditions.append("m.printed_at IS NOT NULL")
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    # Order by list date (chrono) then name
    query += """ ORDER BY 
                substr(l.liste_date, 7, 4) DESC, 
                substr(l.liste_date, 4, 2) DESC, 
                substr(l.liste_date, 1, 2) DESC, 
                p.last_name ASC"""
    
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    if offset is not None:
        query += " OFFSET ?"
        params.append(offset)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows

def count_patients(liste_id=None, search_query=None, status_filter=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT COUNT(*) 
        FROM patients p 
        JOIN listes l ON p.liste_id = l.id
        LEFT JOIN patient_metadata m 
          ON m.last_name = p.last_name 
          AND m.first_name = p.first_name 
          AND m.date_of_birth = p.date_of_birth
          AND m.liste_date = l.liste_date
    """
        
    params = []
    conditions = []
    
    if liste_id:
        conditions.append("p.liste_id = ?")
        params.append(liste_id)
    
    if search_query:
        conditions.append("(p.last_name LIKE ? OR p.first_name LIKE ? OR p.patient_json LIKE ?)")
        search_term = f"%{search_query}%"
        params.extend([search_term, search_term, search_term])
        
    if status_filter:
        if status_filter in ['pending', 'completed']:
            conditions.append("p.status = ?")
            params.append(status_filter)
        elif status_filter == 'not_printed':
            conditions.append("p.status = 'completed' AND m.printed_at IS NULL")
        elif status_filter == 'printed':
            conditions.append("m.printed_at IS NOT NULL")
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    cursor.execute(query, params)
    count = cursor.fetchone()[0]
    conn.close()
    return count

def delete_patient(patient_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
    conn.commit()
    conn.close()

# Auto-init on import
init_db()
