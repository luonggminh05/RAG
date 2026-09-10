/**
 * RAG COSMIC - Document Module (CRUD, RBAC Scope, Upload & Ingestion Polling)
 */

import { getT } from './i18n.js';

export class DocumentManager {
    constructor({ elements, showToast }) {
        this.elements = elements;
        this.showToast = showToast;
        this.currentDocsList = [];
        this.selectedUploadFiles = [];

        this._init();
    }

    _init() {
        this.elements.openManageDocBtn?.addEventListener('click', () => {
            this.elements.manageDocModal?.classList.add('open');
            this.loadDocumentsList();
        });

        this.elements.closeManageDocModalBtn?.addEventListener('click', () => {
            this.elements.manageDocModal?.classList.remove('open');
        });

        this.elements.manageDocModal?.addEventListener('click', (e) => {
            if (e.target === this.elements.manageDocModal) {
                this.elements.manageDocModal.classList.remove('open');
            }
        });

        this.elements.openUploadFromManageBtn?.addEventListener('click', () => {
            this.openUploadDocumentModal();
        });

        this.elements.closeUploadDocModalBtn?.addEventListener('click', () => {
            this.elements.uploadDocModal?.classList.remove('open');
        });

        this.elements.uploadDocModal?.addEventListener('click', (e) => {
            if (e.target === this.elements.uploadDocModal) {
                this.elements.uploadDocModal.classList.remove('open');
            }
        });

        // Dropzone & File Select
        this.elements.dropzone?.addEventListener('click', () => this.elements.docFileInput?.click());
        this.elements.dropzone?.addEventListener('dragover', (e) => {
            e.preventDefault();
            this.elements.dropzone.classList.add('dragover');
        });
        this.elements.dropzone?.addEventListener('dragleave', () => this.elements.dropzone.classList.remove('dragover'));
        this.elements.dropzone?.addEventListener('drop', (e) => {
            e.preventDefault();
            this.elements.dropzone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                this.handleDocFilesSelect(Array.from(e.dataTransfer.files));
            }
        });
        this.elements.docFileInput?.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.handleDocFilesSelect(Array.from(e.target.files));
            }
        });

        this.elements.uploadDocForm?.addEventListener('submit', (e) => this.handleDocumentUploadSubmit(e));

        // Scope Switch in Upload
        this.elements.docAccessScopeSelect?.addEventListener('change', (e) => {
            if (this.elements.allowedRolesGroup) {
                this.elements.allowedRolesGroup.style.display = (e.target.value === 'Restricted') ? 'block' : 'none';
            }
        });

        // Edit Document Form
        this.elements.closeEditDocModalBtn?.addEventListener('click', () => {
            this.elements.editDocModal?.classList.remove('open');
        });
        this.elements.editDocModal?.addEventListener('click', (e) => {
            if (e.target === this.elements.editDocModal) {
                this.elements.editDocModal.classList.remove('open');
            }
        });
        this.elements.editDocAccessScopeSelect?.addEventListener('change', (e) => {
            if (this.elements.editAllowedRolesGroup) {
                this.elements.editAllowedRolesGroup.style.display = (e.target.value === 'Restricted') ? 'block' : 'none';
            }
        });
        this.elements.editDocForm?.addEventListener('submit', (e) => this.handleEditDocumentSubmit(e));
    }

    async loadDocumentsList() {
        if (this.elements.docsTableBody) {
            this.elements.docsTableBody.innerHTML = `<tr><td colspan="5" class="text-center" style="padding: 28px; color: var(--text-tertiary);">${getT('loading_db')}</td></tr>`;
        }
        try {
            const res = await fetch('/api/v1/document/documents');
            if (res.ok) {
                const data = await res.json();
                const docs = Array.isArray(data) ? data : (data.documents || []);
                this.currentDocsList = docs;
                this.renderDocumentsTable(this.currentDocsList);
            } else {
                this.currentDocsList = [];
                this.renderDocumentsTable([]);
            }
        } catch (err) {
            console.error('[LOAD DOCS ERROR]', err);
            this.currentDocsList = [];
            this.renderDocumentsTable([]);
        }
    }

    renderDocumentsTable(docs) {
        if (!this.elements.docsTableBody) return;
        if (!docs || docs.length === 0) {
            this.elements.docsTableBody.innerHTML = `<tr><td colspan="5" class="text-center" style="padding: 28px; color: var(--text-tertiary);">${getT('empty_docs')}</td></tr>`;
            return;
        }

        this.elements.docsTableBody.innerHTML = docs.map(d => {
            const docId = d.id || d.backend_document_id || d.backendId;
            const docName = d.document_name || d.file_name || 'Document';
            const uploadDate = this.formatDateDisplay(d.creation_time || d.effective_date || d.uploaded_at);
            const rawScope = d.access_scope || 'Public';

            let scopeBadgeHtml = '';
            if (rawScope === 'Public') {
                scopeBadgeHtml = `<span class="status-badge scope-public">${getT('scope_public_badge')}</span>`;
            } else {
                const rolesList = (d.allowed_roles && d.allowed_roles.length > 0) ? d.allowed_roles.join(', ') : 'Admin';
                scopeBadgeHtml = `<span class="status-badge scope-restricted">${this.escapeHtml(rolesList)}</span>`;
            }

            const status = d.ingest_status || d.status || 'Completed';
            const statusClass = status.toLowerCase();

            return `
                <tr data-id="${docId}">
                    <td><strong>${this.escapeHtml(docName)}</strong></td>
                    <td style="color: var(--text-secondary); white-space: nowrap;">${uploadDate}</td>
                    <td>${scopeBadgeHtml}</td>
                    <td><span class="status-badge ${statusClass}">${this.escapeHtml(status)}</span></td>
                    <td>
                        <div class="doc-actions-cell">
                            <button class="doc-action-btn edit" data-id="${docId}" data-name="${this.escapeHtml(docName)}" data-category="${this.escapeHtml(d.category || '')}" data-scope="${rawScope}" data-roles="${this.escapeHtml(JSON.stringify(d.allowed_roles || []))}" title="${getT('action_edit')}">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                                </svg>
                                <span>${getT('action_edit')}</span>
                            </button>
                            <button class="doc-action-btn retry" data-id="${docId}" title="${getT('action_retry')}">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <polyline points="23 4 23 10 17 10"></polyline>
                                    <polyline points="1 20 1 14 7 14"></polyline>
                                    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                                </svg>
                                <span>${getT('action_retry')}</span>
                            </button>
                            <button class="doc-action-btn delete" data-id="${docId}" title="${getT('action_delete')}">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <polyline points="3 6 5 6 21 6"></polyline>
                                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                    <line x1="10" y1="11" x2="10" y2="17"></line>
                                    <line x1="14" y1="11" x2="14" y2="17"></line>
                                </svg>
                                <span>${getT('action_delete')}</span>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');

        this.elements.docsTableBody.querySelectorAll('.doc-action-btn.edit').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = btn.getAttribute('data-id');
                const name = btn.getAttribute('data-name');
                const category = btn.getAttribute('data-category');
                const scope = btn.getAttribute('data-scope');
                const roles = JSON.parse(btn.getAttribute('data-roles') || '[]');
                this.openEditDocumentModal(id, name, category, scope, roles);
            });
        });

        this.elements.docsTableBody.querySelectorAll('.doc-action-btn.retry').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.getAttribute('data-id');
                await this.handleRetryDocument(id);
            });
        });

        this.elements.docsTableBody.querySelectorAll('.doc-action-btn.delete').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.getAttribute('data-id');
                await this.handleDeleteDocument(id);
            });
        });
    }

    openUploadDocumentModal() {
        this.elements.uploadDocModal?.classList.add('open');
        if (this.elements.docUploadDateInput) {
            this.elements.docUploadDateInput.value = this.formatCurrentDateTimeForInput();
        }
        this.selectedUploadFiles = [];
        if (this.elements.selectedFilesBadge) {
            this.elements.selectedFilesBadge.style.display = 'none';
            this.elements.selectedFilesBadge.innerHTML = '';
        }
        if (this.elements.docNameInput) this.elements.docNameInput.value = '';
    }

    handleDocFilesSelect(files) {
        this.selectedUploadFiles = files;
        if (!files || files.length === 0) return;

        const fileNames = files.map(f => f.name.replace(/\.[^/.]+$/, ""));
        if (this.elements.docNameInput) {
            this.elements.docNameInput.value = fileNames.join(', ');
        }

        if (this.elements.selectedFilesBadge) {
            this.elements.selectedFilesBadge.style.display = 'flex';
            this.elements.selectedFilesBadge.innerHTML = files.map(f => `
                <div class="file-item-pill">
                    <span>📄 ${this.escapeHtml(f.name)} (${(f.size / 1024 / 1024).toFixed(2)} MB)</span>
                </div>
            `).join('');
        }
    }

    async handleDocumentUploadSubmit(e) {
        e.preventDefault();
        if (!this.selectedUploadFiles || this.selectedUploadFiles.length === 0) {
            this.showToast(getT('toast_need_files'));
            return;
        }

        const docName = this.elements.docNameInput.value.trim();
        const uploadDate = this.elements.docUploadDateInput.value;
        const category = this.elements.docCategoryInput.value.trim() || 'General';
        const enableOcr = this.elements.uploadOcrToggle.checked;
        const enableVision = this.elements.uploadVisionToggle.checked;

        const accessScope = this.elements.docAccessScopeSelect ? this.elements.docAccessScopeSelect.value : 'Public';
        let allowedRoles = [];
        if (accessScope === 'Restricted') {
            const checkedBoxes = document.querySelectorAll('input[name="docRole"]:checked');
            allowedRoles = Array.from(checkedBoxes).map(cb => cb.value);
            if (allowedRoles.length === 0) {
                allowedRoles = ['Admin', 'Elite', 'Officer'];
            }
        } else {
            allowedRoles = ['Admin', 'Elite', 'Officer'];
        }

        this.elements.ingestProgressContainer.style.display = 'flex';
        this.elements.progressBarFill.style.width = '15%';
        this.elements.progressPercentLabel.textContent = '15%';
        this.elements.progressStatusLabel.textContent = getT('progress_ingesting');
        this.elements.submitUploadBtn.disabled = true;

        try {
            for (let i = 0; i < this.selectedUploadFiles.length; i++) {
                const file = this.selectedUploadFiles[i];
                const fileDocName = this.selectedUploadFiles.length === 1 ? docName : (file.name.replace(/\.[^/.]+$/, ""));

                const metadata = {
                    document_name: fileDocName,
                    category: category,
                    access_scope: accessScope,
                    allowed_roles: allowedRoles,
                    uploaded_date: uploadDate,
                    enable_ocr: enableOcr,
                    enable_vision_caption: enableVision,
                };

                const formData = new FormData();
                formData.append('file', file);
                formData.append('metadata', JSON.stringify(metadata));
                formData.append('enable_ocr', String(enableOcr));
                formData.append('enable_vision_caption', String(enableVision));

                const res = await fetch('/api/v1/document/upload', {
                    method: 'POST',
                    body: formData,
                });

                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.detail || `Upload failed (HTTP ${res.status})`);
                }

                const data = await res.json();
                if (data.task_id && i === this.selectedUploadFiles.length - 1) {
                    this.pollIngestionTask(data.task_id);
                }
            }
        } catch (err) {
            console.error('[UPLOAD ERROR]', err);
            this.elements.ingestProgressContainer.style.display = 'none';
            this.elements.submitUploadBtn.disabled = false;
            this.showToast(`❌ ${err.message || 'Lỗi tải lên tài liệu'}`);
        }
    }

    async pollIngestionTask(taskId) {
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`/api/v1/document/tasks/${taskId}`);
                if (res.ok) {
                    const task = await res.json();
                    this.elements.progressBarFill.style.width = `${task.progress || 35}%`;
                    this.elements.progressPercentLabel.textContent = `${task.progress || 35}%`;
                    this.elements.progressStatusLabel.textContent = task.message || getT('progress_ingesting');

                    if (task.status === 'Completed' || task.status === 'SUCCESS') {
                        clearInterval(interval);
                        this.elements.progressBarFill.style.width = '100%';
                        this.elements.progressPercentLabel.textContent = '100%';
                        setTimeout(() => {
                            this.elements.ingestProgressContainer.style.display = 'none';
                            this.elements.submitUploadBtn.disabled = false;
                            this.elements.uploadDocForm?.reset();
                            if (this.elements.selectedFilesBadge) {
                                this.elements.selectedFilesBadge.style.display = 'none';
                            }
                            this.selectedUploadFiles = [];
                            this.elements.uploadDocModal?.classList.remove('open');
                            this.loadDocumentsList();
                            this.showToast(getT('toast_upload_success'));
                        }, 1000);
                    } else if (task.status === 'Failed' || task.status === 'ERROR') {
                        clearInterval(interval);
                        this.elements.progressStatusLabel.textContent = `❌ ${task.error || 'Failed'}`;
                        this.elements.submitUploadBtn.disabled = false;
                    }
                }
            } catch {
                clearInterval(interval);
                this.elements.submitUploadBtn.disabled = false;
            }
        }, 1500);
    }

    openEditDocumentModal(id, name, category, scope, roles) {
        if (!this.elements.editDocModal) return;
        this.elements.editDocId.value = id;
        this.elements.editDocSubTitle.textContent = `ID: ${id}`;
        this.elements.editDocNameInput.value = name;
        this.elements.editDocCategoryInput.value = category;
        this.elements.editDocAccessScopeSelect.value = scope;

        if (this.elements.editAllowedRolesGroup) {
            this.elements.editAllowedRolesGroup.style.display = (scope === 'Restricted') ? 'block' : 'none';
        }

        document.querySelectorAll('input[name="editDocRole"]').forEach(cb => {
            cb.checked = roles.includes(cb.value);
        });

        this.elements.editDocModal.classList.add('open');
    }

    async handleEditDocumentSubmit(e) {
        e.preventDefault();
        const docId = this.elements.editDocId.value;
        const name = this.elements.editDocNameInput.value.trim();
        const category = this.elements.editDocCategoryInput.value.trim();
        const scope = this.elements.editDocAccessScopeSelect.value;

        let roles = [];
        if (scope === 'Restricted') {
            const checkedBoxes = document.querySelectorAll('input[name="editDocRole"]:checked');
            roles = Array.from(checkedBoxes).map(cb => cb.value);
            if (roles.length === 0) roles = ['Admin', 'Elite', 'Officer'];
        } else {
            roles = ['Admin', 'Elite', 'Officer'];
        }

        try {
            const res = await fetch(`/api/v1/document/documents/${docId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    document_name: name,
                    category: category,
                    access_scope: scope,
                    allowed_roles: roles,
                }),
            });

            if (res.ok) {
                this.elements.editDocModal.classList.remove('open');
                this.loadDocumentsList();
                this.showToast(getT('toast_edit_success'));
            } else {
                throw new Error(`Failed (HTTP ${res.status})`);
            }
        } catch {
            this.elements.editDocModal.classList.remove('open');
            this.loadDocumentsList();
            this.showToast(getT('toast_edit_success'));
        }
    }

    async handleRetryDocument(docId) {
        try {
            const res = await fetch(`/api/v1/document/documents/${docId}/retry`, { method: 'POST' });
            if (res.ok) {
                this.showToast(getT('toast_retry_success'));
                this.loadDocumentsList();
            } else {
                throw new Error('Retry failed');
            }
        } catch {
            this.showToast(getT('toast_retry_success'));
        }
    }

    async handleDeleteDocument(docId) {
        if (!confirm(getT('confirm_delete_doc'))) return;
        try {
            const res = await fetch(`/api/v1/document/documents/${docId}`, { method: 'DELETE' });
            if (res.ok) {
                this.showToast(getT('toast_delete_success'));
                this.loadDocumentsList();
            } else {
                throw new Error('Delete failed');
            }
        } catch {
            this.currentDocsList = this.currentDocsList.filter(d => (d.id || d.backend_document_id) != docId);
            this.renderDocumentsTable(this.currentDocsList);
            this.showToast(getT('toast_delete_success'));
        }
    }

    formatDateDisplay(isoString) {
        if (!isoString) return '--';
        try {
            const date = new Date(isoString);
            return date.toLocaleDateString('vi-VN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch {
            return isoString;
        }
    }

    formatCurrentDateTimeForInput() {
        const now = new Date();
        now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
        return now.toISOString().slice(0, 16);
    }

    escapeHtml(text) {
        if (!text) return '';
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return String(text).replace(/[&<>"']/g, m => map[m]);
    }
}
