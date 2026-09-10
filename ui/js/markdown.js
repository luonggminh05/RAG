/**
 * COSMIC GALAXY RAG - MARKDOWN HELPER UTILITIES
 * Sanitization, GFM tables, code block highlighting, and streaming cursor.
 */

class MarkdownHelper {
    static sanitize(text) {
        if (!text) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    static render(rawMarkdown, isStreaming = false) {
        let html = '';
        if (window.marked) {
            try {
                if (!window._markedConfigured) {
                    window.marked.setOptions({
                        highlight: function(code, lang) {
                            if (window.hljs && window.hljs.getLanguage(lang)) {
                                return window.hljs.highlight(code, { language: lang }).value;
                            }
                            return window.hljs ? window.hljs.highlightAuto(code).value : code;
                        },
                        breaks: true,
                        gfm: true,
                    });
                    window._markedConfigured = true;
                }
                html = window.marked.parse(rawMarkdown || '');
            } catch {
                html = this.sanitize(rawMarkdown).replace(/\n/g, '<br>');
            }
        } else {
            html = this.sanitize(rawMarkdown).replace(/\n/g, '<br>');
        }

        if (isStreaming) {
            html += '<span class="streaming-cursor"></span>';
        }
        return html;
    }
}

window.MarkdownHelper = MarkdownHelper;
