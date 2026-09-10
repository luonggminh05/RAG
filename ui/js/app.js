/**
 * RAG COSMIC GALAXY AI - JAVASCRIPT ENTRY POINT (ES6 Modular Architecture)
 * - Modules: i18n, resizer, vision, document, chat, feedback
 * - Pure i18n Translation (100% Vietnamese or 100% English)
 * - 8-Directional Multi-Edge Drag Resize for Modals
 * - Soft Rounded Custom Dropdowns for RBAC & Language
 * - Real-time Agentic RAG SSE Stream with Citations & Retry API
 */

import { getCurrentLanguage, getT, setLanguage, applyTranslations } from './modules/i18n.js';
import { initModalMultiEdgeResizing } from './modules/resizer.js';
import { VisionHandler } from './modules/vision.js';
import { DocumentManager } from './modules/document.js';
import { ChatManager } from './modules/chat.js';

document.addEventListener('DOMContentLoaded', () => {
    // ── Application State ──
    const state = {
        selectedModel: 'qwen2.5vl:7b',
        currentUserRole: localStorage.getItem('cosmic_rag_user_role') || 'Admin',
        currentTheme: localStorage.getItem('cosmic_rag_theme') || 'dark',
    };

    // ── DOM References ──
    const elements = {
        sidebar: document.getElementById('sidebar'),
        topbarSidebarToggleBtn: document.getElementById('topbarSidebarToggleBtn'),
        collapseSidebarBtn: document.getElementById('collapseSidebarBtn'),
        sidebarCollapseTrigger: document.getElementById('sidebarCollapseTrigger'),
        newChatBtn: document.getElementById('newChatBtn'),
        conversationsList: document.getElementById('conversationsList'),
        statusDot: document.getElementById('statusDot'),
        statusText: document.getElementById('statusText'),
        modelSelect: document.getElementById('modelSelect'),
        userRoleBadge: document.getElementById('userRoleBadge'),
        // Custom Dropdowns
        rbacDropdownWrap: document.getElementById('rbacDropdownWrap'),
        rbacTriggerBtn: document.getElementById('rbacTriggerBtn'),
        rbacSelectedLabel: document.getElementById('rbacSelectedLabel'),
        rbacDropdownPanel: document.getElementById('rbacDropdownPanel'),
        langDropdownWrap: document.getElementById('langDropdownWrap'),
        langTriggerBtn: document.getElementById('langTriggerBtn'),
        langSelectedLabel: document.getElementById('langSelectedLabel'),
        langDropdownPanel: document.getElementById('langDropdownPanel'),

        visionToggle: document.getElementById('visionToggle'),
        chatContainer: document.getElementById('chatContainer'),
        welcomeHero: document.getElementById('welcomeHero'),
        greetingTitle: document.getElementById('greetingTitle'),
        messageList: document.getElementById('messageList'),
        imagePreviewStrip: document.getElementById('imagePreviewStrip'),
        attachBtn: document.getElementById('attachBtn'),
        imageFileInput: document.getElementById('imageFileInput'),
        chatInput: document.getElementById('chatInput'),
        sendBtn: document.getElementById('sendBtn'),
        chatModePill: document.getElementById('chatModePill'),
        coworkModePill: document.getElementById('coworkModePill'),
        themeToggleBtn: document.getElementById('themeToggleBtn'),
        // Manage Document Modal
        manageDocModal: document.getElementById('manageDocModal'),
        manageDialogBox: document.getElementById('manageDialogBox'),
        openManageDocBtn: document.getElementById('openManageDocBtn'),
        closeManageDocModalBtn: document.getElementById('closeManageDocModalBtn'),
        docsTableBody: document.getElementById('docsTableBody'),
        openUploadFromManageBtn: document.getElementById('openUploadFromManageBtn'),
        // Upload Document Modal
        uploadDocModal: document.getElementById('uploadDocModal'),
        uploadDialogBox: document.getElementById('uploadDialogBox'),
        closeUploadDocModalBtn: document.getElementById('closeUploadDocModalBtn'),
        uploadDocForm: document.getElementById('uploadDocForm'),
        dropzone: document.getElementById('dropzone'),
        dropzoneText: document.getElementById('dropzoneText'),
        docFileInput: document.getElementById('docFileInput'),
        selectedFilesBadge: document.getElementById('selectedFilesBadge'),
        docNameInput: document.getElementById('docNameInput'),
        docUploadDateInput: document.getElementById('docUploadDateInput'),
        docCategoryInput: document.getElementById('docCategoryInput'),
        docAccessScopeSelect: document.getElementById('docAccessScopeSelect'),
        allowedRolesGroup: document.getElementById('allowedRolesGroup'),
        uploadOcrToggle: document.getElementById('uploadOcrToggle'),
        uploadVisionToggle: document.getElementById('uploadVisionToggle'),
        ingestProgressContainer: document.getElementById('ingestProgressContainer'),
        progressStatusLabel: document.getElementById('progressStatusLabel'),
        progressPercentLabel: document.getElementById('progressPercentLabel'),
        progressBarFill: document.getElementById('progressBarFill'),
        submitUploadBtn: document.getElementById('submitUploadBtn'),
        // Edit Document Modal
        editDocModal: document.getElementById('editDocModal'),
        closeEditDocModalBtn: document.getElementById('closeEditDocModalBtn'),
        editDocForm: document.getElementById('editDocForm'),
        editDocId: document.getElementById('editDocId'),
        editDocSubTitle: document.getElementById('editDocSubTitle'),
        editDocNameInput: document.getElementById('editDocNameInput'),
        editDocCategoryInput: document.getElementById('editDocCategoryInput'),
        editDocAccessScopeSelect: document.getElementById('editDocAccessScopeSelect'),
        editAllowedRolesGroup: document.getElementById('editAllowedRolesGroup'),
        // Citations Modal
        citationModal: document.getElementById('citationModal'),
        closeCitationModalBtn: document.getElementById('closeCitationModalBtn'),
        citationModalTitle: document.getElementById('citationModalTitle'),
        citationModalSource: document.getElementById('citationModalSource'),
        citationModalBody: document.getElementById('citationModalBody'),
        dragDropOverlay: document.getElementById('dragDropOverlay'),
        scrollBottomBtn: document.getElementById('scrollBottomBtn'),
        scrollUnreadDot: document.getElementById('scrollUnreadDot'),
        toastContainer: document.getElementById('toastContainer'),
    };

    // ── Helper: Toast Notifications ──
    function showToast(message, duration = 3200) {
        if (!elements.toastContainer) return;
        const toast = document.createElement('div');
        toast.className = 'toast-bubble';
        toast.textContent = message;
        elements.toastContainer.appendChild(toast);

        requestAnimationFrame(() => {
            toast.classList.add('visible');
        });

        setTimeout(() => {
            toast.classList.remove('visible');
            setTimeout(() => toast.remove(), 350);
        }, duration);
    }

    // ── Dynamic Greeting ──
    function setDynamicGreeting() {
        if (!elements.greetingTitle) return;
        const hour = new Date().getHours();
        let greetingKey = 'greeting_morning';
        if (hour >= 12 && hour < 18) greetingKey = 'greeting_afternoon';
        else if (hour >= 18 || hour < 5) greetingKey = 'greeting_evening';
        elements.greetingTitle.textContent = getT(greetingKey);
    }

    // ── Theme Management ──
    function initTheme() {
        applyTheme(state.currentTheme);
        elements.themeToggleBtn?.addEventListener('click', () => {
            const nextTheme = state.currentTheme === 'dark' ? 'light' : 'dark';
            applyTheme(nextTheme);
            showToast(`${getT('toast_theme_switched')}: ${nextTheme === 'light' ? 'Light Mode' : 'Dark Mode'}`);
        });
    }

    function applyTheme(theme) {
        state.currentTheme = theme;
        localStorage.setItem('cosmic_rag_theme', theme);
        const isLight = theme === 'light';
        document.body.className = isLight ? 'light-theme' : 'claude-cosmic-theme';

        const moonIcon = elements.themeToggleBtn?.querySelector('.theme-icon-moon');
        const sunIcon = elements.themeToggleBtn?.querySelector('.theme-icon-sun');
        if (moonIcon && sunIcon) {
            moonIcon.style.display = isLight ? 'none' : 'block';
            sunIcon.style.display = isLight ? 'block' : 'none';
        }
    }

    // ── Sidebar Management ──
    function initSidebarState() {
        const isCollapsed = localStorage.getItem('cosmic_rag_sidebar_collapsed') === '1';
        if (isCollapsed && elements.sidebar) {
            elements.sidebar.classList.add('collapsed');
        }

        const toggleSidebar = () => {
            if (!elements.sidebar) return;
            const collapsed = elements.sidebar.classList.toggle('collapsed');
            localStorage.setItem('cosmic_rag_sidebar_collapsed', collapsed ? '1' : '0');
        };

        elements.topbarSidebarToggleBtn?.addEventListener('click', toggleSidebar);
        elements.collapseSidebarBtn?.addEventListener('click', toggleSidebar);
        elements.sidebarCollapseTrigger?.addEventListener('click', toggleSidebar);

        window.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === '\\') {
                e.preventDefault();
                toggleSidebar();
            }
        });
    }

    // ── Custom Dropdowns (RBAC & Language) ──
    function initCustomDropdowns() {
        // RBAC Dropdown
        if (elements.rbacSelectedLabel) elements.rbacSelectedLabel.textContent = state.currentUserRole;
        if (elements.userRoleBadge) elements.userRoleBadge.textContent = state.currentUserRole;

        document.querySelectorAll('#rbacDropdownPanel .custom-dropdown-option').forEach(opt => {
            opt.classList.toggle('active', opt.getAttribute('data-role') === state.currentUserRole);
        });

        elements.rbacTriggerBtn?.addEventListener('click', (e) => {
            e.stopPropagation();
            elements.rbacDropdownWrap?.classList.toggle('open');
            elements.langDropdownWrap?.classList.remove('open');
        });

        document.querySelectorAll('#rbacDropdownPanel .custom-dropdown-option').forEach(opt => {
            opt.addEventListener('click', (e) => {
                e.stopPropagation();
                const role = opt.getAttribute('data-role');
                state.currentUserRole = role;
                localStorage.setItem('cosmic_rag_user_role', role);

                if (elements.rbacSelectedLabel) elements.rbacSelectedLabel.textContent = role;
                if (elements.userRoleBadge) elements.userRoleBadge.textContent = role;

                document.querySelectorAll('#rbacDropdownPanel .custom-dropdown-option').forEach(o => {
                    o.classList.toggle('active', o === opt);
                });

                elements.rbacDropdownWrap?.classList.remove('open');
                showToast(`${getT('toast_role_switched')}: ${role}`);
            });
        });

        // Language Dropdown
        const currentLang = getCurrentLanguage();
        if (elements.langSelectedLabel) {
            elements.langSelectedLabel.textContent = currentLang === 'vi' ? 'Tiếng Việt' : 'English';
        }

        elements.langTriggerBtn?.addEventListener('click', (e) => {
            e.stopPropagation();
            elements.langDropdownWrap?.classList.toggle('open');
            elements.rbacDropdownWrap?.classList.remove('open');
        });

        document.querySelectorAll('#langDropdownPanel .custom-dropdown-option').forEach(opt => {
            opt.classList.toggle('active', opt.getAttribute('data-lang') === currentLang);
            opt.addEventListener('click', (e) => {
                e.stopPropagation();
                const lang = opt.getAttribute('data-lang');
                setLanguage(lang);
                if (elements.langSelectedLabel) {
                    elements.langSelectedLabel.textContent = lang === 'vi' ? 'Tiếng Việt' : 'English';
                }
                document.querySelectorAll('#langDropdownPanel .custom-dropdown-option').forEach(o => {
                    o.classList.toggle('active', o === opt);
                });
                elements.langDropdownWrap?.classList.remove('open');
                setDynamicGreeting();
                showToast(getT('toast_lang_switched'));
            });
        });

        window.addEventListener('click', () => {
            elements.rbacDropdownWrap?.classList.remove('open');
            elements.langDropdownWrap?.classList.remove('open');
        });
    }

    // ── Dynamic Models & System Status ──
    async function fetchModelsCatalog() {
        try {
            const res = await fetch('/api/v1/chat/models');
            if (res.ok) {
                const data = await res.json();
                renderModelSelector(data.models || [], data.current_default);
                setSystemStatus(true, getT('engine_ready'));
            } else {
                setSystemStatus(false, getT('engine_offline'));
            }
        } catch {
            setSystemStatus(false, getT('engine_offline'));
        }
    }

    function renderModelSelector(models, defaultModel) {
        if (!elements.modelSelect) return;
        elements.modelSelect.innerHTML = '';
        models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m.id;
            opt.textContent = m.name;
            if (m.id === defaultModel || m.id === state.selectedModel) {
                opt.selected = true;
                state.selectedModel = m.id;
            }
            elements.modelSelect.appendChild(opt);
        });

        elements.modelSelect.addEventListener('change', (e) => {
            state.selectedModel = e.target.value;
        });
    }

    function setSystemStatus(isOnline, text) {
        if (elements.statusDot) {
            elements.statusDot.className = `status-dot ${isOnline ? 'online' : 'offline'}`;
        }
        if (elements.statusText) {
            elements.statusText.textContent = text;
        }
    }

    // ── Module Initialization & Wiring ──
    async function initApp() {
        initTheme();
        initSidebarState();
        applyTranslations();
        setDynamicGreeting();
        initCustomDropdowns();
        initModalMultiEdgeResizing();

        // 1. Vision Module
        const visionHandler = new VisionHandler({
            attachBtn: elements.attachBtn,
            imageFileInput: elements.imageFileInput,
            imagePreviewStrip: elements.imagePreviewStrip,
            dragDropOverlay: elements.dragDropOverlay,
            showToast,
        });

        elements.visionToggle?.addEventListener('change', (e) => {
            visionHandler.setEnabled(e.target.checked);
        });

        // 2. Document Module
        const documentManager = new DocumentManager({
            elements,
            showToast,
        });

        // 3. Chat Module
        const chatManager = new ChatManager({
            elements,
            visionHandler,
            getRole: () => state.currentUserRole,
            getModel: () => state.selectedModel,
            showToast,
        });

        // Mode Pills
        elements.chatModePill?.addEventListener('click', () => {
            elements.chatModePill.classList.add('active');
            elements.coworkModePill?.classList.remove('active');
        });
        elements.coworkModePill?.addEventListener('click', () => {
            elements.coworkModePill.classList.add('active');
            elements.chatModePill?.classList.remove('active');
            showToast(getT('toast_reasoning_mode'));
        });

        await fetchModelsCatalog();
        await chatManager.loadConversations();

        if (chatManager.currentConversationId) {
            await chatManager.loadConversationMessages(chatManager.currentConversationId);
        }
    }

    initApp();
});
