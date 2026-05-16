# Changelog - TARZALI-PDF

All notable changes to this project will be documented in this file.

## [2026-05-16] - Patient Management & Dashboard Enhancements

### Added
- **Rejeté Visual Indicator**: Added a red "Rejeté" badge next to patient names if any of their analyses were rejected.
- **Unmark as Delivered**: Added the ability to toggle delivery status back to "undelivered" with a confirmation prompt.
- **Patient Notes**: Added a free-text notes field per patient. Notes are saved to the database and can be edited inline from the dashboard.
- **Notes Indicator**: A 📝 badge appears next to patients with notes, with a tooltip previewing the content.
- **Dashboard Stats Widget**: Added a row of 4 cards showing Total, Pending, Completed, and Delivered patient counts.
- **Mark as Delivered**: Added a "Mark as remis" button for each patient to track delivery status.
- **Delivery Tracking**: New `printed_at` timestamp column in the database to record exactly when results were handed over.
- **Visual Status Indicators**: Row styling for delivered patients (opacity reduction and green border) to improve workflow visibility.
- **Real-time UI Updates**: Integrated AJAX-based status updates that increment the "Remis" counter and update the UI without page reloads.

### Changed
- **UI Optimizations**: Narrowed sidebar and reduced content padding to maximize space for patient details.
- **Icon-only Badges**: Converted "CI-JOINT" and "Rejeté" badges to icon-only indicators with tooltips to reduce visual clutter.
- **Avatar Removal**: Removed patient initials and avatar boxes for a cleaner, more streamlined layout.
- **Dashboard Refactoring**: Improved DOM structure with `data-patient-id` and `patient-name-text` classes for more reliable element targeting in JavaScript.
- **Reliability Improvements**: Enhanced `saveNote()` and `fetchOnlineResults()` functions to use direct attribute selection, eliminating fragile relative DOM traversal.

## [2026-05-16] - Git Initialization & Viewer Fix

### Fixed
- **Template Error in Viewer**: Removed a redundant `page_numbers` span in `viewer.html` that caused errors because the variable was not provided by the routes.

### Changed
- **Git Repository Setup**: Initialized the project as a git repository.
- **Security**: Configured `.gitignore` to protect sensitive data (`config.json`, `Labo.json`, and `.gemini/` folder).
- **Configuration Template**: Added `config.json.example` as a safe template for environment setup.

## [2026-05-16] - Feature Enhancements & UI Indicators

### Added
- **Print Selected Feature**: Added ability to selectively print specific subtests within a patient record. Checkboxes allow users to choose which results to include in the generated PDF report.
- **Ci-Joint Visual Indicator**: Implemented a "📎 CI-JOINT" badge on the dashboard. It automatically appears next to patient names if their record contains attachments (annexes), making them instantly identifiable.
- **Improved Test Details**: Enhanced the collapsible test details view with a cleaner header and "Print Selection" action button.

### Changed
- **UI Refinement**: Restored the professional "TARZALI" branding in the topbar and optimized spacing in the patient list rows.

---

## [2026-05-13] - Configuration Migration, Pagination & UI Refinement

### Added
- **Offline Support**: Migrated all external dependencies (Bootstrap 5.3.3 and Bootstrap Icons 1.11.3) to local files in a new `static/` directory. The application no longer requires an internet connection to render the user interface.
- **Tarzaali Online Settings**: Added new section in parameters for username and password with automated Base64 obfuscation/de-obfuscation.

### Fixed
- **JavaScript Critical Bug**: Resolved an "Uncaught TypeError: Cannot set properties of null (setting 'onsubmit')" which occurred when scripts attempted to access DOM elements before they were fully rendered.
- **Script Consolidation**: Reorganized and cleaned up all JavaScript logic in `dashboard.html` and `upload.html` for better stability and faster loading.
- **UI Consistency**: Standardized CSS and JS paths across all templates using Flask's `url_for('static', ...)` for reliable asset delivery.
- **Dynamic Configuration System**: Migrated from `gemini_key.txt` to a centralized `config.json`.
- **Dynamic Model Selection**: The application now uses the AI model selected in settings (default: Gemini 2.5 Flash) for all extractions.
- **Dashboard Pagination**: Implemented server-side pagination (25 patients per page) to handle large datasets efficiently.
- **Enhanced Navigation**: Added large, user-friendly pagination controls using Bootstrap's `pagination-lg`.
- **Global Patient Counter**: Added a dynamic "Total Patients" indicator that reflects current filters (search, status, or list).

### Changed
- **Model Filtering**: Updated the available models list to exclude older Gemini versions (1.5 and 2.0), focusing on the latest Flash models.
- **Settings UI**: Eliminated the split-second "flicker" of raw model IDs by implementing instant client-side name mapping.
- **Startup Logic**: Optimized initialization to create `config.json` automatically on first run while maintaining a read-only fallback for existing `gemini_key.txt` users.

### Fixed
- **Startup Crash**: Resolved a `NameError` in `app.py` caused by incorrect initialization order of configuration variables.
- **Selection Persistence**: Fixed an issue where the model dropdown would reset when refreshing the available models list.

---

## [2026-05-07] - Font Consistency and Helvetica Elimination

### Added
- Registered `Arial` font family to correctly link Normal, Bold, Italic, and Bold-Italic styles in generated reports.
- Implemented `EMPTY_P` (empty Paragraph) to handle empty table cells gracefully.

### Fixed
- Eliminated `Helvetica` leakage in the generated PDF by ensuring every table cell explicitly uses the registered `Arial` font.
- Standardized font naming to use comma-style (e.g., `Arial,Bold`) for PDF property consistency.
