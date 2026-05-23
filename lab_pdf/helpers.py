"""
Utility functions for patient data analysis.

Pure functions with no side effects — safe to call from any context.
"""

import re


def get_patient_status_summary(patient):
    """Get a summary status for a patient based on their tests.

    Returns one of: "pending", "rejected", or "completed".
    - If any subtest is "pending", the patient is pending.
    - If any subtest is "rejected" (and none pending), the patient is rejected.
    - Otherwise, the patient is completed.
    """
    statuses = set()
    for test in patient.get("tests", []):
        for sub in test.get("subTests", []):
            statuses.add(sub.get("status", "completed"))

    if "pending" in statuses:
        return "pending"
    if "rejected" in statuses:
        return "rejected"
    return "completed"


def get_patient_status_details(patient):
    """Get detailed status for each subtest of a patient.

    Returns a list of dicts with name, status, result, and isAbnormal
    for every subtest across all test groups.
    """
    details = []
    for test in patient.get("tests", []):
        for sub in test.get("subTests", []):
            details.append({
                "name": sub.get("subtestName", ""),
                "status": sub.get("status", "completed"),
                "result": sub.get("result", ""),
                "isAbnormal": sub.get("isAbnormal", False),
            })
    return details


def get_cijoint_pages(patient):
    """Collect all unique non-null ciJointPage values from a patient's subtests.

    Returns a sorted list of 1-based page numbers that should be merged
    from the source PDF into the patient's generated report.
    """
    pages = set()
    for test in patient.get("tests", []):
        for sub in test.get("subTests", []):
            p = sub.get("ciJointPage")
            if p is not None:
                try:
                    pages.add(int(p))
                except (ValueError, TypeError):
                    pass
    return sorted(pages)


def make_patient_filename(patient, suffix=""):
    """Build a filename string for a patient's generated PDF.

    Format: LASTNAME_FIRSTNAME_<sanitized_sampleDate>[_suffix].pdf
    The date portion is the sampleDate with all non-digit chars stripped.
    """
    last_name = patient.get("lastName", "unknown")
    first_name = patient.get("firstName", "unknown")
    sample_date = patient.get("sampleDate", "")
    date_suffix = re.sub(r'[^0-9]', '', sample_date)

    if date_suffix:
        base = f"{last_name}_{first_name}_{date_suffix}"
    else:
        base = f"{last_name}_{first_name}"

    if suffix:
        return f"{base}_{suffix}.pdf"
    return f"{base}.pdf"


def validate_filename(filename):
    """Validate that a filename doesn't contain path traversal sequences.

    Prevents directory traversal attacks in routes that accept filenames
    from URL parameters (e.g., /pdf/<filename>).
    """
    if not filename:
        return False
    # Block path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        return False
    # Only allow reasonable filename characters
    if not re.match(r'^[\w\-. ]+$', filename):
        return False
    return True
