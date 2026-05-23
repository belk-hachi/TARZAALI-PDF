# Changelog - TARZALI-PDF

All notable changes to this project will be documented in this file.

## [2026-05-23] - Patient Edit Functionality

### Added
- **Patient Edit Icon**: Added an "Edit" (pencil) icon to the patient list in the dashboard for updating patient information.
- **Patient Edit Modal**: Integrated a modal to update First Name, Last Name, and Date of Birth with automatic uppercase conversion for the last name.
- **Backend Update Route**: Implemented `/update-patient` route with automatic conflict resolution to preserve patient metadata (status, notes) during name/DOB updates.
- **Dynamic PDF Generation**: Updated PDF generation logic to retrieve the most recent patient information from the database upon every view or download.

---

## [2026-05-23] - UI Refactoring & Maintenance Enhancements

### Fixed
- **Dashboard BuildError**: Resolved a critical `werkzeug.routing.exceptions.BuildError` by updating all `url_for` calls in templates to use correct blueprint-prefixed endpoints (e.g., `dashboard.dashboard`).
- **Enforced Uppercase Names**: Updated both the database layer (`save_extraction_result`, `update_patient_identity`) and the route layer to ensure both First Name and Last Name are consistently saved in uppercase.
- **Path Standardization**: Refactored hardcoded paths in `upload.html` and `viewer.html` to use Flask's `url_for` for better reliability and blueprint compatibility.

### Changed
- **Relocated Backup Functionality**: Moved the manual backup button from the dashboard header to a new "Maintenance" tab within the Settings modal to declutter the main UI.
- **Adjusted Backup Frequency**: Changed the automatic background backup interval from 30 minutes to **once every 24 hours** to reduce system overhead.
- **Enhanced Theme Toggle**: Increased the size of the light/dark mode icon and container for better visibility and easier interaction.

---

## [2026-05-22] - Dynamic Laboratory Configuration

### Added
- **Dynamic Lab Information**: Introduced new configuration fields for laboratory details (Dr. Name, Address, Phone, Fax, Mobile) in the settings interface.
- **Configurable PDF Header**: The PDF generator now dynamically pulls contact/address information from `config.json` instead of using hardcoded defaults.
- **Enhanced Settings UI**: Added dedicated inputs in the settings modal to manage lab profile information.

## [2026-05-22] - High-Quality Slate Dark Mode & High-Density UI

### Added
- **Slate Semantic Dark Mode**: Implemented a professional dark theme using a Slate/Blue-Grey palette (`#0F172A`, `#1E293B`) with hierarchical layering for depth and accessibility.
- **High-Contrast Typography**: Optimized text colors for dark mode using Slate-50 (`#F8FAFC`) for primary data and Slate-400 (`#94A3B8`) for secondary information.
- **Offline UI Reliability**: Fully localized all application assets. Removed Google Fonts CDN dependency in favor of high-quality system-native fonts for 100% offline rendering.
- **Auto-Refresh Filters**: Integrated automatic page reload when marking patients as "Traité" within a filtered view, ensuring the displayed list stays accurate.

### Changed
- **High-Density Layout**:
    - Reduced main heading font size to 1.15rem for better proportional fit.
    - Compacted pagination controls with custom small styling and removed the bulky `pagination-lg`.
    - Applied a global 90% zoom factor to provide the user's preferred "high-density" workspace by default.
- **Eliminated Harsh Contrast**: Replaced all pure white content containers and data rows with elevated slate backgrounds.
- **Accessibility Refinement**: Standardized status badges with deep-tinted backgrounds and vibrant emerald/amber/red text variants.
- **Unified Action Buttons**: Refined action icons (View, Download, Delete) with soft transparent hover states.
- **Table Header Overhaul**: Updated table headers to use clean dark backgrounds with muted light text.

## [2026-05-22] - Google Material 3 UI Revamp & Interactive Filters

### Added
- **Interactive Stats Cards**: The statistics dashboard cards are now clickable links that instantly filter the patient list.
- **"Traité" (Printed) Filter**: Added full backend and frontend support for filtering the patient list by processed status.
- **"Read Email" Row Styling**: Processed patient rows now adopt a "read" state with normal font weight and a subtle background tint, mimicking a modern inbox.

### Changed
- **Google Roboto Typography**: Switched the primary application font to Roboto for a cleaner, more professional Google-style aesthetic.
- **Compact Layout Overhaul**: 
    - Redesigned statistics cards into a horizontal, space-efficient layout.
    - Reduced action icon and button sizes for a more professional "high-density" UI.
    - Tightened sidebar and topbar spacing to maximize content area.
- **Merged Filters & Stats**: Replaced the separate status tabs with the interactive stats bar for a more intuitive and unified navigation experience.
- **Refined Badges**: Shrunk icons inside status badges to match the new compact design.

## [2026-05-21] - Dark Mode, "Non Traité" Filter & UI Polish

### Added
- **Dark Mode Support**: Implemented a comprehensive Dark Mode across the entire application (`dashboard.html`, `upload.html`, `viewer.html`).
- **Manual Theme Toggle**: Added a Sun/Moon toggle button in the topbar to switch between Light and Dark themes.
- **Persistent Theme Preference**: User's theme choice is saved in `localStorage` and applied instantly on page load.
- **"Non Traité" Filter**: Added a dedicated filter and status tab for dossiers that are "Terminé" but haven't been marked as processed (Traité).
- **Expanded Stats Dashboard**: Added a fifth indicator card for "Non Traité" with a red warning theme for better visibility of pending dossiers.
- **Themed UI Components**: Custom dark styling for all modals, inputs, tables, and badges to ensure a high-contrast and professional look.

### Changed
- **Improved Search Visibility**: Redesigned the search bar with a distinct background and border to ensure it's clearly visible in Dark Mode.
- **Enhanced "Traité" Highlighting**: Refined the styling for processed patient rows with a light gray background in Light Mode and a dark surface-plus background in Dark Mode.
- **Dark Mode Text Optimization**: Applied white text and high-contrast indicators for processed patients in Dark Mode to ensure maximum legibility.
- **UI Spacing**: Adjusted the stats bar to fit 5 indicators while maintaining a clean and responsive layout.
- **Documentation Update**: Updated `README.md` to reflect the new UI-based configuration system.

### Fixed
- **Placeholder Visibility**: Fixed dark-on-dark placeholder text in the search bar for Dark Mode.
- **Indicator Contrast**: Resolved visibility issues for patient test counts and pagination controls in Dark Mode.

## [2026-05-17] - Visit-Isolated Patient Metadata & Schema Refactoring

### Added
- **Visit-Isolated Patient Metadata**: Decoupled patient notes and delivery status from the main extraction pipeline to ensure data persistence across re-uploads.
- **Per-Visit Data Isolation**: Metadata is now keyed by a 4-field identity (`last_name`, `first_name`, `date_of_birth`, `liste_date`), preventing notes or status from bleeding between different visits of the same patient.
- **Robust Schema Migration**: Implemented a sophisticated migration system in `init_db()` that handles fresh installs, legacy 3-field keys, and automated data recovery.
- **Safe Schema Cleanup**: Successfully removed redundant `notes` and `printed_at` columns from the `patients` table using the SQLite rename/recreate/copy/drop pattern, ensuring a clean and normalized database structure.

### Changed
- **Metadata Persistence**: Notes and "remis" status now survive even if a list is deleted and re-uploaded, as they are stored in a dedicated table decoupled from the extraction results.
- **Database Engine Refactoring**: Updated all upsert and retrieval functions (`update_patient_notes`, `mark_patient_printed`, `get_dashboard_stats`, `get_patients`) to use the new visit-isolated identity key.
- **Stats Accuracy**: Enhanced `get_dashboard_stats` to derive delivery counts directly from the decoupled metadata table via strict identity matching.

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
