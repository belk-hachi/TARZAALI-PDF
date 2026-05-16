# TARZALI-PDF

TARZALI-PDF is a modern web application designed to automate the extraction of patient data from medical laboratory reports using the Google Gemini AI, and generate professional, customized PDF results.

## 🚀 Key Features
* **AI-Powered Extraction**: Uses Google Gemini 2.5 Flash to intelligently parse complex lab reports (including scans).
* **Interactive Upload**: Modern modal-based upload with real-time progress tracking and automated multi-step processing.
* **Smart Reporting**: Generates clean, professional PDF reports with:
    * Automatic merging of original diagnostic images ("ci-joint" pages).
    * Dynamic result formatting (clean numeric display).
    * Clear highlighting for abnormal results (asterisks and red bold text).
* **Advanced Dashboard**: Full-width management system with:
    * Simultaneous search by **Last Name**, **First Name**, or **Test Name**.
    * Expandable test details directly in the patient table.
    * Persistent access to the original source PDF for every extraction.
* **Portable & Secure**: Built with Flask and SQLite; can be compiled into a standalone Windows executable.

## 🛠️ Prerequisites
* Python 3.13+
* pip

## 🏁 Getting Started

1. **Clone the repository.**
2. **Setup virtual environment:**
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```
3. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```
4. **Run the application:**
   ```powershell
   python app.py
   ```

## ⚙️ Configuration
* **API Key:** 
    1. Obtain a free API key from [Google AI Studio](https://aistudio.google.com/).
    2. On the first run, the app will generate `gemini_key.txt`. 
    3. Paste your key into this file and restart the application.
* **Prompt Engineering:** Customize `prompt.md` to fine-tune how the AI extracts data from your specific report formats.

## 📦 Bundling as Executable
To create a standalone `.exe` for Windows using PyInstaller:

```powershell
pyinstaller --noconfirm --onefile --windowed `
    --add-data "logo.jpg;." `
    --add-data "templates;templates" `
    --add-data "static;static" `
    --name "TARZALI-PDF" `
    app.py
```

The compiled application will be available in the `dist/` folder.
