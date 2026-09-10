/**
 * RAG COSMIC - Feedback Module (Like / Dislike & User Feedback API)
 */

export class FeedbackHandler {
    static async submitFeedback(messageId, rating, comment = null) {
        if (!messageId) return { success: false, error: 'No message ID' };
        try {
            const res = await fetch(`/api/v1/chat/messages/${messageId}/feedback`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rating, comment }),
            });
            if (res.ok) {
                return { success: true, data: await res.json() };
            }
            // Fallback alternative route
            const fallbackRes = await fetch(`/api/v1/chat/${messageId}/feedback`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rating, comment }),
            });
            if (fallbackRes.ok) {
                return { success: true, data: await fallbackRes.json() };
            }
            return { success: false, status: res.status };
        } catch (err) {
            console.error('[FEEDBACK ERROR]', err);
            return { success: false, error: err.message };
        }
    }

    static setupFeedbackButtons(actionsBar, messageId, showToast, t) {
        const likeBtn = actionsBar.querySelector('#likeMsgBtn') || actionsBar.querySelector('.like-msg-btn');
        const dislikeBtn = actionsBar.querySelector('#dislikeMsgBtn') || actionsBar.querySelector('.dislike-msg-btn');

        if (likeBtn) {
            likeBtn.addEventListener('click', async () => {
                const isAlreadyLiked = likeBtn.classList.contains('active-like');
                if (isAlreadyLiked) {
                    likeBtn.classList.remove('active-like');
                    return;
                }
                likeBtn.classList.add('active-like');
                dislikeBtn?.classList.remove('active-dislike');

                if (messageId) {
                    const res = await FeedbackHandler.submitFeedback(messageId, 'positive');
                    if (res.success && showToast && t) {
                        showToast(t('feedback_thank_you') || 'Cảm ơn bạn đã đóng góp phản hồi!');
                    }
                }
            });
        }

        if (dislikeBtn) {
            dislikeBtn.addEventListener('click', async () => {
                const isAlreadyDisliked = dislikeBtn.classList.contains('active-dislike');
                if (isAlreadyDisliked) {
                    dislikeBtn.classList.remove('active-dislike');
                    return;
                }
                dislikeBtn.classList.add('active-dislike');
                likeBtn?.classList.remove('active-like');

                if (messageId) {
                    const res = await FeedbackHandler.submitFeedback(messageId, 'negative');
                    if (res.success && showToast && t) {
                        showToast(t('feedback_thank_you') || 'Cảm ơn bạn đã đóng góp phản hồi!');
                    }
                }
            });
        }
    }
}
