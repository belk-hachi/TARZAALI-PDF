/* --- Global Variables --- */
// Uses CONFIG object defined in dashboard.html

/* --- Theme Toggle Logic --- */
function updateThemeIcon(theme) {
    const icon = document.getElementById('theme-icon');
    if (icon) {
        icon.className = theme === 'dark' ? 'bi bi-moon-fill' : 'bi bi-sun';
    }
}

function toggleTheme() {
    const htmlEl = document.documentElement;
    const currentTheme = htmlEl.getAttribute('data-bs-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    htmlEl.setAttribute('data-bs-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
}

function openEditPatientModal(id, lastName, firstName, dob) {
    document.getElementById('edit-patient-id').value = id;
    document.getElementById('edit-last-name').value = lastName;
    document.getElementById('edit-first-name').value = firstName;
    document.getElementById('edit-dob').value = dob;
    new bootstrap.Modal(document.getElementById('editPatientModal')).show();
}

/* --- Notes Logic --- */
function saveNote(patientId) {
    const textarea = document.getElementById(`notes-${patientId}`);
    const feedback = document.getElementById(`notes-feedback-${patientId}`);
    const notes = textarea.value;

    fetch(`/update-notes/${patientId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: notes })
    })
    .then(res => {
        if (!res.ok) throw new Error('Network response was not ok');
        return res.json();
    })
    .then(data => {
        if (data.success) {
            feedback.textContent = '✓ Note enregistrée';
            feedback.style.color = '#198754';
            feedback.style.display = 'block';
            setTimeout(() => { feedback.style.display = 'none'; }, 2000);

            const row = document.querySelector(`tr[data-patient-id="${patientId}"]`);
            const nameCell = row.querySelector('td:first-child .d-flex.align-items-center > div');
            let badge = nameCell.querySelector('.notes-badge');
            
            if (notes.trim()) {
                if (!badge) {
                    badge = document.createElement('span');
                    badge.className = 'badge bg-warning-subtle text-warning border border-warning-subtle rounded-pill notes-badge ms-2';
                    badge.style.fontSize = '0.65rem';
                    badge.style.padding = '0.2rem 0.5rem';
                    badge.textContent = '📝';
                    nameCell.querySelector('.patient-name-text').after(badge);
                }
                badge.title = notes.trim();
            } else {
                if (badge) badge.remove();
            }
        } else {
            throw new Error('Server returned failure');
        }
    })
    .catch(err => {
        console.error("Save note error:", err);
        feedback.textContent = '✗ Erreur lors de la sauvegarde';
        feedback.style.color = '#dc3545';
        feedback.style.display = 'block';
        setTimeout(() => { feedback.style.display = 'none'; }, 3000);
    });
}

/* --- Mark as Printed Logic --- */
function markAsPrinted(patientId, btn) {
    if (!confirm("Marquer ce dossier comme traité ?")) return;
    
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    
    fetch(`/mark-printed/${patientId}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                if (CONFIG.currentStatusFilter === 'not_printed') {
                    window.location.reload();
                    return;
                }

                const row = btn.closest('tr');
                row.classList.add('printed');
                
                const badgeHtml = `
                    <button onclick="unmarkAsPrinted(${patientId}, this)" class="btn btn-sm badge-printed border-0 d-flex align-items-center gap-1 ms-1" title="Cliquer pour annuler le traitement">
                        <i class="bi bi-check-lg"></i> Traité
                    </button>
                `;
                btn.outerHTML = badgeHtml;
                
                const statEl = document.getElementById('stat-printed-value');
                if (statEl) statEl.textContent = parseInt(statEl.textContent) + 1;
                
                const statNotEl = document.getElementById('stat-not-printed-value');
                if (statNotEl) statNotEl.textContent = Math.max(0, parseInt(statNotEl.textContent) - 1);
            }
        })
        .catch(err => {
            alert("Erreur lors de la mise à jour : " + err);
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        });
}

function unmarkAsPrinted(patientId, btn) {
    if (!confirm("Voulez-vous annuler le traitement de ce dossier ?")) return;
    
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    
    fetch(`/unmark-printed/${patientId}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                if (CONFIG.currentStatusFilter === 'printed') {
                    window.location.reload();
                    return;
                }

                const row = btn.closest('tr');
                row.classList.remove('printed');
                
                const btnHtml = `
                    <button onclick="markAsPrinted(${patientId}, this)" class="btn btn-sm btn-outline-secondary ms-1" title="Marquer comme traité">
                        <i class="bi bi-patch-check"></i>
                    </button>
                `;
                btn.outerHTML = btnHtml;
                
                const statEl = document.getElementById('stat-printed-value');
                if (statEl) statEl.textContent = Math.max(0, parseInt(statEl.textContent) - 1);
                
                const statNotEl = document.getElementById('stat-not-printed-value');
                if (statNotEl) statNotEl.textContent = parseInt(statNotEl.textContent) + 1;
            }
        })
        .catch(err => {
            alert("Erreur lors de la mise à jour : " + err);
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        });
}

/* --- Online Results Logic --- */
let onlineData = null;

function fetchOnlineResults(listeId, listeDate) {
    const btn = document.getElementById('online-btn');
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Chargement...';

    fetch(`/api/online-results/${listeId}`)
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                alert("Erreur API: " + data.error);
                btn.disabled = false;
                btn.innerHTML = originalHtml;
                return;
            }
            onlineData = data;

            const pendingPatients = [];
            document.querySelectorAll('.badge-pending').forEach(badge => {
                const row = badge.closest('tr');
                const nameEl = row.querySelector('.patient-name-text');
                if (nameEl) {
                    const fullName = nameEl.textContent.trim().toUpperCase().replace(/\s+/g, ' ');
                    pendingPatients.push(fullName);
                }
            });

            const matched = onlineData.filter(item => {
                const apiFullName = (item.Nom.trim() + " " + item.Prenom.trim()).toUpperCase().replace(/\s+/g, ' ');
                return pendingPatients.includes(apiFullName);
            });

            populateOnlineModal(matched, listeDate);
            new bootstrap.Modal(document.getElementById('onlineModal')).show();

            btn.disabled = false;
            btn.innerHTML = originalHtml;
        })
        .catch(err => {
            alert("Erreur de connexion: " + err);
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        });
}

function populateOnlineModal(patients, listeDate) {
    document.getElementById('online-liste-date').textContent = listeDate;
    const body = document.getElementById('online-results-body');

    if (!patients || patients.length === 0) {
        body.innerHTML = `
            <div class="text-center py-5 text-muted">
                <i class="bi bi-inbox" style="font-size:3rem"></i>
                <p class="mt-3">Aucun patient en cours trouvé dans les données online pour cette page.</p>
                <small>Note: Assurez-vous que les noms correspondent exactement (Nom Prénom).</small>
            </div>`;
        return;
    }

    let html = '';
    patients.forEach(patient => {
        html += `
        <div class="card border shadow-sm mb-4">
            <div class="card-header bg-light">
                <h6 class="fw-bold text-primary mb-0">
                    <i class="bi bi-person-fill me-2"></i>${patient.Nom} ${patient.Prenom}
                </h6>
            </div>
            <div class="table-responsive">
                <table class="table table-sm table-hover mb-0">
                    <thead class="table-light">
                        <tr class="small text-muted text-uppercase">
                            <th class="ps-3">Analyse</th>
                            <th>Paramètre</th>
                            <th>Résultat</th>
                            <th>Unité</th>
                            <th>Norme</th>
                            <th class="pe-3">État</th>
                        </tr>
                    </thead>
                    <tbody>`;

        patient.ListAnalyses.forEach(analyse => {
            analyse.ListParametres.forEach(param => {
                const isAbnormal = param.FlagNorme === 'H' || param.FlagNorme === 'B';
                const resultClass = isAbnormal ? 'text-danger fw-bold' : 'fw-bold';
                const resultText = param.Resultat || '<span class="text-muted fst-italic small">En attente</span>';
                const flagText = param.FlagNorme ? `<span class="badge bg-danger ms-1">${param.FlagNorme}</span>` : '';

                html += `
                <tr class="align-middle">
                    <td class="ps-3 text-muted small">${analyse.Analyse}</td>
                    <td>${param.Parametre}</td>
                    <td><span class="${resultClass}">${resultText}</span> ${flagText}</td>
                    <td><small>${param.Unite || ''}</small></td>
                    <td class="text-muted small">${param.Norme || ''}</td>
                    <td class="pe-3"><span class="badge bg-warning text-dark small">${param.EtatDescription}</span></td>
                </tr>`;
            });
        });

        html += `</tbody></table></div></div>`;
    });

    body.innerHTML = html;
}

/* --- Partial Print Logic --- */
function togglePrintButton(patientId) {
    const checkboxes = document.querySelectorAll(`.test-checkbox-${patientId}:checked`);
    const btn = document.getElementById(`print-selected-${patientId}`);
    if (btn) {
        if (checkboxes.length > 0) {
            btn.classList.remove('d-none');
        } else {
            btn.classList.add('d-none');
        }
    }
}

function printSelected(patientId) {
    const checkboxes = document.querySelectorAll(`.test-checkbox-${patientId}:checked`);
    const selectedIndices = Array.from(checkboxes).map(cb => parseInt(cb.value));
    
    if (selectedIndices.length === 0) return;

    fetch(`/generate-partial/${patientId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ test_indices: selectedIndices })
    })
    .then(response => response.json())
    .then(data => {
        if (data.pdf_url) {
            window.location.href = data.pdf_url;
        } else if (data.error) {
            alert("Erreur: " + data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert("Une erreur est survenue lors de la génération du PDF partiel.");
    });
}

/* --- Settings Logic --- */
function saveConfig() {
    const config = {
        api_key: document.getElementById('api_key_input').value,
        model: document.getElementById('model-select').value,
        online_username: document.getElementById('online_username').value,
        online_password: document.getElementById('online_password').value,
        lab_dr_name: document.getElementById('lab_dr_name').value,
        lab_addr_l1: document.getElementById('lab_addr_l1').value,
        lab_addr_l2: document.getElementById('lab_addr_l2').value,
        lab_tel: document.getElementById('lab_tel').value,
        lab_fax: document.getElementById('lab_fax').value,
        lab_mobile: document.getElementById('lab_mobile').value,
        backup_dir: document.getElementById('backup_dir_input').value,
        max_backups: parseInt(document.getElementById('max_backups_input').value) || 10,
        email_imap_server: document.getElementById('email_imap_server').value,
        email_user: document.getElementById('email_user').value,
        email_pass: document.getElementById('email_pass').value,
        email_folder: document.getElementById('email_folder').value,
        email_sender_filter: document.getElementById('email_sender_filter').value,
        email_subject_filter: document.getElementById('email_subject_filter').value,
        email_main_pdf_keyword: document.getElementById('email_main_pdf_keyword').value,
        email_fetch_interval: parseInt(document.getElementById('email_fetch_interval').value) || 60,
        delete_after_fetch: document.getElementById('delete_after_fetch').checked
    };
    fetch(CONFIG.urls.config, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(config)
    }).then(() => {
        alert("Paramètres enregistrés !");
        const modal = bootstrap.Modal.getInstance(document.getElementById('settingsModal'));
        if (modal) modal.hide();
    });
}

function fetchModels() {
    const btn = document.querySelector('[onclick="fetchModels()"]');
    if(btn) btn.disabled = true;
    fetch('/api/models')
        .then(res => res.json())
        .then(data => {
            const select = document.getElementById('model-select');
            if(!select) return;
            const currentVal = select.value;
            select.innerHTML = '';
            data.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m.name;
                opt.textContent = m.display_name;
                if (m.name === currentVal) opt.selected = true;
                select.appendChild(opt);
            });
            if (currentVal && !select.querySelector('option[selected]')) {
                if (!select.innerHTML.includes(currentVal)) {
                    select.selectedIndex = 0;
                }
            } else if (!currentVal) {
                select.selectedIndex = 0;
            }
            if(btn) btn.disabled = false;
        })
        .catch(err => {
            alert("Erreur lors de la récupération des modèles.");
            if(btn) btn.disabled = false;
        });
}

function testBackupDir() {
    const path = document.getElementById('backup_dir_input').value;
    fetch('/api/test-backup-dir', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ path: path })
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                alert(data.message);
            } else {
                alert("Erreur: " + data.error);
            }
        })
        .catch(err => {
            alert("Erreur lors du test de connexion.");
        });
}

/* --- Notification Logic --- */
let unreadCount = 0;

function fetchNotifications() {
    fetch('/api/notifications')
        .then(res => res.json())
        .then(data => {
            const badge = document.getElementById('notification-badge');
            const itemsContainer = document.getElementById('notification-items');
            if (!badge || !itemsContainer) return;

            const unread = data.filter(n => n.is_read === 0);
            unreadCount = unread.length;
            
            if (data.length > 0) {
                if (unreadCount > 0) {
                    badge.textContent = unreadCount;
                    badge.classList.remove('d-none');
                } else {
                    badge.classList.add('d-none');
                }
                
                let html = '';
                data.forEach(notif => {
                    const isRead = notif.is_read === 1;
                    const textClass = isRead ? 'text-muted opacity-75' : '';
                    const iconColor = isRead ? 'text-muted' : (notif.type === 'new_patient' ? 'text-primary' : 'text-success');
                    const icon = notif.type === 'new_patient' ? 'bi-person-plus-fill' : 'bi-check-circle-fill';
                    const date = new Date(notif.created_at).toLocaleString('fr-FR', { hour: '2-digit', minute: '2-digit' });

                    let notifContent = `
                        <li class="p-2 border-bottom hover-bg ${isRead ? 'bg-light-subtle' : ''}">
                            <div class="d-flex align-items-start gap-2 ${textClass}">
                                <i class="bi ${icon} ${iconColor} mt-1"></i>
                                <div>
                                    <div class="small fw-bold">${notif.message}</div>
                                    <div class="text-muted" style="font-size: 0.7rem;">${date}</div>
                                </div>
                            </div>
                        </li>
                    `;

                    if (notif.type === 'new_patient' && notif.liste_id) {
                        html += `<a href="/dashboard?liste_id=${notif.liste_id}" class="text-decoration-none text-reset">${notifContent}</a>`;
                    } else if (notif.patient_id) {
                        html += `<a href="/view-db/${notif.patient_id}" class="text-decoration-none text-reset">${notifContent}</a>`;
                    } else {
                        html += notifContent;
                    }
                });
                itemsContainer.innerHTML = html;
            } else {
                badge.classList.add('d-none');
                itemsContainer.innerHTML = `
                    <li class="p-4 text-center text-muted small">
                        <i class="bi bi-envelope-open d-block fs-2 mb-2 opacity-50"></i>
                        Aucune nouvelle notification
                    </li>
                `;
            }
        });
}

function markNotificationsRead() {
    if (unreadCount === 0) return;
    
    fetch('/api/notifications/read', { method: 'POST' })
        .then(() => {
            unreadCount = 0;
            const badge = document.getElementById('notification-badge');
            if (badge) badge.classList.add('d-none');
        });
}

/* --- Backup Logic --- */
function triggerBackup(btn) {
    const originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Sauvegarde...';
    
    fetch(CONFIG.urls.backup, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            btn.disabled = false;
            btn.innerHTML = originalHTML;
            if (data.success) {
                alert("Sauvegarde créée avec succès !");
            } else {
                alert("Erreur : " + (data.error || "La sauvegarde a échoué"));
            }
        })
        .catch(err => {
            btn.disabled = false;
            btn.innerHTML = originalHTML;
            alert("Erreur de connexion lors de la sauvegarde.");
        });
}

function triggerQuickEmailFetch(btn) {
    const icon = document.getElementById('quick-fetch-icon');
    if (!icon || icon.classList.contains('spin-animation')) return;

    icon.classList.add('spin-animation');
    
    fetch("/api/trigger-email-fetch", { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            icon.classList.remove('spin-animation');
            if (data.success) {
                if (data.count > 0) {
                    fetchNotifications();
                    refreshEmailActivity();
                } else {
                    alert("Aucun nouvel e-mail trouvé.");
                }
            } else {
                alert("Erreur : " + (data.error || "La récupération a échoué"));
            }
        })
        .catch(err => {
            icon.classList.remove('spin-animation');
            console.error("Quick fetch error:", err);
            alert("Erreur de connexion lors de la récupération des emails.");
        });
}

function refreshEmailActivity() {
    const log = document.getElementById('email-activity-log');
    if (!log) return;
    log.textContent = 'Chargement...';
    fetch('/api/email-activity')
        .then(res => res.json())
        .then(data => {
            log.textContent = data.lines.join('\n') || 'Aucune activité.';
            log.scrollTop = log.scrollHeight;
        })
        .catch(() => {
            log.textContent = 'Erreur lors du chargement.';
        });
}

/* --- Search Logic --- */
let searchTimer;
function debounceSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
        const input = document.getElementById('search-input');
        if (input) {
            sessionStorage.setItem('search_cursor_pos', input.selectionStart);
            input.form.submit();
        }
    }, 400);
}

/* --- Modal Upload Logic --- */
function updateModalFileName(input) {
    const fileName = input.files[0] ? input.files[0].name : '';
    const el = document.getElementById('modal-file-name');
    if (el) el.textContent = fileName;
}

function setModalStep(id, status) {
    const step = document.getElementById(id);
    if(!step) return;
    step.classList.add('active');
    if (status === 'completed') {
        step.classList.remove('active');
        step.classList.add('completed');
        const icon = step.querySelector('.step-icon i');
        if(icon) icon.className = 'bi bi-check-lg';
    }
}

/* --- Initialization --- */
document.addEventListener('DOMContentLoaded', function() {
    // 1. Notification Polling
    fetchNotifications();
    setInterval(fetchNotifications, 60000);

    // 2. Auto-load Email Activity when tab is shown
    document.querySelectorAll('[data-bs-target="#tab-email"]').forEach(tab => {
        tab.addEventListener('shown.bs.tab', refreshEmailActivity);
    });

    // 3. Theme Initialization
    const savedTheme = localStorage.getItem('theme') || 'light';
    updateThemeIcon(savedTheme);

    // 4. Restore focus and cursor position on page load
    const input = document.getElementById('search-input');
    if (input && CONFIG.searchQuery) {
        input.focus();
        const pos = sessionStorage.getItem('search_cursor_pos');
        if (pos !== null) {
            input.setSelectionRange(pos, pos);
        } else {
            input.setSelectionRange(CONFIG.searchQuery.length, CONFIG.searchQuery.length);
        }
    }

    // 5. Settings Modal Event Listener
    const settingsModal = document.getElementById('settingsModal');
    if (settingsModal) {
        settingsModal.addEventListener('show.bs.modal', function () {
            fetch(CONFIG.urls.config)
                .then(res => res.json())
                .then(data => {
                    const apiKeyInput = document.getElementById('api_key_input');
                    const usernameInput = document.getElementById('online_username');
                    const passwordInput = document.getElementById('online_password');
                    const drNameInput = document.getElementById('lab_dr_name');
                    const addrL1Input = document.getElementById('lab_addr_l1');
                    const addrL2Input = document.getElementById('lab_addr_l2');
                    const telInput = document.getElementById('lab_tel');
                    const faxInput = document.getElementById('lab_fax');
                    const mobileInput = document.getElementById('lab_mobile');
                    const backupDirInput = document.getElementById('backup_dir_input');
                    const maxBackupsInput = document.getElementById('max_backups_input');
                    const emailImapInput = document.getElementById('email_imap_server');
                    const emailUserInput = document.getElementById('email_user');
                    const emailPassInput = document.getElementById('email_pass');
                    const emailFolderInput = document.getElementById('email_folder');
                    const emailSenderInput = document.getElementById('email_sender_filter');
                    const emailSubjectInput = document.getElementById('email_subject_filter');
                    const emailKeywordInput = document.getElementById('email_main_pdf_keyword');
                    const emailIntervalInput = document.getElementById('email_fetch_interval');
                    const select = document.getElementById('model-select');
                    
                    if (apiKeyInput) apiKeyInput.value = data.api_key || '';
                    if (usernameInput) usernameInput.value = data.online_username || '';
                    if (passwordInput) passwordInput.value = data.online_password || '';
                    if (drNameInput) drNameInput.value = data.lab_dr_name || '';
                    if (addrL1Input) addrL1Input.value = data.lab_addr_l1 || '';
                    if (addrL2Input) addrL2Input.value = data.lab_addr_l2 || '';
                    if (telInput) telInput.value = data.lab_tel || '';
                    if (faxInput) faxInput.value = data.lab_fax || '';
                    if (mobileInput) mobileInput.value = data.lab_mobile || '';
                    if (backupDirInput) backupDirInput.value = data.backup_dir || '';
                    if (maxBackupsInput) maxBackupsInput.value = data.max_backups || 10;
                    if (emailImapInput) emailImapInput.value = data.email_imap_server || '';
                    if (emailUserInput) emailUserInput.value = data.email_user || '';
                    if (emailPassInput) emailPassInput.value = data.email_pass || '';
                    if (emailFolderInput) emailFolderInput.value = data.email_folder || 'INBOX';
                    if (emailSenderInput) emailSenderInput.value = data.email_sender_filter || '';
                    if (emailSubjectInput) emailSubjectInput.value = data.email_subject_filter || 'Compte Rendu';
                    if (emailKeywordInput) emailKeywordInput.value = data.email_main_pdf_keyword || 'liste';
                    if (emailIntervalInput) emailIntervalInput.value = data.email_fetch_interval || 60;
                    
                    if (select) {
                        const modelMap = {
                            'gemini-2.5-flash': 'Gemini 2.5 Flash',
                            'models/gemini-2.5-flash': 'Gemini 2.5 Flash',
                            'gemini-2.0-flash': 'Gemini 2.0 Flash',
                            'models/gemini-2.0-flash': 'Gemini 2.0 Flash',
                            'gemini-1.5-flash': 'Gemini 1.5 Flash',
                            'models/gemini-1.5-flash': 'Gemini 1.5 Flash'
                        };
                        const displayName = modelMap[data.model] || data.model;
                        select.innerHTML = `<option value="${data.model}">${displayName}</option>`;
                    }
                });
            fetchModels();
        });
    }

    // 6. Upload Form Handling
    const uploadForm = document.getElementById('modal-upload-form');
    if (uploadForm) {
        uploadForm.onsubmit = function(e) {
            e.preventDefault();
            
            const fileInput = document.getElementById('modal_pdf_file');
            if (!fileInput || !fileInput.files[0]) {
                alert("Veuillez sélectionner un fichier PDF d'abord.");
                return;
            }

            document.getElementById('upload-form-container').style.display = 'none';
            document.getElementById('modal-error-container').innerHTML = '';
            document.getElementById('modal-processing-stepper').style.display = 'block';
            document.getElementById('close-modal-btn').style.display = 'none'; 

            const formData = new FormData(this);
            const xhr = new XMLHttpRequest();

            setModalStep('m-step-upload', 'active');
            document.getElementById('m-upload-progress-container').style.display = 'block';
            
            xhr.upload.onprogress = function(e) {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    document.getElementById('m-upload-progress-bar').style.width = percent + '%';
                    document.getElementById('m-upload-status').textContent = `Téléchargement : ${percent}%`;
                }
            };

            xhr.onload = function() {
                if (xhr.status >= 200 && xhr.status < 400) {
                    if (xhr.responseURL.includes('/dashboard')) {
                        setModalStep('m-step-processing', 'completed');
                        setModalStep('m-step-final', 'completed');
                        setTimeout(() => {
                            window.location.href = xhr.responseURL;
                        }, 500);
                    } else {
                        const parser = new DOMParser();
                        const doc = parser.parseFromString(xhr.responseText, 'text/html');
                        const errorDiv = doc.querySelector('.alert-danger');
                        
                        document.getElementById('modal-processing-stepper').style.display = 'none';
                        document.getElementById('upload-form-container').style.display = 'block';
                        document.getElementById('close-modal-btn').style.display = 'block';

                        if (errorDiv) {
                            document.getElementById('modal-error-container').innerHTML = `
                                <div class="alert alert-danger mb-3">${errorDiv.innerHTML}</div>
                            `;
                        } else {
                            alert("Une erreur inconnue est survenue.");
                        }
                    }
                } else {
                    alert("Erreur serveur (" + xhr.status + ")");
                    window.location.reload();
                }
            };

            xhr.upload.onload = function() {
                setModalStep('m-step-upload', 'completed');
                document.getElementById('m-upload-status').textContent = 'Fichier reçu';
                setModalStep('m-step-ai', 'active');
                
                setTimeout(() => { if (xhr.readyState < 4) { setModalStep('m-step-ai', 'completed'); setModalStep('m-step-processing', 'active'); } }, 4000);
                setTimeout(() => { if (xhr.readyState < 4) { setModalStep('m-step-processing', 'completed'); setModalStep('m-step-final', 'active'); } }, 10000);
            };

            xhr.open('POST', CONFIG.urls.upload, true);
            xhr.send(formData);
        };
    }

    // 7. Reset modal on close
    const uploadModal = document.getElementById('uploadModal');
    if (uploadModal) {
        uploadModal.addEventListener('hidden.bs.modal', function () {
            if (uploadForm) uploadForm.reset();
            const fileNameEl = document.getElementById('modal-file-name');
            if (fileNameEl) fileNameEl.textContent = '';
            document.getElementById('upload-form-container').style.display = 'block';
            document.getElementById('modal-processing-stepper').style.display = 'none';
            document.getElementById('modal-error-container').innerHTML = '';
            document.getElementById('close-modal-btn').style.display = 'block';
            
            ['m-step-upload', 'm-step-ai', 'm-step-processing', 'm-step-final'].forEach(id => {
                const step = document.getElementById(id);
                if(!step) return;
                step.classList.remove('active', 'completed');
                const icon = step.querySelector('.step-icon i');
                if(!icon) return;
                if(id === 'm-step-upload') icon.className = 'bi bi-upload';
                if(id === 'm-step-ai') icon.className = 'bi bi-robot';
                if(id === 'm-step-processing') icon.className = 'bi bi-gear-fill';
                if(id === 'm-step-final') icon.className = 'bi bi-check-lg';
            });
            document.getElementById('m-upload-progress-container').style.display = 'none';
            document.getElementById('m-upload-progress-bar').style.width = '0%';
        });
    }

    // 8. Edit Form Global Handler
    const editForm = document.getElementById('edit-patient-form');
    if (editForm) {
        editForm.onsubmit = function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            fetch('/update-patient', {
                method: 'POST',
                body: JSON.stringify(Object.fromEntries(formData)),
                headers: { 'Content-Type': 'application/json' }
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    window.location.reload();
                } else {
                    alert('Erreur: ' + data.error);
                }
            });
        };
    }
});
