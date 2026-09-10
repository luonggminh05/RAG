/**
 * RAG COSMIC - i18n Internationalization Module
 */

export const I18N = {
    vi: {
        page_title: "RAG Cosmic | Hệ thống Trợ lý Tri thức Vũ trụ",
        brand_name: "RAG",
        new_chat: "Cuộc trò chuyện mới",
        manage_doc: "Quản lý tài liệu",
        vision_mode: "Chế độ thị giác",
        role_admin: "Admin",
        role_elite: "Elite",
        role_officer: "Officer",
        lang_vi: "Tiếng Việt",
        lang_en: "English",
        pinned_header: "Đã ghim",
        pinned_sample_1: "Quy trình phê duyệt mua sắm TSCĐ",
        chats_header: "Lịch sử trò chuyện",
        loading_history: "Đang tải lịch sử...",
        no_history: "Chưa có cuộc trò chuyện nào",
        greeting_morning: "Suy ngẫm buổi sáng",
        greeting_afternoon: "Suy ngẫm buổi chiều",
        greeting_evening: "Suy ngẫm buổi tối",
        input_placeholder: "Tôi có thể hỗ trợ gì cho bạn hôm nay?",
        mode_chat: "Trò chuyện",
        mode_reasoning: "Suy luận sâu",
        model_quality: "Chất lượng cao",
        engine_ready: "Động cơ RAG sẵn sàng",
        engine_offline: "Ngoại tuyến",
        drag_drop_hint: "Thả hình ảnh vào đây để tải lên",
        // Manage Modal
        manage_modal_title: "Quản lý tài liệu tri thức",
        manage_modal_subtitle: "Dữ liệu tài liệu được tải trực tiếp từ cơ sở dữ liệu với phân quyền RBAC",
        upload_doc_btn: "Tải tài liệu lên",
        col_doc_name: "TÊN TÀI LIỆU",
        col_upload_date: "NGÀY TẢI LÊN",
        col_access_scope: "PHẠM VI TRUY CẬP",
        col_status: "TRẠNG THÁI",
        col_actions: "HÀNH ĐỘNG",
        loading_db: "Đang tải dữ liệu từ cơ sở dữ liệu...",
        empty_docs: "Chưa có tài liệu nào. Bấm nút 'Tải tài liệu lên' ở góc trên để nạp tài liệu mới.",
        action_edit: "Sửa",
        action_retry: "Thử lại",
        action_delete: "Xóa",
        scope_public_badge: "Công khai",
        // Upload Modal
        upload_modal_title: "Tải tài liệu mới",
        dropzone_text: "Kéo thả tệp vào đây hoặc <span class=\"highlight\">Bấm để chọn tệp từ máy tính</span>",
        dropzone_sub: "Hỗ trợ: PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), Ảnh scan (.png, .jpg)",
        label_doc_name: "Tên tài liệu hiển thị",
        placeholder_doc_name: "Tự động điền khi chọn tệp hoặc nhập tùy chỉnh...",
        label_upload_date: "Ngày tải lên",
        label_category: "Phân loại danh mục",
        placeholder_category: "Ví dụ: Quy chế, Hướng dẫn sử dụng, Kế toán",
        label_scope: "Phạm vi phân quyền",
        scope_public: "Công khai",
        scope_restricted: "Phân theo vai trò (Admin / Elite / Officer)",
        label_roles_select: "Vai trò được phép truy cập tài liệu này:",
        label_ocr: "Bật OCR trích xuất chữ trong ảnh scan (Tesseract)",
        label_vision: "Bật Vision AI phân tích biểu đồ & giao diện (Qwen-VL)",
        submit_upload_btn: "Xác nhận nạp tài liệu",
        progress_ingesting: "Đang phân đoạn và nhúng Vector...",
        // Edit Modal
        edit_modal_title: "Chỉnh sửa tài liệu",
        save_changes_btn: "Lưu thay đổi",
        // Citations & Actions
        citations_title: "Chi tiết trích dẫn nguồn",
        citations_label: "Trích dẫn:",
        copy_btn: "📋 Sao chép",
        copied_btn: "✓ Đã sao chép",
        retry_prompt_btn: "🔄 Thử lại",
        reasoning_title: "Quá trình suy luận (Reasoning Process)",
        // Feedback
        feedback_positive_btn: "👍 Thích",
        feedback_negative_btn: "👎 Chưa hài lòng",
        feedback_thank_you: "Cảm ơn bạn đã đóng góp phản hồi!",
        // Toasts & Dialogs
        toast_lang_switched: "Đã chuyển sang Tiếng Việt",
        toast_theme_switched: "Đã đổi giao diện",
        toast_role_switched: "Đã chuyển vai trò sang",
        toast_reasoning_mode: "Chế độ Suy luận sâu: Tự động đối chiếu đa tài liệu.",
        toast_need_files: "Vui lòng chọn ít nhất 1 tệp tài liệu để nạp!",
        toast_upload_success: "Tài liệu đã được phân đoạn & nhúng Vector thành công! 🚀",
        toast_edit_success: "Đã cập nhật thành công tài liệu! ✨",
        toast_retry_success: "Đã kích hoạt re-ingest cho tài liệu! 🔄",
        toast_delete_success: "Đã xóa tài liệu thành công khỏi cơ sở dữ liệu. 🗑️",
        confirm_delete_doc: "Bạn có chắc chắn muốn xóa vĩnh viễn tài liệu này và toàn bộ Vector Chunks liên quan?",
        confirm_delete_conv: "Bạn có chắc muốn xóa cuộc trò chuyện này?",
    },
    en: {
        page_title: "RAG Cosmic | Cosmic Knowledge AI Assistant",
        brand_name: "RAG",
        new_chat: "New Chat",
        manage_doc: "Manage Documents",
        vision_mode: "Vision Mode",
        role_admin: "Admin",
        role_elite: "Elite",
        role_officer: "Officer",
        lang_vi: "Tiếng Việt",
        lang_en: "English",
        pinned_header: "Pinned",
        pinned_sample_1: "Asset procurement & handover process",
        chats_header: "Chats & Tasks",
        loading_history: "Loading history...",
        no_history: "No conversations yet",
        greeting_morning: "Morning thoughts",
        greeting_afternoon: "Afternoon thoughts",
        greeting_evening: "Evening thoughts",
        input_placeholder: "How can I help you today?",
        mode_chat: "Chat",
        mode_reasoning: "Reasoning",
        model_quality: "High",
        engine_ready: "RAG Engine Ready",
        engine_offline: "Offline",
        drag_drop_hint: "Drop images here to upload",
        // Manage Modal
        manage_modal_title: "Knowledge Document Management",
        manage_modal_subtitle: "Documents loaded directly from database with RBAC access control",
        upload_doc_btn: "Upload Document",
        col_doc_name: "DOCUMENT NAME",
        col_upload_date: "UPLOAD DATE",
        col_access_scope: "ACCESS SCOPE",
        col_status: "STATUS",
        col_actions: "ACTIONS",
        loading_db: "Loading documents from database...",
        empty_docs: "No documents found. Click 'Upload Document' above to ingest new files.",
        action_edit: "Edit",
        action_retry: "Retry",
        action_delete: "Delete",
        scope_public_badge: "Public",
        // Upload Modal
        upload_modal_title: "Upload New Documents",
        dropzone_text: "Drag & drop files here or <span class=\"highlight\">Click to browse files</span>",
        dropzone_sub: "Supports: PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), Images (.png, .jpg)",
        label_doc_name: "Display Document Name",
        placeholder_doc_name: "Auto-filled when files are selected or custom name...",
        label_upload_date: "Upload Date",
        label_category: "Category",
        placeholder_category: "E.g., Guidelines, User Manuals, Accounting",
        label_scope: "Access Scope",
        scope_public: "Public",
        scope_restricted: "Role-based (Admin / Elite / Officer)",
        label_roles_select: "Roles allowed to access this document:",
        label_ocr: "Enable OCR text extraction for scanned images (Tesseract)",
        label_vision: "Enable Vision AI diagram & UI analysis (Qwen-VL)",
        submit_upload_btn: "Confirm & Ingest Documents",
        progress_ingesting: "Chunking and embedding vectors...",
        // Edit Modal
        edit_modal_title: "Edit Document",
        save_changes_btn: "Save Changes",
        // Citations & Actions
        citations_title: "Source Citation Details",
        citations_label: "Citations:",
        copy_btn: "📋 Copy",
        copied_btn: "✓ Copied",
        retry_prompt_btn: "🔄 Retry",
        reasoning_title: "Reasoning Process",
        // Feedback
        feedback_positive_btn: "👍 Helpful",
        feedback_negative_btn: "👎 Not helpful",
        feedback_thank_you: "Thank you for your feedback!",
        // Toasts & Dialogs
        toast_lang_switched: "Switched to English",
        toast_theme_switched: "Switched theme",
        toast_role_switched: "User role changed to",
        toast_reasoning_mode: "Reasoning Mode: Deep cross-document analysis enabled.",
        toast_need_files: "Please select at least 1 document file to upload!",
        toast_upload_success: "Documents parsed and vector embeddings stored! 🚀",
        toast_edit_success: "Document updated successfully! ✨",
        toast_retry_success: "Re-ingestion queued for document! 🔄",
        toast_delete_success: "Document deleted from database. 🗑️",
        confirm_delete_doc: "Are you sure you want to permanently delete this document and its vector chunks?",
        confirm_delete_conv: "Are you sure you want to delete this conversation?",
    }
};

let _currentLang = localStorage.getItem('rag_language') || 'vi';

export function getCurrentLanguage() {
    return _currentLang;
}

export function getT(key, lang = _currentLang) {
    const dict = I18N[lang] || I18N.vi;
    return dict[key] || key;
}

export function setLanguage(lang) {
    _currentLang = (lang === 'en') ? 'en' : 'vi';
    localStorage.setItem('rag_language', _currentLang);
    applyTranslations(_currentLang);
}

export function applyTranslations(lang = _currentLang) {
    const dict = I18N[lang] || I18N.vi;
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (dict[key]) {
            if (el.tagName === 'INPUT' && el.getAttribute('placeholder')) {
                el.placeholder = dict[key];
            } else {
                el.textContent = dict[key];
            }
        }
    });

    const pageTitle = document.getElementById('pageTitle');
    if (pageTitle && dict.page_title) {
        pageTitle.textContent = dict.page_title;
    }
}
