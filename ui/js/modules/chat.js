/**
 * RAG COSMIC - Chat Module (SSE Streaming, Markdown, Think Tags, Citations & Retry)
 */

import { getT } from './i18n.js';
import { FeedbackHandler } from './feedback.js';

export class ChatManager {
    constructor({ elements, visionHandler, getRole, getModel, showToast }) {
        this.elements = elements;
        this.visionHandler = visionHandler;
        this.getRole = getRole;
        this.getModel = getModel;
        this.showToast = showToast;

        this.currentConversationId = localStorage.getItem('cosmic_rag_conv_id') || null;
        this.isStreaming = false;

        this._init();
    }

    _init() {
        this.elements.newChatBtn?.addEventListener('click', () => this.startNewConversation());

        this.elements.chatInput?.addEventListener('input', () => this.adjustTextareaHeight());
        this.elements.chatInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        this.elements.sendBtn?.addEventListener('click', () => this.sendMessage());

        // Pinned prompts
        document.querySelectorAll('.pinned-sample').forEach(item => {
            item.addEventListener('click', () => {
                const prompt = item.getAttribute('data-prompt');
                if (prompt) {
                    this.elements.chatInput.value = prompt;
                    this.adjustTextareaHeight();
                    this.sendMessage();
                }
            });
        });

        // Close Citation Modal
        this.elements.closeCitationModalBtn?.addEventListener('click', () => {
            if (this.elements.citationModal) {
                this.elements.citationModal.style.display = 'none';
            }
        });

        // Floating Scroll-to-Bottom Button
        this._initScrollBottomButton();
    }

    _initScrollBottomButton() {
        const updateScrollBtn = () => {
            if (!this.elements.chatContainer || !this.elements.scrollBottomBtn) return;
            const { scrollTop, scrollHeight, clientHeight } = this.elements.chatContainer;
            const isNearBottom = scrollHeight - scrollTop - clientHeight < 140;
            if (!isNearBottom) {
                this.elements.scrollBottomBtn.classList.add('visible');
            } else {
                this.elements.scrollBottomBtn.classList.remove('visible');
                this.elements.scrollUnreadDot?.classList.remove('active');
            }
        };

        this.elements.chatContainer?.addEventListener('scroll', updateScrollBtn);
        this.elements.scrollBottomBtn?.addEventListener('click', () => {
            this.elements.chatContainer?.scrollTo({ top: this.elements.chatContainer.scrollHeight, behavior: 'smooth' });
            this.elements.scrollUnreadDot?.classList.remove('active');
        });
    }

    startNewConversation() {
        this.currentConversationId = null;
        localStorage.removeItem('cosmic_rag_conv_id');
        if (this.elements.messageList) this.elements.messageList.innerHTML = '';
        if (this.elements.welcomeHero) this.elements.welcomeHero.style.display = 'block';
        if (this.elements.chatInput) {
            this.elements.chatInput.value = '';
            this.elements.chatInput.focus();
        }
        this.adjustTextareaHeight();
        this.loadConversations();
    }

    async loadConversations() {
        try {
            const res = await fetch('/api/v1/chat/conversations');
            if (res.ok) {
                const data = await res.json();
                const convs = Array.isArray(data) ? data : (data.conversations || []);
                this.renderConversationsList(convs);
            }
        } catch (err) {
            console.warn('[LOAD CONVERSATIONS WARNING]', err);
        }
    }

    renderConversationsList(conversations) {
        if (!this.elements.conversationsList) return;
        this.elements.conversationsList.innerHTML = '';

        if (!conversations || conversations.length === 0) {
            this.elements.conversationsList.innerHTML = `<div class="empty-nav-state">${getT('no_history')}</div>`;
            return;
        }

        conversations.forEach(c => {
            const item = document.createElement('div');
            item.className = `conv-history-item ${String(c.id) === String(this.currentConversationId) ? 'active' : ''}`;
            item.setAttribute('data-id', c.id);

            const titleText = c.title || 'Cuộc trò chuyện mới';
            item.innerHTML = `
                <span class="conv-item-title">${this.escapeHtml(titleText)}</span>
                <button class="conv-delete-btn" title="${getT('confirm_delete_conv')}">×</button>
            `;

            item.addEventListener('click', (e) => {
                if (e.target.classList.contains('conv-delete-btn')) return;
                this.selectConversation(c.id);
            });

            item.querySelector('.conv-delete-btn').addEventListener('click', async (e) => {
                e.stopPropagation();
                if (confirm(getT('confirm_delete_conv'))) {
                    await this.deleteConversation(c.id);
                }
            });

            this.elements.conversationsList.appendChild(item);
        });
    }

    async selectConversation(convId) {
        this.currentConversationId = String(convId);
        localStorage.setItem('cosmic_rag_conv_id', this.currentConversationId);
        if (this.elements.welcomeHero) this.elements.welcomeHero.style.display = 'none';

        document.querySelectorAll('.conv-history-item').forEach(el => {
            el.classList.toggle('active', el.getAttribute('data-id') === String(convId));
        });

        await this.loadConversationMessages(convId);
    }

    async deleteConversation(convId) {
        try {
            await fetch(`/api/v1/chat/conversations/${convId}`, { method: 'DELETE' });
            if (String(this.currentConversationId) === String(convId)) {
                this.startNewConversation();
            } else {
                this.loadConversations();
            }
        } catch (err) {
            console.error('[DELETE CONVERSATION ERROR]', err);
        }
    }

    async loadConversationMessages(convId) {
        if (!this.elements.messageList) return;
        this.elements.messageList.innerHTML = '';
        try {
            const res = await fetch(`/api/v1/chat/conversations/${convId}/messages`);
            if (res.ok) {
                const messages = await res.json();
                if (messages && messages.length > 0) {
                    if (this.elements.welcomeHero) this.elements.welcomeHero.style.display = 'none';
                    messages.forEach(m => {
                        if (m.role === 'user') {
                            this.appendUserMessage(m.content);
                        } else if (m.role === 'assistant') {
                            this.appendExistingAssistantMessage(m.content, m.id);
                        }
                    });
                    this.scrollToBottom();
                }
            }
        } catch (err) {
            console.error('[LOAD MESSAGES ERROR]', err);
        }
    }

    appendUserMessage(text, images = []) {
        if (!this.elements.messageList) return;
        const msgDiv = document.createElement('div');
        msgDiv.className = 'chat-message user';

        let imagesHtml = '';
        if (images && images.length > 0) {
            imagesHtml = `<div class="message-attached-images">` +
                images.map(img => `<img src="${img.base64}" class="attached-thumb-img" alt="Attached">`).join('') +
                `</div>`;
        }

        msgDiv.innerHTML = `
            <div class="message-content-wrapper">
                ${imagesHtml}
                <div class="user-bubble">${this.escapeHtml(text)}</div>
            </div>
            <div class="chat-avatar user">U</div>
        `;
        this.elements.messageList.appendChild(msgDiv);
        this.scrollToBottom();
    }

    appendExistingAssistantMessage(content, messageId = null) {
        if (!this.elements.messageList) return;
        const { msgElement, contentElement, actionsBar } = this.createAssistantMessageElement();
        this.elements.messageList.appendChild(msgElement);

        this.renderMarkdown(contentElement, content, false);
        this.setupCodeCopyButtons(contentElement);
        this.renderMessageActions(actionsBar, content, '', messageId);
    }

    createAssistantMessageElement() {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'chat-message assistant';

        msgDiv.innerHTML = `
            <div class="chat-avatar assistant">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 1L13.8 8.2L21 6.5L16.2 12L21 17.5L13.8 15.8L12 23L10.2 15.8L3 17.5L7.8 12L3 6.5L10.2 8.2L12 1Z" />
                </svg>
            </div>
            <div class="message-content-wrapper" style="width: 100%;">
                <div class="thinking-accordion" style="display: none;">
                    <div class="thinking-accordion-header">
                        <div class="thinking-header-title">
                            <span class="thinking-pulse-icon"></span>
                            <span>${getT('reasoning_title')}</span>
                            <span class="wave-pulse-loading"><span></span><span></span><span></span></span>
                        </div>
                        <span class="thinking-chevron">▾</span>
                    </div>
                    <div class="thinking-accordion-content"></div>
                </div>
                <div class="assistant-bubble markdown-body"></div>
                <div class="message-actions-bar" style="display: none;"></div>
            </div>
        `;

        const thinkingAccordion = msgDiv.querySelector('.thinking-accordion');
        const thinkingHeader = msgDiv.querySelector('.thinking-accordion-header');
        const thinkingContent = msgDiv.querySelector('.thinking-accordion-content');
        const contentElement = msgDiv.querySelector('.assistant-bubble');
        const actionsBar = msgDiv.querySelector('.message-actions-bar');

        thinkingHeader?.addEventListener('click', () => {
            thinkingAccordion.classList.toggle('collapsed');
        });

        return {
            msgElement: msgDiv,
            thinkingAccordion,
            thinkingContent,
            contentElement,
            actionsBar,
        };
    }

    async sendMessage(overrideText = null, options = { isRetry: false, retryMessageId: null }) {
        if (this.isStreaming) return;

        const text = overrideText !== null ? overrideText : (this.elements.chatInput?.value || '').trim();
        const attachedImages = this.visionHandler ? this.visionHandler.getImages() : [];
        const hasImages = attachedImages.length > 0;

        if (!text && !hasImages) return;

        if (this.elements.welcomeHero) this.elements.welcomeHero.style.display = 'none';

        if (!options.isRetry) {
            this.appendUserMessage(text, attachedImages);
        }

        const currentMessageText = text;
        const currentImages = [...attachedImages];

        if (this.elements.chatInput) this.elements.chatInput.value = '';
        this.adjustTextareaHeight();
        if (this.visionHandler) this.visionHandler.clearImages();

        const {
            msgElement,
            thinkingAccordion,
            thinkingContent,
            contentElement,
            actionsBar
        } = this.createAssistantMessageElement();

        this.elements.messageList?.appendChild(msgElement);
        this.scrollToBottom();

        this.isStreaming = true;
        if (this.elements.sendBtn) this.elements.sendBtn.disabled = true;

        const payload = {
            message: currentMessageText,
            images: currentImages,
            conversation_id: this.currentConversationId ? String(this.currentConversationId) : null,
            model: this.getModel ? this.getModel() : 'qwen2.5vl:7b',
            user_roles: this.getRole ? this.getRole() : 'Admin',
            enable_vision: this.visionHandler ? this.visionHandler.isEnabled : true,
            is_retry: Boolean(options.isRetry),
            retry_message_id: options.retryMessageId || null,
        };

        try {
            const response = await fetch('/api/v1/chat/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                    'X-User-Roles': this.getRole ? this.getRole() : 'Admin',
                },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                if (response.status === 429) {
                    throw new Error('Bạn đã gửi quá nhiều yêu cầu (Rate Limit Exceeded). Vui lòng đợi trong giây lát!');
                }
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let rawAssistantAnswer = '';
            let rawThinkingText = '';
            let currentEvent = 'token';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i].trim();
                    if (!line) continue;

                    if (line.startsWith('event:')) {
                        currentEvent = line.substring(6).trim();
                    } else if (line.startsWith('data:')) {
                        const dataStr = line.substring(5).trim();
                        this.handleSSEData(currentEvent, dataStr, {
                            onToken: (txt) => {
                                rawAssistantAnswer += txt;
                                this.renderMarkdown(contentElement, rawAssistantAnswer, true);
                                this.scrollToBottom();
                            },
                            onThinking: (thTxt) => {
                                rawThinkingText += thTxt;
                                thinkingAccordion.style.display = 'block';
                                thinkingContent.textContent = rawThinkingText;
                                this.scrollToBottom();
                            },
                            onConversationId: (convId) => {
                                if (convId && convId !== this.currentConversationId) {
                                    this.currentConversationId = String(convId);
                                    localStorage.setItem('cosmic_rag_conv_id', String(convId));
                                    this.loadConversations();
                                }
                            },
                            onCitations: (citations) => {
                                this.renderCitations(msgElement, citations);
                            },
                        });
                    }
                }
            }

            this.renderMarkdown(contentElement, rawAssistantAnswer, false);
            this.setupCodeCopyButtons(contentElement);
            this.renderMessageActions(actionsBar, rawAssistantAnswer, currentMessageText);
            this.scrollToBottom();

            // Refresh conversation list to pick up updated titles
            this.loadConversations();

        } catch (err) {
            console.error('[STREAM ERROR]', err);
            const errorMsg = `❌ **Lỗi**: ${this.escapeHtml(err.message || 'Không thể kết nối đến API backend.')}`;
            this.renderMarkdown(contentElement, errorMsg, false);
            this.setupCodeCopyButtons(contentElement);
            this.renderMessageActions(actionsBar, errorMsg, currentMessageText);
            this.scrollToBottom();
        } finally {
            this.isStreaming = false;
            if (this.elements.sendBtn) this.elements.sendBtn.disabled = false;
            this.elements.chatInput?.focus();
        }
    }

    handleSSEData(event, dataStr, callbacks) {
        try {
            const parsed = JSON.parse(dataStr);
            if (event === 'thinking' || parsed.thinking) {
                callbacks.onThinking(parsed.thinking || parsed.text || parsed.content || '');
            } else if (event === 'citations' || parsed.citations) {
                callbacks.onCitations(parsed.citations || []);
            } else if (event === 'meta' || parsed.conversation_id) {
                if (parsed.conversation_id) callbacks.onConversationId(parsed.conversation_id);
            } else {
                const token = parsed.text !== undefined ? parsed.text : (parsed.token !== undefined ? parsed.token : (parsed.content || ''));
                if (token) callbacks.onToken(token);
            }
        } catch {
            if (event === 'thinking') callbacks.onThinking(dataStr);
            else callbacks.onToken(dataStr);
        }
    }

    renderMarkdown(element, markdownText, isStreaming = false) {
        if (!element) return;
        if (window.MarkdownHelper) {
            element.innerHTML = window.MarkdownHelper.render(markdownText, isStreaming);
        } else {
            element.textContent = markdownText;
        }
    }

    setupCodeCopyButtons(container) {
        container.querySelectorAll('pre').forEach(pre => {
            if (pre.querySelector('.code-copy-btn')) return;
            const btn = document.createElement('button');
            btn.className = 'action-icon-btn code-copy-btn';
            btn.style.position = 'absolute';
            btn.style.top = '6px';
            btn.style.right = '6px';
            btn.innerHTML = getT('copy_btn');
            btn.addEventListener('click', () => {
                const code = pre.querySelector('code')?.innerText || pre.innerText;
                navigator.clipboard.writeText(code);
                btn.innerHTML = getT('copied_btn');
                setTimeout(() => (btn.innerHTML = getT('copy_btn')), 2000);
            });
            pre.appendChild(btn);
        });
    }

    renderCitations(msgElement, citations) {
        if (!citations || citations.length === 0) return;
        const wrapper = document.createElement('div');
        wrapper.className = 'citations-wrapper';
        wrapper.innerHTML = `<span class="citations-label">${getT('citations_label')}</span>`;

        citations.forEach((c, idx) => {
            const pill = document.createElement('span');
            pill.className = 'citation-pill-tag';
            const docName = c.document_name || c.source || `Doc ${idx + 1}`;
            const pageInfo = c.page ? ` (P.${c.page})` : '';
            pill.innerHTML = `📄 ${this.escapeHtml(docName)}${pageInfo}`;
            pill.addEventListener('click', () => {
                if (this.elements.citationModalTitle) this.elements.citationModalTitle.textContent = getT('citations_title');
                if (this.elements.citationModalSource) this.elements.citationModalSource.textContent = docName;
                if (this.elements.citationModalBody) this.elements.citationModalBody.textContent = c.text || c.content || '';
                if (this.elements.citationModal) this.elements.citationModal.style.display = 'flex';
            });
            wrapper.appendChild(pill);
        });

        const contentWrap = msgElement.querySelector('.message-content-wrapper');
        const actionsBar = msgElement.querySelector('.message-actions-bar');
        if (contentWrap && actionsBar) {
            contentWrap.insertBefore(wrapper, actionsBar);
        }
    }

    renderMessageActions(actionsBar, answerText, userPrompt, messageId = null) {
        actionsBar.style.display = 'flex';
        actionsBar.innerHTML = `
            <button class="action-icon-btn copy-btn" title="${getT('copy_btn')}">
                <span>${getT('copy_btn')}</span>
            </button>
            <button class="action-icon-btn retry-btn" title="${getT('retry_prompt_btn')}">
                <span>${getT('retry_prompt_btn')}</span>
            </button>
            <button class="action-icon-btn like-msg-btn" id="likeMsgBtn" title="${getT('feedback_positive_btn')}">👍</button>
            <button class="action-icon-btn dislike-msg-btn" id="dislikeMsgBtn" title="${getT('feedback_negative_btn')}">👎</button>
        `;

        actionsBar.querySelector('.copy-btn')?.addEventListener('click', (e) => {
            navigator.clipboard.writeText(answerText);
            const btn = e.currentTarget;
            btn.innerHTML = `<span>${getT('copied_btn')}</span>`;
            setTimeout(() => { btn.innerHTML = `<span>${getT('copy_btn')}</span>`; }, 2000);
        });

        actionsBar.querySelector('.retry-btn')?.addEventListener('click', () => {
            if (userPrompt) {
                this.sendMessage(userPrompt, { isRetry: true, retryMessageId: messageId });
            }
        });

        // Setup Like / Dislike (P4.3)
        FeedbackHandler.setupFeedbackButtons(actionsBar, messageId, this.showToast, getT);
    }

    adjustTextareaHeight() {
        if (!this.elements.chatInput) return;
        this.elements.chatInput.style.height = 'auto';
        const newHeight = Math.min(this.elements.chatInput.scrollHeight, 180);
        this.elements.chatInput.style.height = `${newHeight}px`;
    }

    scrollToBottom() {
        if (!this.elements.chatContainer) return;
        const { scrollTop, scrollHeight, clientHeight } = this.elements.chatContainer;
        const isNearBottom = scrollHeight - scrollTop - clientHeight < 150;

        if (isNearBottom || !this.isStreaming) {
            this.elements.chatContainer.scrollTop = scrollHeight;
            this.elements.scrollUnreadDot?.classList.remove('active');
        } else {
            // User scrolled up to inspect previous answers, show unread indicator on floating btn
            this.elements.scrollBottomBtn?.classList.add('visible');
            this.elements.scrollUnreadDot?.classList.add('active');
        }
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
