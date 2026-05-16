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
    
    # Tables for listes
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

    # Migration: Add original_filename column if it doesn't exist (for existing DBs)
    try:
        cursor.execute("ALTER TABLE listes ADD COLUMN original_filename TEXT")
    except sqlite3.OperationalError:
        pass # Column already exists

    # Migration: Add printed_at column to patients if it doesn't exist
    try:
        cursor.execute("ALTER TABLE patients ADD COLUMN printed_at TIMESTAMP DEFAULT NULL")
    except sqlite3.OperationalError:
        pass

    # Migration: Add notes column to patients if it doesn't exist
    try:
        cursor.execute("ALTER TABLE patients ADD COLUMN notes TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass

    # Table for patients
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
        printed_at TIMESTAMP DEFAULT NULL,
        notes TEXT DEFAULT NULL,
        FOREIGN KEY (liste_id) REFERENCES listes (id) ON DELETE CASCADE
    )
    ''')
    
    conn.commit()
    conn.close()

def update_patient_notes(patient_id, notes):
    """Update a patient's notes in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE patients SET notes = ? WHERE id = ?",
        (notes.strip() if notes else None, patient_id)
    )
    conn.commit()
    conn.close()

def mark_patient_printed(patient_id):
    """Mark a patient as printed/delivered with current timestamp."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE patients SET printed_at = ? WHERE id = ?",
        (datetime.now().isoformat(), patient_id)
    )
    conn.commit()
    conn.close()

def get_dashboard_stats(liste_id=None):
    """Get aggregate stats for patients, optionally filtered by liste_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    base_query = "FROM patients"
    params = []
    if liste_id:
        base_query += " WHERE liste_id = ?"
        params.append(liste_id)
    
    # Run 4 counts
    cursor.execute(f"SELECT COUNT(*) {base_query}", params)
    total = cursor.fetchone()[0]
    
    pending_cond = "status = 'pending'"
    cursor.execute(f"SELECT COUNT(*) {base_query} {'AND' if liste_id else 'WHERE'} {pending_cond}", params)
    pending = cursor.fetchone()[0]
    
    completed_cond = "status = 'completed'"
    cursor.execute(f"SELECT COUNT(*) {base_query} {'AND' if liste_id else 'WHERE'} {completed_cond}", params)
    completed = cursor.fetchone()[0]
    
    printed_cond = "printed_at IS NOT NULL"
    cursor.execute(f"SELECT COUNT(*) {base_query} {'AND' if liste_id else 'WHERE'} {printed_cond}", params)
    printed = cursor.fetchone()[0]
    
    conn.close()
    return {
        "total": total,
        "pending": pending,
        "completed": completed,
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
        SELECT p.*, l.list_number, l.liste_date 
        FROM patients p 
        JOIN listes l ON p.liste_id = l.id
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
        
    if status_filter and status_filter in ['pending', 'completed']:
        conditions.append("p.status = ?")
        params.append(status_filter)
        
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
    
    query = "SELECT COUNT(*) FROM patients p"
    if search_query or (status_filter and status_filter in ['pending', 'completed']) or liste_id:
        query += " JOIN listes l ON p.liste_id = l.id"
        
    params = []
    conditions = []
    
    if liste_id:
        conditions.append("p.liste_id = ?")
        params.append(liste_id)
    
    if search_query:
        conditions.append("(p.last_name LIKE ? OR p.first_name LIKE ? OR p.patient_json LIKE ?)")
        search_term = f"%{search_query}%"
        params.extend([search_term, search_term, search_term])
        
    if status_filter and status_filter in ['pending', 'completed']:
        conditions.append("p.status = ?")
        params.append(status_filter)
        
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
