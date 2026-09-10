/**
 * RAG COSMIC - Resizer Module (8-Directional Multi-Edge Drag Resize for Modals)
 */

export function initModalMultiEdgeResizing() {
    document.querySelectorAll('.resizable-modal').forEach(modal => {
        const handles = modal.querySelectorAll('.edge-resize-handle');
        handles.forEach(handle => {
            handle.addEventListener('mousedown', (e) => {
                e.preventDefault();
                e.stopPropagation();

                const startX = e.clientX;
                const startY = e.clientY;
                const rect = modal.getBoundingClientRect();
                const startWidth = rect.width;
                const startHeight = rect.height;

                const isTop = handle.classList.contains('handle-top') || handle.classList.contains('handle-top-left') || handle.classList.contains('handle-top-right');
                const isBottom = handle.classList.contains('handle-bottom') || handle.classList.contains('handle-bottom-left') || handle.classList.contains('handle-bottom-right');
                const isLeft = handle.classList.contains('handle-left') || handle.classList.contains('handle-top-left') || handle.classList.contains('handle-bottom-left');
                const isRight = handle.classList.contains('handle-right') || handle.classList.contains('handle-top-right') || handle.classList.contains('handle-bottom-right');

                function onMouseMove(moveEvent) {
                    const dx = moveEvent.clientX - startX;
                    const dy = moveEvent.clientY - startY;

                    let newWidth = startWidth;
                    let newHeight = startHeight;

                    if (isRight) newWidth = startWidth + dx * 2;
                    if (isLeft) newWidth = startWidth - dx * 2;
                    if (isBottom) newHeight = startHeight + dy * 2;
                    if (isTop) newHeight = startHeight - dy * 2;

                    // Constraints
                    const minW = 480;
                    const maxW = window.innerWidth * 0.96;
                    const minH = 360;
                    const maxH = window.innerHeight * 0.96;

                    if (newWidth >= minW && newWidth <= maxW) {
                        modal.style.width = `${newWidth}px`;
                    }
                    if (newHeight >= minH && newHeight <= maxH) {
                        modal.style.height = `${newHeight}px`;
                    }
                }

                function onMouseUp() {
                    window.removeEventListener('mousemove', onMouseMove);
                    window.removeEventListener('mouseup', onMouseUp);
                }

                window.addEventListener('mousemove', onMouseMove);
                window.addEventListener('mouseup', onMouseUp);
            });
        });
    });
}
