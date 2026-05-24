# TARZALI-PDF

TARZALI-PDF is a modern, high-density web application designed to automate medical laboratory workflow management. It covers the entire lifecycle from automatic email retrieval and AI-powered data extraction to professional PDF generation and long-term data archiving.

## 🚀 Key Features
* **Background Email Automation**: Automatically polls (IMAP) for laboratory reports, processes attachments, and merges PDF results.
* **AI-Powered Extraction**: Uses Google Gemini 2.5 Flash to intelligently parse reports and extract patient data.
* **Smart Reporting**: Generates professional, customized PDF reports with dynamic branding and automatic handling of annexed images.
* **High-Density Dashboard**: A modern, Slate-themed interface with real-time stats, comprehensive filters, and inline patient editing.
* **Maintenance & Reliability**:
    * **Compressed Backups**: Automated, configurable ZIP backups of database and uploads.
    * **Activity Logging**: Dedicated log viewer for tracking background processes.
    * **Offline Ready**: Fully localized UI assets—no internet required for interface rendering.
* **Portable & Secure**: Built with Flask and SQLite; supports standalone Windows deployment.

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
* **System Settings**: Access the **⚙️ Paramètres** modal in the dashboard to configure:
    * **API Key**: Gemini API key from [Google AI Studio](https://aistudio.google.com/).
    * **Email Integration**: IMAP server, credentials, and filtering rules for automated result retrieval.
    * **Backup**: Custom storage paths and connectivity testing.
    * **Laboratory Info**: Dynamic header information for generated reports.
* **Prompt Engineering**: Customize `prompt.md` to fine-tune extraction behavior.

## 📦 Bundling as Executable
To create a standalone `.exe` for Windows using PyInstaller:

```powershell
pyinstaller --noconfirm --onefile --windowed `
    --add-data "logo.jpg;." `
    --add-data "templates;templates" `
    --add-data "static;static" `
    --name "TARZALI-PDF" `
    app.py

