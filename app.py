import os
import sys
import json
import re
import uuid
import base64
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from pypdf import PdfReader, PdfWriter
from google import genai
import database

def obscure_password(password):
    """Simple Base64 obfuscation."""
    if not password: return ""
    return base64.b64encode(password.encode()).decode()

def deobscure_password(obscured):
    """Decode simple Base64 obfuscation."""
    if not obscured: return ""
    try:
        return base64.b64decode(obscured.encode()).decode()
    except Exception:
        return ""

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

app = Flask(__name__, 
            template_folder=resource_path("templates"))

app.secret_key = os.environ.get("SECRET_KEY", "lab-pdf-secret-key-change-me")

# Register custom Jinja filter
@app.template_filter('from_json')
def from_json_filter(s):
    return json.loads(s)

# ─── Configuration & Paths ──────────────────────────────────────────────────

# For writable data (DB, Uploads, Logs), we use the folder where the EXE is located
if getattr(sys, 'frozen', False):
    # If running as an EXE
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # If running as a script
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
GENERATED_DIR = os.path.join(BASE_DIR, "generated")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# For read-only assets (bundled inside the EXE)
LOGO_PATH = resource_path("logo.jpg")

# External Files (next to the EXE)
KEY_FILE_PATH = os.path.join(BASE_DIR, "gemini_key.txt")
PROMPT_PATH = os.path.join(BASE_DIR, "prompt.md")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

def load_config():
    """Load configuration from config.json with fallback to gemini_key.txt."""
    config = {
        "api_key": "", 
        "model": "gemini-2.5-flash",
        "online_username": "",
        "online_password": "",
        "lab_dr_name": "IBN SINA. Dr N.KACI",
        "lab_addr_l1": "Boulevard Amir Abdelkader, Cité nouvelle",
        "lab_addr_l2": "mosquée 205 N°1 et 2. DJELFA",
        "lab_tel": "027902479",
        "lab_fax": "027902479",
        "lab_mobile": "0671013704"
    }
    
    # 1. Try to load from config.json
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Decrypt password before using in app
                if data.get("online_password"):
                    data["online_password"] = deobscure_password(data["online_password"])
                config.update(data)
        except Exception as e:
            print(f"[Config] Error loading config.json: {e}")
            
    # 2. If api_key is still empty, try fallback to gemini_key.txt
    if not config.get("api_key") and os.path.exists(KEY_FILE_PATH):
        try:
            with open(KEY_FILE_PATH, "r", encoding="utf-8") as f:
                key = f.read().strip()
                if key:
                    config["api_key"] = key
        except Exception as e:
            print(f"[Config] Error loading gemini_key.txt: {e}")
            
    return config

def save_config(config):
    """Save configuration to config.json with password obfuscation."""
    to_save = config.copy()
    if to_save.get("online_password"):
        to_save["online_password"] = obscure_password(to_save["online_password"])
    
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2)

def init_external_files():
    """Ensure config.json and prompt.md exist next to the EXE."""
    # 1. Handle Config
    if not os.path.exists(CONFIG_FILE):
        # Initial config
        initial_config = load_config()
        save_config(initial_config)
        print(f"[Init] Created {CONFIG_FILE}")

    # 2. Handle Prompt
    if not os.path.exists(PROMPT_PATH):
        bundled_prompt_path = resource_path("prompt.md")
        content = ""
        
        # Try reading from bundle
        if os.path.exists(bundled_prompt_path):
            with open(bundled_prompt_path, "r", encoding="utf-8") as f:
                content = f.read()
        
        # Fallback to a sensible default if bundle was empty or missing
        if not content.strip():
            content = """# You are a data extraction assistant for a medical laboratory.
I will give you a PDF lab report. Your job is to extract all patient and test result data from it and return it as a single valid JSON object.
The JSON must follow this exact structure:
{
    "listNumber": <string — extract the full list identifier exactly as it appears, e.g. "LISTE_SD_620_73470", or null>,
    "listeDate": <"DD/MM/YYYY" or null>,
    "printDate": <"DD/MM/YYYY" or null>,
    "patients": [
        {
        "lastName": <string, UPPERCASE>,
        "firstName": <string>,
        "dateOfBirth": <"DD/MM/YYYY">,
        "sampleDate": <"DD/MM/YYYY HH:MM:SS">,
        "tests": [
            {
                "testName": <string>,
                "subTests": [
                    {
                    "subtestName": <string>,
                    "result": <string or number>,
                    "normalRange": <string>,
                    "unit": <string or null>,
                    "isAbnormal": <true if result marked with * or in red, else false>,
                    "status": <"completed" if result is a value, "pending" if "En Cours" or "Non Trié" or "En Validation" or "En Attente" or unresolved Ci-Joint>,
                    "method": <string — the italic text below this subtest, or "" if none>,
                    "observation": <string — the text after "Observation:" label, or "" if none>,
                    "ciJointPage": <integer — the 1-based page number where the attached annex page for this subtest is located, or null>
                    }
                ]
            }
            ]
            }
    ]
}
Rules:
Extract EVERY patient, test, and subtest — do not skip any
"method" is the small italic line directly below the subtest result (e.g. "ROCHE - ECLIA électrochimiluminescence sandwich sur Cobas 6000(e)-1")
"observation" is the text that follows the "Observation:" label — copy it in full
If a result has an asterisk (*) or appears in red, set isAbnormal to true
result "<0.040" or similar → keep as string, set isAbnormal based on context
normalRange "Aucune" → keep as "Aucune"
Do NOT invent or guess any method or observation — if not present in the PDF, use ""
A result displayed as / (a single forward slash) means no value was entered — keep it as "/" in the result field, do not replace it with an empty string.


Deduplication — CRITICAL:
This PDF is a batch report containing multiple patients across multiple pages. The same patient may appear on more than one page with different tests on each page. When building the JSON, each patient must appear ONCE only. If you encounter the same patient (matched by lastName + firstName + sampleDate) on a second or third page, merge their tests into the single existing entry for that patient — do not create a duplicate patient entry. Similarly, if the exact same testName + subtestName combination already exists for a patient, do not add it again — keep only the first occurrence.

Patient completeness — CRITICAL:
A patient's results may span 2, 3, or more consecutive pages. The boundary between one patient and the next is ALWAYS and ONLY the next >> LASTNAME FIRSTNAME << header line. Do NOT consider a patient complete until you have seen that next header. Specifically:
- A page break in the middle of a patient's tests does NOT end that patient's record.
- Tests that appear at the very bottom of a page, immediately before a page break, belong to the current patient — do not drop them.
- After finishing a patient, verify that ALL tests visible between their >> NAME << header and the next >> NAME << header have been captured, including tests that spill onto the following page.
- WARNING: A single patient's tests can span 3 or more pages. You MUST read ALL pages before closing any patient entry. The ONLY valid signal that a patient is complete is the appearance of the next >> LASTNAME FIRSTNAME << header — never a page break.

Ci-Joint handling — CRITICAL, read carefully:
When a subtest result is "Ci-Joint", there is a separate annex page elsewhere in the PDF that belongs to this subtest. Your ONLY job here is to find that page number and set ciJointPage to it. Do NOT change the result — it stays "Ci-Joint". Do NOT extract or rewrite anything from the annex page.
STEP 1 — Find the annex page: Scan ALL pages of the PDF, especially from the middle to the end. Annex pages look completely different from the results pages — they do not have the standard lab results table. Instead they show a graph or detailed data table for a specific test (e.g. a protein electrophoresis curve, an allergen panel, etc.). The patient's name on these annex pages appears on the very first line in this format: "DD/MM/YYYY  NNN  LASTNAME FIRSTNAME" (e.g. "07/05/2026  129  BOUKOUFALA LARBI"). Match by last name only — ignore the date, the number, accent differences, or word order.
STEP 2 — Confirm the test type: The annex page must relate to the same test as the "Ci-Joint" subtest. Use keyword matching — it does not need to be exact:

For "Électrophorèse des protéines sériques": match any page containing "CAPILLARYS PROTEIN", "Electrophorèse des protéines sériques", or fraction headers (Albumine, Alpha 1, Alpha 2, Beta 1, Beta 2, Gamma).
For "IgE spécifiques" or allergen panels: match any page containing "IgE", "Panel", "Allergène", "EUROLINE", or allergen result tables.
For other tests: use the most specific keyword from the test name.

STEP 3 — Set ciJointPage: Once you have confirmed the matching annex page, set ciJointPage to its 1-based page number in the PDF. Keep result as "Ci-Joint", keep status as "completed", keep isAbnormal as false unless the main results page already marked it abnormal.
STEP 4 — Only if you have scanned every page and truly cannot find ANY annex page matching both this patient's last name and this test type: keep result as "Ci-Joint", status "pending", ciJointPage null.
IMPORTANT: ciJointPage must never be null when a matching annex page exists in the PDF. Leaving it null means the annex page will not be attached to the patient's report.
CRITICAL: Any double quotes (") inside string values MUST be replaced with single quotes (') to keep the JSON valid. For example, if the PDF contains: ABBOTT - "CMIA" immunologie microparticulaire par chimiluminescence sur Architect i2000SR-2, you MUST output: "ABBOTT - 'CMIA' immunologie microparticulaire par chimiluminescence sur Architect i2000SR-2". NEVER leave unescaped double quotes inside a JSON string value.
CRITICAL: The patient header line format is: >> LASTNAME FIRSTNAME  Né(e) le DD/MM/YYYY "Né(e)" is NOT part of the name. lastName = first word(s) in UPPERCASE, firstName = remaining words before "Né(e)". Never put "Né(e)" in firstName.
CRITICAL: Do NOT use Unicode escape sequences like \u00df, \u00b2, etc. Any special characters from the PDF must be written as their plain equivalent: β (Greek beta) → write as "B", ² (superscript 2) → write as "2", ß (German sharp S) → write as "B". For example, "β2-Glycoprotéine" → write as "B2-Glycoprotéine", "µU/mL" → write as "uU/mL". This ensures the JSON is ASCII-safe and avoids encoding issues.
CRITICAL: Every string value MUST be on a SINGLE line. NEVER insert line breaks or newlines inside a JSON string value. Long strings like method or observation must stay on one line — do NOT wrap or break them across multiple lines. A line break inside a string makes the JSON invalid and unparseable. Line breaks are ONLY allowed between key-value pairs, never inside values.
Return ONLY the JSON object, no explanation, no markdown, no code fences
"""

        with open(PROMPT_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[Init] Created {PROMPT_PATH} with default instructions.")

def get_api_key():
    """Read API key from config.json or fallback to gemini_key.txt."""
    return load_config().get("api_key", "")

# Ensure folders and external files exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
init_external_files()


# ─── Helpers ────────────────────────────────────────────────────────────────

def load_prompt():
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def save_ai_log(prompt, input_text, output_json):
    """Save the prompt, input text, and AI response to a log file for diagnosis."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_id = str(uuid.uuid4())[:8]
    log_filename = f"ai_log_{timestamp}_{log_id}.json"
    log_path = os.path.join(LOGS_DIR, log_filename)
    
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "prompt": prompt,
        "input_text": input_text,
        "output_json": output_json
    }
    
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    print(f"[LOG] AI transaction saved to {log_filename}")


def call_ai_for_extraction(pdf_path, prompt, model_name=None):
    """Send PDF file directly to Gemini. Works with scanned PDFs too."""
    from google.genai import types

    config = load_config()
    api_key = config.get("api_key")
    if model_name is None:
        model_name = config.get("model", "gemini-2.5-flash")

    if not api_key:
        raise Exception("Clé API Gemini manquante. Veuillez coller votre clé dans les paramètres ou 'gemini_key.txt' and relancer l'extraction.")

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                types.Part.from_text(text=prompt)
            ]
        )
        raw_text = response.text.strip()
    except Exception as e:
        raise Exception(f"Gemini API call failed: {str(e)}")

    if raw_text.startswith("```"):
        raw_text = re.sub(r'^```(?:json)?\s*\n?', '', raw_text)
        raw_text = re.sub(r'\n?```\s*$', '', raw_text)

    try:
        result = json.loads(raw_text)
        save_ai_log(prompt, f"[PDF sent directly: {os.path.basename(pdf_path)}]", result)
        return result
    except json.JSONDecodeError as e:
        save_ai_log(prompt, f"[PDF sent directly: {os.path.basename(pdf_path)}]", {"ERROR": "Invalid JSON", "RAW": raw_text})
        raise Exception(f"L'IA a retourné un JSON invalide. Erreur : {str(e)}\nRéponse brute :\n{raw_text}")


def generate_patient_pdf(patient, list_info, source_pdf_path=None, cijoint_pages=None, custom_filename=None):
    """Generate a PDF for a single patient using generate_pdf.py."""

    from generate_pdf import generate_pdf
    from io import BytesIO

    # Fetch configuration for dynamic lab info
    config = load_config()
    lab_config = {
        "lab_dr_name": config.get("lab_dr_name"),
        "lab_addr_l1": config.get("lab_addr_l1"),
        "lab_addr_l2": config.get("lab_addr_l2"),
        "lab_tel": config.get("lab_tel"),
        "lab_fax": config.get("lab_fax"),
        "lab_mobile": config.get("lab_mobile"),
        "email": config.get("email", "info.tarzaali@gmail.com"),
        "lab_name": config.get("lab_name", "LABORATOIRE D'ANALYSES DE BIOLOGIE MEDICALE"),
        "prof_name": config.get("prof_name", "Professeur Abdelaziz TARZAALI")
    }

    last_name = patient.get("lastName", "unknown")
    first_name = patient.get("firstName", "unknown")
    sample_date = patient.get("sampleDate", "")
    date_suffix = re.sub(r'[^0-9]', '', sample_date)

    # Step 1: Generate the report PDF
    report_bytes = generate_pdf(patient, list_info, logo_path=LOGO_PATH, lab_config=lab_config)

    # Step 2: Merge ci-joint pages if needed
    if cijoint_pages and source_pdf_path and os.path.exists(source_pdf_path):
        try:
            writer = PdfWriter()
            report_bytes.seek(0)
            reader_report = PdfReader(report_bytes)
            for page in reader_report.pages:
                writer.add_page(page)

            reader_source = PdfReader(source_pdf_path)
            total_source_pages = len(reader_source.pages)

            for page_num in cijoint_pages:
                idx = page_num - 1
                if 0 <= idx < total_source_pages:
                    writer.add_page(reader_source.pages[idx])
            
            merged = BytesIO()
            writer.write(merged)
            merged.seek(0)
            final_bytes = merged
        except Exception as e:
            print(f"[PDF] ERROR merging ci-joint pages: {e}")
            report_bytes.seek(0)
            final_bytes = report_bytes
    else:
        report_bytes.seek(0)
        final_bytes = report_bytes

    # Step 3: Save final PDF
    if custom_filename:
        filename = custom_filename
    else:
        filename = f"{last_name}_{first_name}_{date_suffix}.pdf" if date_suffix else f"{last_name}_{first_name}.pdf"
    
    filepath = os.path.join(GENERATED_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(final_bytes.read())

    return filename


def get_patient_status_summary(patient):
    """Get a summary status for a patient based on their tests."""
    statuses = set()
    for test in patient.get("tests", []):
        for sub in test.get("subTests", []):
            statuses.add(sub.get("status", "completed"))

    if "pending" in statuses:
        return "pending"
    return "completed"


def get_patient_status_details(patient):
    """Get detailed status for each test of a patient."""
    details = []
    for test in patient.get("tests", []):
        for sub in test.get("subTests", []):
            details.append({
                "name": sub.get("subtestName", ""),
                "status": sub.get("status", "completed"),
                "result": sub.get("result", ""),
                "isAbnormal": sub.get("isAbnormal", False)
            })
    return details


def get_cijoint_pages(patient):
    """Collect all unique non-null ciJointPage values from a patient's subtests.
    Returns a sorted list of 1-based page numbers."""
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


# ─── Session Storage ────────────────────────────────────────────────────────

def save_session_data(session_id, data):
    path = os.path.join(UPLOAD_DIR, f"{session_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_session_data(session_id):
    path = os.path.join(UPLOAD_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ─── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("dashboard"))


@app.route("/upload-page")
def upload_page():
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def upload():
    """Upload PDF → AI extracts data → show patient list."""
    if "pdf_file" not in request.files:
        return jsonify({"error": "Aucun fichier téléchargé"}), 400

    file = request.files["pdf_file"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Seuls les fichiers PDF sont autorisés"}), 400

    session_id = str(uuid.uuid4())[:8]
    pdf_filename = f"{session_id}_{file.filename}"
    pdf_path = os.path.join(UPLOAD_DIR, pdf_filename)
    file.save(pdf_path)

    try:
        # Get selected model from config
        config = load_config()
        model = config.get("model", "gemini-2.5-flash")

        # Call AI for extraction
        prompt = load_prompt()
        extraction_result = call_ai_for_extraction(pdf_path, prompt, model_name=model)

        patients_data = extraction_result.get("patients", [])

        # Build patient list with status (NO PDF generation here)
        patient_list = []
        for p_idx, patient in enumerate(patients_data):
            status = get_patient_status_summary(patient)
            details = get_patient_status_details(patient)
            pages = get_cijoint_pages(patient)
            patient_list.append({
                "index": p_idx,
                "lastName": patient.get("lastName", ""),
                "firstName": patient.get("firstName", ""),
                "dateOfBirth": patient.get("dateOfBirth", ""),
                "status": status,
                "testCount": len(patient.get("tests", [])),
                "testDetails": details,
                "pages": pages
            })

        # Save session data
        session_data = {
            "session_id": session_id,
            "listNumber": extraction_result.get("listNumber"),
            "listeDate": extraction_result.get("listeDate"),
            "printDate": extraction_result.get("printDate"),
            "patients": patients_data,
            "patient_list": patient_list,
            "total_pages": 0,
            "processed_at": datetime.now().isoformat(),
            "source_pdf_path": pdf_path
        }
        save_session_data(session_id, session_data)

        # Step 5: Persist to SQLite
        liste_id = None
        try:
            liste_id = database.save_extraction_result(extraction_result, original_filename=pdf_filename)
        except Exception as db_err:
            print(f"[DB] Error saving to database: {db_err}")

        # Redirect to Dashboard filtered by the new list ID
        if liste_id:
            return redirect(url_for("dashboard", liste_id=liste_id))
        else:
            return redirect(url_for("dashboard"))

    except json.JSONDecodeError as e:
        return render_template("upload.html", error=f"L'IA a retourné un JSON invalide : {str(e)}")
    except Exception as e:
        error_msg = str(e)
        # Check for Gemini Quota/Resource Exhaustion
        if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg or "quota" in error_msg.lower():
            friendly_error = "Limite de quota (version gratuite) atteinte. Veuillez patienter environ 30 secondes à 1 minute avant de réessayer."
            return render_template("upload.html", error=friendly_error)
        elif "503" in error_msg or "UNAVAILABLE" in error_msg:
            friendly_error = "Le service IA est temporairement surchargé. Veuillez réessayer dans quelques instants."
            return render_template("upload.html", error=friendly_error, is_503=True)
        elif "getaddrinfo" in error_msg or "Errno 11001" in error_msg:
            friendly_error = "Erreur de connexion : Impossible d'atteindre le service IA. Veuillez vérifier votre connexion internet."
            return render_template("upload.html", error=friendly_error)
        else:
            friendly_error = f"Erreur de traitement : {error_msg}"
            return render_template("upload.html", error=friendly_error)


@app.route("/view-session-source/<session_id>")
def view_session_source(session_id):
    """View the original PDF from a session."""
    data = load_session_data(session_id)
    if not data:
        return "Session introuvable", 404
        
    source_filename = os.path.basename(data.get("source_pdf_path", ""))
    list_number = data.get("listNumber", "Liste")
    
    return render_template("viewer.html",
                           session_id=session_id,
                           patient_index=0,
                           patient_name=list_number,
                           pdf_filename=source_filename,
                           is_source=True)


@app.route("/view/<session_id>/<int:patient_index>")
def view_patient(session_id, patient_index):
    """Generate PDF for a single patient on-demand and show it."""
    data = load_session_data(session_id)
    if not data:
        return redirect(url_for("upload_page"))

    patients = data.get("patients", [])
    if patient_index < 0 or patient_index >= len(patients):
        return redirect(url_for("patients", session_id=session_id))

    patient = patients[patient_index]

    # Generate PDF for THIS patient only (on-demand)
    list_info = {
        "listNumber": data.get("listNumber", ""),
        "listeDate": data.get("listeDate", ""),
        "printDate": data.get("printDate", "")
    }
    source_pdf = data.get("source_pdf_path")
    cijoint_pages = get_cijoint_pages(patient)
    pdf_filename = generate_patient_pdf(patient, list_info, source_pdf, cijoint_pages)

    patient_name = f"{patient.get('lastName', '')} {patient.get('firstName', '')}"

    return render_template("viewer.html",
                           session_id=session_id,
                           patient_index=patient_index,
                           patient_name=patient_name,
                           pdf_filename=pdf_filename)


@app.route("/download/<session_id>/<int:patient_index>")
def download_patient(session_id, patient_index):
    """Download the generated patient PDF."""
    data = load_session_data(session_id)
    if not data:
        return redirect(url_for("upload_page"))

    patients = data.get("patients", [])
    if patient_index < 0 or patient_index >= len(patients):
        return redirect(url_for("patients", session_id=session_id))

    patient = patients[patient_index]

    # Check if PDF already generated, if not generate it
    last_name = patient.get("lastName", "unknown")
    first_name = patient.get("firstName", "unknown")
    sample_date = patient.get("sampleDate", "")
    date_suffix = re.sub(r'[^0-9]', '', sample_date)
    
    pdf_filename = f"{last_name}_{first_name}_{date_suffix}.pdf" if date_suffix else f"{last_name}_{first_name}.pdf"
    pdf_path = os.path.join(GENERATED_DIR, pdf_filename)

    if not os.path.exists(pdf_path):
        list_info = {
            "listNumber": data.get("listNumber", ""),
            "listeDate": data.get("listeDate", ""),
            "printDate": data.get("printDate", "")
        }
        source_pdf = data.get("source_pdf_path")
        cijoint_pages = get_cijoint_pages(patient)
        pdf_filename = generate_patient_pdf(patient, list_info, source_pdf, cijoint_pages)

    download_name = f"{last_name}_{first_name}_results.pdf"

    return send_file(pdf_path,
                     as_attachment=True,
                     download_name=download_name,
                     mimetype="application/pdf")


@app.route("/pdf/<filename>")
def serve_pdf(filename):
    """Serve a generated PDF file for in-browser rendering."""
    pdf_path = os.path.join(GENERATED_DIR, filename)
    if not os.path.exists(pdf_path):
        return jsonify({"error": "PDF not found"}), 404
    return send_file(pdf_path, mimetype="application/pdf")


@app.route("/source-pdf/<filename>")
def serve_source_pdf(filename):
    """Serve an original uploaded PDF file."""
    pdf_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(pdf_path):
        return jsonify({"error": "Original PDF not found"}), 404
    return send_file(pdf_path, mimetype="application/pdf")


@app.route("/view-source/<int:liste_id>")
def view_source_pdf(liste_id):
    """Show the original uploaded PDF in the viewer."""
    conn = database.get_db_connection()
    row = conn.execute("SELECT * FROM listes WHERE id = ?", (liste_id,)).fetchone()
    conn.close()

    if not row or not row['original_filename']:
        return "Fichier original introuvable ou non enregistré pour cette liste.", 404

    return render_template("viewer.html",
                           session_id="source",
                           patient_index=liste_id,
                           patient_name=row['list_number'],
                           pdf_filename=row['original_filename'],
                           is_source=True)


@app.route("/api/patients/<session_id>")
def api_patients(session_id):
    data = load_session_data(session_id)
    if not data:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(data.get("patient_list", []))


@app.route("/api/status/<session_id>/<int:patient_index>")
def api_patient_status(session_id, patient_index):
    data = load_session_data(session_id)
    if not data:
        return jsonify({"error": "Session not found"}), 404

    patients = data.get("patients", [])
    if patient_index < 0 or patient_index >= len(patients):
        return jsonify({"error": "Patient not found"}), 404

    patient = patients[patient_index]
    return jsonify({
        "patient": patient,
        "status": get_patient_status_summary(patient),
        "testDetails": get_patient_status_details(patient)
    })


@app.route("/logo.jpg")
def serve_logo():
    """Serve the laboratory logo."""
    return send_file(LOGO_PATH, mimetype="image/jpeg")


# ─── DB Dashboard Routes ───────────────────────────────────────────────────

@app.route("/dashboard")
def dashboard():
    """Main dashboard showing listes and patients with pagination."""
    liste_id = request.args.get("liste_id", type=int)
    search_query = request.args.get("q", "")
    status_filter = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    per_page = 25

    listes = database.get_all_listes()

    # Get dashboard stats
    stats = database.get_dashboard_stats(liste_id=liste_id)

    # Get total count for pagination
    total_count = database.count_patients(liste_id=liste_id, search_query=search_query, status_filter=status_filter)

    # Calculate offset
    offset = (page - 1) * per_page

    # Get paginated patients
    patients = database.get_patients(
        liste_id=liste_id, 
        search_query=search_query, 
        status_filter=status_filter,
        limit=per_page,
        offset=offset
    )

    total_pages = (total_count + per_page - 1) // per_page
    selected_liste = next((l for l in listes if l['id'] == liste_id), None) if liste_id else None

    return render_template("dashboard.html",
                           listes=listes,
                           patients=patients,
                           selected_liste_id=liste_id,
                           selected_liste=selected_liste,
                           search_query=search_query,
                           status_filter=status_filter,
                           page=page,
                           total_pages=total_pages,
                           total_count=total_count,
                           stats=stats)

@app.route("/mark-printed/<int:patient_id>", methods=["POST"])
def mark_printed(patient_id):
    """Mark a patient as delivered in the database."""
    database.mark_patient_printed(patient_id)
    return jsonify({"success": True})

@app.route("/unmark-printed/<int:patient_id>", methods=["POST"])
def unmark_printed(patient_id):
    """Unmark a patient as delivered in the database."""
    database.unmark_patient_printed(patient_id)
    return jsonify({"success": True})

@app.route("/update-notes/<int:patient_id>", methods=["POST"])
def update_notes(patient_id):
    """Update a patient's notes in the database."""
    data = request.json
    notes = data.get("notes", "")
    database.update_patient_notes(patient_id, notes)
    return jsonify({"success": True})

@app.route("/generate-partial/<int:patient_id>", methods=["POST"])
def generate_partial_pdf_route(patient_id):
    """Generate a PDF for a patient with only selected tests."""
    data = request.json
    selected_indices = data.get("test_indices", [])
    
    if not selected_indices:
        return jsonify({"error": "Aucun test sélectionné"}), 400

    # Get patient from DB
    conn = database.get_db_connection()
    row = conn.execute("SELECT p.*, l.list_number, l.liste_date, l.print_date, l.original_filename FROM patients p JOIN listes l ON p.liste_id = l.id WHERE p.id = ?", (patient_id,)).fetchone()
    conn.close()
    
    if not row:
        return jsonify({"error": "Patient introuvable"}), 404
    
    patient = json.loads(row['patient_json'])
    
    # Filter tests
    all_tests = patient.get("tests", [])
    filtered_tests = [all_tests[i] for i in selected_indices if 0 <= i < len(all_tests)]
    
    if not filtered_tests:
        return jsonify({"error": "Sélection de tests invalide"}), 400
        
    # Create a temporary patient object with filtered tests
    partial_patient = patient.copy()
    partial_patient["tests"] = filtered_tests
    
    list_info = {
        "listNumber": row['list_number'],
        "listeDate": row['liste_date'],
        "printDate": row['print_date']
    }
    
    # Use the stored original filename to enable ci-joint merging
    original_filename = row['original_filename'] if row['original_filename'] else None
    source_pdf_path = os.path.join(UPLOAD_DIR, original_filename) if original_filename else None
    
    if source_pdf_path and os.path.exists(source_pdf_path):
        cijoint_pages = get_cijoint_pages(partial_patient)
    else:
        source_pdf_path = None
        cijoint_pages = []

    # Generate PDF with a unique filename for partial
    last_name = row['last_name']
    first_name = row['first_name']
    sample_date = patient.get("sampleDate", "")
    date_suffix = re.sub(r'[^0-9]', '', sample_date)
    
    # Add PARTIAL and a short UUID to the filename to avoid collisions
    unique_id = str(uuid.uuid4())[:4]
    filename = f"{last_name}_{first_name}_{date_suffix}_PARTIAL_{unique_id}.pdf" if date_suffix else f"{last_name}_{first_name}_PARTIAL_{unique_id}.pdf"
    
    # We need to modify generate_patient_pdf to accept an optional filename or just call generate_pdf directly here
    # Actually, let's update generate_patient_pdf to accept an optional filename.
    
    pdf_filename = generate_patient_pdf(partial_patient, list_info, source_pdf_path, cijoint_pages, custom_filename=filename)
    
    return jsonify({
        "success": True,
        "pdf_url": url_for('view_partial_pdf', filename=pdf_filename, patient_name=f"{last_name} {first_name}")
    })


@app.route("/view-partial/<filename>")
def view_partial_pdf(filename):
    """View a partially generated PDF."""
    patient_name = request.args.get("patient_name", "Patient")
    return render_template("viewer.html",
                           session_id="partial",
                           patient_index=0,
                           patient_name=patient_name,
                           pdf_filename=filename)


@app.route("/download-partial/<filename>")
def download_partial_pdf(filename):
    """Download a partially generated PDF."""
    pdf_path = os.path.join(GENERATED_DIR, filename)
    if not os.path.exists(pdf_path):
        return jsonify({"error": "PDF introuvable"}), 404
        
    return send_file(pdf_path,
                     as_attachment=True,
                     download_name=f"selection_analyses.pdf",
                     mimetype="application/pdf")


@app.route("/delete-patient/<int:patient_id>", methods=["POST"])
def delete_patient_route(patient_id):
    """Delete a patient record from DB."""
    database.delete_patient(patient_id)
    return redirect(url_for("dashboard", **request.args))


@app.route("/delete-liste/<int:liste_id>", methods=["POST"])
def delete_liste_route(liste_id):
    """Delete an entire list ONLY if it has no patients."""
    conn = database.get_db_connection()
    # Double check that no patients exist
    count = conn.execute("SELECT COUNT(*) FROM patients WHERE liste_id = ?", (liste_id,)).fetchone()[0]
    
    if count == 0:
        conn.execute("DELETE FROM listes WHERE id = ?", (liste_id,))
        conn.commit()
    
    conn.close()
    return redirect(url_for("dashboard"))


@app.route("/view-db/<int:patient_id>")
def view_patient_db(patient_id):
    """Generate PDF for a patient from DB and show it."""
    # Get patient from DB
    conn = database.get_db_connection()
    row = conn.execute("SELECT p.*, l.list_number, l.liste_date, l.print_date, l.original_filename FROM patients p JOIN listes l ON p.liste_id = l.id WHERE p.id = ?", (patient_id,)).fetchone()
    conn.close()
    
    if not row:
        return redirect(url_for("dashboard"))
    
    patient = json.loads(row['patient_json'])
    list_info = {
        "listNumber": row['list_number'],
        "listeDate": row['liste_date'],
        "printDate": row['print_date']
    }
    
    # Use the stored original filename to enable ci-joint merging for DB records
    original_filename = row['original_filename'] if row['original_filename'] else None
    source_pdf_path = os.path.join(UPLOAD_DIR, original_filename) if original_filename else None
    
    # Only try to get cijoint pages if the source file actually exists
    if source_pdf_path and os.path.exists(source_pdf_path):
        cijoint_pages = get_cijoint_pages(patient)
    else:
        source_pdf_path = None
        cijoint_pages = []

    pdf_filename = generate_patient_pdf(patient, list_info, source_pdf_path, cijoint_pages)
    
    patient_name = f"{row['last_name']} {row['first_name']}"
    
    return render_template("viewer.html",
                           session_id="db",
                           patient_index=patient_id,
                           patient_name=patient_name,
                           pdf_filename=pdf_filename)


@app.route("/download-db/<int:patient_id>")
def download_patient_db(patient_id):
    """Download the generated patient PDF from DB record."""
    conn = database.get_db_connection()
    row = conn.execute("SELECT p.*, l.list_number, l.liste_date, l.print_date, l.original_filename FROM patients p JOIN listes l ON p.liste_id = l.id WHERE p.id = ?", (patient_id,)).fetchone()
    conn.close()
    
    if not row:
        return redirect(url_for("dashboard"))
        
    last_name = row['last_name']
    first_name = row['first_name']
    patient = json.loads(row['patient_json'])
    sample_date = patient.get("sampleDate", "")
    date_suffix = re.sub(r'[^0-9]', '', sample_date)
    
    pdf_filename = f"{last_name}_{first_name}_{date_suffix}.pdf" if date_suffix else f"{last_name}_{first_name}.pdf"
    pdf_path = os.path.join(GENERATED_DIR, pdf_filename)

    if not os.path.exists(pdf_path):
        list_info = {
            "listNumber": row['list_number'],
            "listeDate": row['liste_date'],
            "printDate": row['print_date']
        }
        
        # Reconstruct path and pages for merging
        original_filename = row['original_filename'] if row['original_filename'] else None
        source_pdf_path = os.path.join(UPLOAD_DIR, original_filename) if original_filename else None
        
        if source_pdf_path and os.path.exists(source_pdf_path):
            cijoint_pages = get_cijoint_pages(patient)
        else:
            source_pdf_path = None
            cijoint_pages = []

        generate_patient_pdf(patient, list_info, source_pdf_path, cijoint_pages)

    return send_file(pdf_path,
                     as_attachment=True,
                     download_name=f"{last_name}_{first_name}_results.pdf",
                     mimetype="application/pdf")


@app.route("/api/online-results/<int:liste_id>")
def online_results(liste_id):
    """Fetch real-time lab results from external API for a specific list date."""
    # 1. Get liste_date from DB
    conn = database.get_db_connection()
    row = conn.execute("SELECT liste_date FROM listes WHERE id = ?", (liste_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Liste introuvable"}), 404

    # 2. Convert DD/MM/YYYY → YYYYMMDD
    date_str = row['liste_date']  # e.g. "14/05/2026"
    try:
        date_param = date_str[6:10] + date_str[3:5] + date_str[0:2]  # → "20260514"
    except Exception:
        return jsonify({"error": "Format de date invalide"}), 400

    # 3. Load credentials from config
    config = load_config()
    username = config.get("online_username", "")
    password = config.get("online_password", "")
    api_key = "e1cbcb83-a73d-4623-ac16-363d7724040b"

    if not username or not password:
        return jsonify({"error": "Identifiants Tarzaali Online non configurés"}), 400

    # 4. Call the external API
    import requests
    url = (
        f"http://biogroupe.ddns.net:8020/api/appLabo/RealTime/Labo"
        f"?patient=&urgence=ALL&etat=&codeAnalyseUnique=&codeParametreUnique="
        f"&codeEchantillon=&dateStart={date_param}&dateEnd={date_param}"
        f"&username={username}&password={password}&apiKey={api_key}"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/config", methods=["GET", "POST"])
def config_endpoint():
    if request.method == "POST":
        data = request.json
        # Extract lab fields and update config
        config = load_config()
        fields = ["api_key", "model", "online_username", "online_password", 
                  "lab_dr_name", "lab_addr_l1", "lab_addr_l2", "lab_tel", "lab_fax", "lab_mobile"]
        for f in fields:
            if f in data:
                config[f] = data[f]
        
        save_config(config)
        return jsonify({"success": True})
    return jsonify(load_config())


@app.route("/api/models")
def get_available_models():
    """Fetch available models from Gemini API and filter for preferred versions."""
    api_key = get_api_key()
    if not api_key:
        return jsonify({"error": "API key missing"}), 400
    try:
        client = genai.Client(api_key=api_key)
        # Define keywords to include and exclude
        include_keywords = ["flash"]
        exclude_keywords = ["tts", "nano", "image", "lite", "1.5", "2.0"]
        
        models = [
            m for m in client.models.list() 
            if "generateContent" in m.supported_actions and 
            any(k in m.name.lower() for k in include_keywords) and 
            not any(k in m.name.lower() for k in exclude_keywords)
        ]
        
        return jsonify([{"name": m.name, "display_name": m.display_name} for m in models])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    print(f"Démarrage du processeur de PDF Labo sur http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)