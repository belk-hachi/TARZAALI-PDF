"""
Database layer for the Lab PDF Processor.

All SQLite operations are consolidated here. Route handlers should
never write raw SQL — they call functions from this module instead.

Connection lifecycle:
- A new connection is created per-request via get_db() (stored in Flask's g).
- Connections are automatically closed at the end of each request
  via teardown_appcontext.
- For code outside a request context (e.g., backup), use get_db_connection()
  and close manually.

Migration handling:
- init_db() handles three possible states of an existing database:
  State A: Fresh — no tables exist yet.
  State B: Old metadata schema — 3-field key (no liste_date).
  State C: Current — 4-field key with liste_date.
- It also rebuilds the patients table to drop legacy columns if needed.
- This migration logic MUST NOT be simplified — existing users' databases
  may be in any of these three states.
"""

import sqlite3
import json
import logging
from datetime import datetime

from flask import g

from .config import DB_PATH

logger = logging.getLogger(__name__)


# ─── Connection Management ──────────────────────────────────────────────────

def get_db_connection():
    """Create a raw SQLite connection with row factory.

    Use this for code outside Flask request context (e.g., backup, scripts).
    The caller is responsible for closing the connection.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def get_db():
    """Get a request-scoped database connection from Flask's g.

    Creates a new connection on first call within a request, then
    reuses it for the rest of the request. The connection is
    automatically closed by teardown_db().
    """
    if 'db' not in g:
        g.db = get_db_connection()
    return g.db


def teardown_db(exception):
    """Close the request-scoped database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


# ─── Schema Initialization & Migration ──────────────────────────────────────

def init_db():
    """Create tables if they don't exist and handle migrations.

    Safe to call on every startup. Only writes when tables/columns
    are missing. Must be called explicitly from create_app(), NOT
    as a module-level side effect.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Ensure listes table exists
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

    # Migration: Add original_filename column if missing
    try:
        cursor.execute("ALTER TABLE listes ADD COLUMN original_filename TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # 2. Handle patient_metadata migration (State A, B, or C)
    table_exists = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='patient_metadata'"
    ).fetchone()

    if table_exists:
        columns = [
            row[1]
            for row in cursor.execute(
                "PRAGMA table_info(patient_metadata)"
            ).fetchall()
        ]
        if 'liste_date' not in columns:
            # State B: Migrate from 3-field key to 4-field key
            cursor.execute(
                "ALTER TABLE patient_metadata RENAME TO patient_metadata_old"
            )
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
            cursor.execute("""
                INSERT OR IGNORE INTO patient_metadata
                    (last_name, first_name, date_of_birth, liste_date,
                     notes, printed_at)
                SELECT m.last_name, m.first_name, m.date_of_birth,
                       l.liste_date, m.notes, m.printed_at
                FROM patient_metadata_old m
                JOIN patients p
                    ON m.last_name = p.last_name
                   AND m.first_name = p.first_name
                   AND m.date_of_birth = p.date_of_birth
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

    # 3. Handle patients table migration (remove legacy notes/printed_at)
    patients_columns = [
        row[1]
        for row in cursor.execute("PRAGMA table_info(patients)").fetchall()
    ]
    if 'notes' in patients_columns or 'printed_at' in patients_columns:
        # Move leftover data before dropping columns
        cursor.execute("""
            INSERT OR IGNORE INTO patient_metadata
                (last_name, first_name, date_of_birth, liste_date,
                 notes, printed_at)
            SELECT p.last_name, p.first_name, p.date_of_birth,
                   l.liste_date, p.notes, p.printed_at
            FROM patients p
            JOIN listes l ON p.liste_id = l.id
            WHERE p.notes IS NOT NULL OR p.printed_at IS NOT NULL
        """)

        # Rebuild patients table without legacy columns
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
            INSERT INTO patients_new
                (id, liste_id, last_name, first_name, date_of_birth,
                 status, test_count, patient_json)
            SELECT id, liste_id, last_name, first_name, date_of_birth,
                   status, test_count, patient_json
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
    logger.info("Database initialized successfully")


# ─── Liste Operations ───────────────────────────────────────────────────────

def save_extraction_result(extraction_result, original_filename=None):
    """Save the AI extraction result (list + patients) to DB.

    Overwrites if list_number already exists (cascade deletes old patients).
    Returns the liste_id, or None if list_number is missing.
    """
    list_number = (
        extraction_result.get("list_number")
        or extraction_result.get("listNumber")
    )
    if not list_number:
        return None

    conn = get_db()
    cursor = conn.cursor()

    # Delete existing list if present (cascade handles patients)
    cursor.execute(
        "DELETE FROM listes WHERE list_number = ?", (list_number,)
    )

    # Insert list
    cursor.execute(
        "INSERT INTO listes"
        " (list_number, liste_date, print_date, original_filename)"
        " VALUES (?, ?, ?, ?)",
        (
            list_number,
            extraction_result.get("liste_date")
            or extraction_result.get("listeDate"),
            extraction_result.get("print_date")
            or extraction_result.get("printDate"),
            original_filename,
        ),
    )
    liste_id = cursor.lastrowid

    # Insert patients
    patients = extraction_result.get("patients", [])
    for p in patients:
        # Compute status from subtests (duplicated logic for DB-layer
        # self-containment — matches helpers.get_patient_status_summary
        # but also handles "rejected")
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
               (liste_id, last_name, first_name, date_of_birth,
                status, test_count, patient_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                liste_id,
                p.get("lastName"),
                p.get("firstName"),
                p.get("dateOfBirth"),
                status,
                test_count,
                json.dumps(p, ensure_ascii=False),
            ),
        )

    conn.commit()
    return liste_id


def get_all_listes():
    """Get all listes with patient counts, sorted by date descending."""
    conn = get_db()
    cursor = conn.cursor()
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
    return rows


def get_liste_by_id(liste_id):
    """Get a single liste row by ID."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM listes WHERE id = ?", (liste_id,)
    ).fetchone()
    return row


def delete_liste_if_empty(liste_id):
    """Delete an entire list ONLY if it has no patients.

    Returns True if deleted, False if patients exist.
    """
    conn = get_db()
    cursor = conn.cursor()
    count = cursor.execute(
        "SELECT COUNT(*) FROM patients WHERE liste_id = ?", (liste_id,)
    ).fetchone()[0]

    if count == 0:
        cursor.execute("DELETE FROM listes WHERE id = ?", (liste_id,))
        conn.commit()
        return True
    return False


# ─── Patient Queries ────────────────────────────────────────────────────────

def _build_patient_conditions(liste_id=None, search_query=None,
                              status_filter=None):
    """Build WHERE clause and params for patient queries.

    Shared by get_patients() and count_patients() to avoid duplication.
    """
    conditions = []
    params = []

    if liste_id:
        conditions.append("p.liste_id = ?")
        params.append(liste_id)

    if search_query:
        conditions.append(
            "(p.last_name LIKE ? OR p.first_name LIKE ?"
            " OR p.patient_json LIKE ?)"
        )
        search_term = f"%{search_query}%"
        params.extend([search_term, search_term, search_term])

    if status_filter:
        if status_filter in ('pending', 'completed', 'rejected'):
            conditions.append("p.status = ?")
            params.append(status_filter)
        elif status_filter == 'not_printed':
            conditions.append(
                "p.status = 'completed' AND m.printed_at IS NULL"
            )
        elif status_filter == 'printed':
            conditions.append("m.printed_at IS NOT NULL")

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    return where, params


_PATIENT_JOIN = """
    FROM patients p
    JOIN listes l ON p.liste_id = l.id
    LEFT JOIN patient_metadata m
      ON m.last_name = p.last_name
      AND m.first_name = p.first_name
      AND m.date_of_birth = p.date_of_birth
      AND m.liste_date = l.liste_date
"""

_PATIENT_ORDER = """
    ORDER BY
        substr(l.liste_date, 7, 4) DESC,
        substr(l.liste_date, 4, 2) DESC,
        substr(l.liste_date, 1, 2) DESC,
        p.last_name ASC
"""


def get_patients(liste_id=None, search_query=None, status_filter=None,
                 limit=None, offset=None):
    """Get patients with their metadata, filtered and paginated."""
    conn = get_db()
    cursor = conn.cursor()

    where, params = _build_patient_conditions(
        liste_id, search_query, status_filter
    )

    query = (
        "SELECT p.*, l.list_number, l.liste_date, m.notes, m.printed_at"
        + _PATIENT_JOIN
        + where
        + _PATIENT_ORDER
    )

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    if offset is not None:
        query += " OFFSET ?"
        params.append(offset)

    cursor.execute(query, params)
    return cursor.fetchall()


def count_patients(liste_id=None, search_query=None, status_filter=None):
    """Count patients matching the given filters."""
    conn = get_db()
    cursor = conn.cursor()

    where, params = _build_patient_conditions(
        liste_id, search_query, status_filter
    )

    query = "SELECT COUNT(*)" + _PATIENT_JOIN + where
    cursor.execute(query, params)
    return cursor.fetchone()[0]


def get_patient_with_liste(patient_id):
    """Get a patient row joined with its liste info and original filename.

    Returns a Row with all patient columns plus l.list_number,
    l.liste_date, l.print_date, l.original_filename.
    Returns None if patient not found.
    """
    conn = get_db()
    row = conn.execute(
        """SELECT p.*, l.list_number, l.liste_date, l.print_date,
                  l.original_filename
           FROM patients p
           JOIN listes l ON p.liste_id = l.id
           WHERE p.id = ?""",
        (patient_id,),
    ).fetchone()
    return row


def delete_patient(patient_id):
    """Delete a single patient record."""
    conn = get_db()
    conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
    conn.commit()


# ─── Patient Metadata (notes, printed status) ──────────────────────────────

def update_patient_notes(patient_id, notes):
    """Update a patient's notes in patient_metadata (visit-isolated).

    Uses UPSERT with the 4-field identity key.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO patient_metadata
            (last_name, first_name, date_of_birth, liste_date, notes)
        SELECT p.last_name, p.first_name, p.date_of_birth,
               l.liste_date, ?
        FROM patients p
        JOIN listes l ON p.liste_id = l.id
        WHERE p.id = ?
        ON CONFLICT(last_name, first_name, date_of_birth, liste_date)
            DO UPDATE SET notes = excluded.notes
        """,
        (notes.strip() if notes else None, patient_id),
    )
    conn.commit()


def mark_patient_printed(patient_id):
    """Mark a patient as printed/delivered in patient_metadata."""
    conn = get_db()
    cursor = conn.cursor()

    now = datetime.now().isoformat()
    cursor.execute(
        """
        INSERT INTO patient_metadata
            (last_name, first_name, date_of_birth, liste_date, printed_at)
        SELECT p.last_name, p.first_name, p.date_of_birth,
               l.liste_date, ?
        FROM patients p
        JOIN listes l ON p.liste_id = l.id
        WHERE p.id = ?
        ON CONFLICT(last_name, first_name, date_of_birth, liste_date)
            DO UPDATE SET printed_at = excluded.printed_at
        """,
        (now, patient_id),
    )
    conn.commit()


def unmark_patient_printed(patient_id):
    """Unmark a patient as printed/delivered in patient_metadata."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE patient_metadata
        SET printed_at = NULL
        WHERE (last_name, first_name, date_of_birth, liste_date) = (
            SELECT p.last_name, p.first_name, p.date_of_birth,
                   l.liste_date
            FROM patients p
            JOIN listes l ON p.liste_id = l.id
            WHERE p.id = ?
        )
        """,
        (patient_id,),
    )
    conn.commit()


# ─── Patient Identity Update ───────────────────────────────────────────────

def update_patient_identity(patient_id, new_last_name, new_first_name,
                            new_dob):
    """Update patient identity (name, DOB) across both tables.

    This is the most complex write operation in the app:
    1. Updates the patients table.
    2. Updates the patient_metadata table using the 4-field key.
    3. If the new identity already exists in metadata (IntegrityError),
       merges the old record's notes and printed_at into the existing
       one, then deletes the old record.

    Returns (True, None) on success, (False, error_message) on failure.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()

        # Get old identity info
        old_row = cursor.execute(
            """SELECT p.last_name, p.first_name, p.date_of_birth,
                      l.liste_date
               FROM patients p
               JOIN listes l ON p.liste_id = l.id
               WHERE p.id = ?""",
            (patient_id,),
        ).fetchone()

        if not old_row:
            return False, "Patient introuvable"

        old_last, old_first, old_dob, liste_date = old_row

        # 1. Update patients table
        cursor.execute(
            """UPDATE patients
               SET last_name = ?, first_name = ?, date_of_birth = ?
               WHERE id = ?""",
            (new_last_name, new_first_name, new_dob, patient_id),
        )

        # 2. Update patient_metadata with conflict resolution
        try:
            cursor.execute(
                """
                UPDATE patient_metadata
                SET last_name = ?, first_name = ?, date_of_birth = ?
                WHERE last_name = ? AND first_name = ?
                      AND date_of_birth = ? AND liste_date = ?
                """,
                (new_last_name, new_first_name, new_dob,
                 old_last, old_first, old_dob, liste_date),
            )
        except sqlite3.IntegrityError:
            # New identity already exists in metadata — merge
            meta = cursor.execute(
                """
                SELECT notes, printed_at FROM patient_metadata
                WHERE last_name = ? AND first_name = ?
                      AND date_of_birth = ? AND liste_date = ?
                """,
                (old_last, old_first, old_dob, liste_date),
            ).fetchone()

            if meta:
                # Merge into the target (new identity) record
                cursor.execute(
                    """
                    UPDATE patient_metadata
                    SET notes = COALESCE(?, notes),
                        printed_at = COALESCE(?, printed_at)
                    WHERE last_name = ? AND first_name = ?
                          AND date_of_birth = ? AND liste_date = ?
                    """,
                    (meta['notes'], meta['printed_at'],
                     new_last_name, new_first_name, new_dob, liste_date),
                )

                # Delete the old record
                cursor.execute(
                    """
                    DELETE FROM patient_metadata
                    WHERE last_name = ? AND first_name = ?
                          AND date_of_birth = ? AND liste_date = ?
                    """,
                    (old_last, old_first, old_dob, liste_date),
                )

        conn.commit()
        return True, None

    except Exception as e:
        return False, str(e)


# ─── Dashboard Stats ───────────────────────────────────────────────────────

def get_dashboard_stats(liste_id=None):
    """Get aggregate stats for patients, optionally filtered by liste_id.

    Returns a dict with: total, pending, completed, rejected,
    not_printed, printed.
    """
    conn = get_db()
    cursor = conn.cursor()

    params = []
    where_clause = ""
    if liste_id:
        where_clause = "WHERE p.liste_id = ?"
        params.append(liste_id)

    query_base = (
        _PATIENT_JOIN + where_clause
    )

    # Total
    cursor.execute(f"SELECT COUNT(*) {query_base}", params)
    total = cursor.fetchone()[0]

    # Per-status counts
    status_filter = (
        "AND p.status = ?" if where_clause else "WHERE p.status = ?"
    )
    cursor.execute(
        f"SELECT COUNT(*) {query_base} {status_filter}",
        params + ["pending"],
    )
    pending = cursor.fetchone()[0]

    cursor.execute(
        f"SELECT COUNT(*) {query_base} {status_filter}",
        params + ["completed"],
    )
    completed = cursor.fetchone()[0]

    cursor.execute(
        f"SELECT COUNT(*) {query_base} {status_filter}",
        params + ["rejected"],
    )
    rejected = cursor.fetchone()[0]

    # Not printed (completed but not yet delivered)
    not_printed_filter = (
        "AND p.status = 'completed' AND m.printed_at IS NULL"
        if where_clause
        else "WHERE p.status = 'completed' AND m.printed_at IS NULL"
    )
    cursor.execute(
        f"SELECT COUNT(*) {query_base} {not_printed_filter}", params
    )
    not_printed = cursor.fetchone()[0]

    # Printed (delivered)
    printed_filter = (
        "AND m.printed_at IS NOT NULL"
        if where_clause
        else "WHERE m.printed_at IS NOT NULL"
    )
    cursor.execute(
        f"SELECT COUNT(*) {query_base} {printed_filter}", params
    )
    printed = cursor.fetchone()[0]

    return {
        "total": total,
        "pending": pending,
        "completed": completed,
        "rejected": rejected,
        "not_printed": not_printed,
        "printed": printed,
    }
