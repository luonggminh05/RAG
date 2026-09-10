/**
 * RAG COSMIC - Vision Module (Screenshots, Image attachments, Drag & Drop & Compression)
 */

export class VisionHandler {
    constructor({ attachBtn, imageFileInput, imagePreviewStrip, dragDropOverlay, onImagesChanged, showToast }) {
        this.attachBtn = attachBtn;
        this.imageFileInput = imageFileInput;
        this.imagePreviewStrip = imagePreviewStrip;
        this.dragDropOverlay = dragDropOverlay || document.getElementById('dragDropOverlay');
        this.onImagesChanged = onImagesChanged || (() => {});
        this.showToast = showToast || console.log;
        this.attachedImages = [];
        this.isEnabled = true;
        this._dragCounter = 0;

        this._init();
    }

    _init() {
        this.imageFileInput?.addEventListener('change', (e) => this.handleImageFilesSelect(e));
        window.addEventListener('paste', (e) => this.handleClipboardPaste(e));
        this._initDragAndDrop();
    }

    _initDragAndDrop() {
        window.addEventListener('dragenter', (e) => {
            if (!this.isEnabled) return;
            if (e.dataTransfer && Array.from(e.dataTransfer.types).includes('Files')) {
                this._dragCounter++;
                this.dragDropOverlay?.classList.add('active');
            }
        });

        window.addEventListener('dragover', (e) => {
            if (!this.isEnabled) return;
            e.preventDefault();
        });

        window.addEventListener('dragleave', (e) => {
            if (!this.isEnabled) return;
            this._dragCounter--;
            if (this._dragCounter <= 0) {
                this._dragCounter = 0;
                this.dragDropOverlay?.classList.remove('active');
            }
        });

        window.addEventListener('drop', (e) => {
            if (!this.isEnabled) return;
            e.preventDefault();
            this._dragCounter = 0;
            this.dragDropOverlay?.classList.remove('active');

            const files = Array.from(e.dataTransfer?.files || []).filter(f => f.type.startsWith('image/'));
            if (files.length > 0) {
                this.processFiles(files);
            }
        });
    }

    setEnabled(enabled) {
        this.isEnabled = enabled;
        if (!this.isEnabled) {
            this.clearImages();
            this.attachBtn?.classList.add('disabled');
        } else {
            this.attachBtn?.classList.remove('disabled');
        }
    }

    getImages() {
        return [...this.attachedImages];
    }

    clearImages() {
        this.attachedImages = [];
        this.renderPreviewStrip();
        this.onImagesChanged(this.attachedImages);
    }

    handleImageFilesSelect(e) {
        if (!this.isEnabled) return;
        this.processFiles(Array.from(e.target.files || []));
        e.target.value = '';
    }

    handleClipboardPaste(e) {
        if (!this.isEnabled) return;
        const items = (e.clipboardData || e.originalEvent?.clipboardData)?.items || [];
        const imageFiles = [];
        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                const file = items[i].getAsFile();
                if (file) imageFiles.push(file);
            }
        }
        if (imageFiles.length > 0) {
            e.preventDefault();
            this.processFiles(imageFiles);
        }
    }

    /**
     * Tự động nén ảnh client-side qua HTML5 Canvas để tối ưu hóa latency và bộ nhớ.
     */
    async compressImage(file, maxDimension = 1600, quality = 0.85) {
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = (e) => {
                const img = new Image();
                img.onload = () => {
                    let width = img.width;
                    let height = img.height;

                    // Resize if exceeds max dimension
                    if (width > maxDimension || height > maxDimension) {
                        if (width > height) {
                            height = Math.round((height * maxDimension) / width);
                            width = maxDimension;
                        } else {
                            width = Math.round((width * maxDimension) / height);
                            height = maxDimension;
                        }
                    }

                    const canvas = document.createElement('canvas');
                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, width, height);

                    const compressedBase64 = canvas.toDataURL('image/jpeg', quality);
                    resolve(compressedBase64);
                };
                img.onerror = () => resolve(e.target.result); // Fallback original
                img.src = e.target.result;
            };
            reader.onerror = () => resolve(null);
            reader.readAsDataURL(file);
        });
    }

    async processFiles(files) {
        const validFiles = files.filter(f => f.type.startsWith('image/'));
        if (validFiles.length === 0) return;

        if (this.attachedImages.length + validFiles.length > 3) {
            this.showToast('Hệ thống chỉ hỗ trợ tối đa 3 ảnh cùng lúc!');
            return;
        }

        for (const file of validFiles) {
            try {
                const compressedBase64 = await this.compressImage(file);
                if (compressedBase64) {
                    this.attachedImages.push({
                        fileName: file.name,
                        contentType: 'image/jpeg',
                        base64: compressedBase64,
                    });
                }
            } catch (err) {
                console.warn('[VISION] Failed to compress image, using raw:', err);
            }
        }

        this.renderPreviewStrip();
        this.onImagesChanged(this.attachedImages);
    }

    renderPreviewStrip() {
        if (!this.imagePreviewStrip) return;
        this.imagePreviewStrip.innerHTML = '';
        this.attachedImages.forEach((img, idx) => {
            const card = document.createElement('div');
            card.className = 'preview-thumb-card';
            card.innerHTML = `
                <img src="${img.base64}" alt="Thumb">
                <button class="remove-thumb-btn" data-index="${idx}" title="Xóa ảnh">×</button>
            `;
            card.querySelector('.remove-thumb-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                this.attachedImages.splice(idx, 1);
                this.renderPreviewStrip();
                this.onImagesChanged(this.attachedImages);
            });
            this.imagePreviewStrip.appendChild(card);
        });
    }
}
