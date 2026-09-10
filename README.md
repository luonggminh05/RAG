# 🌌 Gemini RAG AI - Multimodal Enterprise Knowledge Assistant

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=Python&logoColor=white)](https://www.python.org/)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20AI-black.svg?style=flat&logo=ollama&logoColor=white)](https://ollama.com/)
[![TEI](https://img.shields.io/badge/HuggingFace-TEI%20bge--m3-orange.svg?style=flat)](https://github.com/huggingface/text-embeddings-inference)
[![SQL Server](https://img.shields.io/badge/SQL%20Server-Vector%201024-CC292B.svg?style=flat&logo=microsoftsqlserver&logoColor=white)](https://www.microsoft.com/sql-server)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

> **Gemini RAG AI** là giải pháp Trợ lý AI hỏi đáp tri thức doanh nghiệp độc lập (Standalone), hỗ trợ **Đa phương thức (Multimodal Vision & Text)**, tìm kiếm lai **Hybrid Search (Vector + Full-Text Search + RRF)** có **Phân quyền vai trò (RBAC)**, tích hợp sẵn giao diện Web phong cách **Google Gemini** thời gian thực (SSE Stream).

---

## 🌟 Tính Năng Nổi Bật

### 1. 🔄 Lựa Chọn Mô Hình AI Linh Hoạt (Dynamic Model Switcher)

Hệ thống cho phép người dùng chuyển đổi tức thì giữa các dòng mô hình AI hàng đầu chạy trên Ollama / vLLM:

- ⚡ **Qwen 2.5 3B (`qwen2.5:3b`)**: Phản hồi siêu nhanh, tối ưu cho hỏi đáp văn bản quy trình và tác vụ nhẹ.
- 👁️ **Qwen 2.5-VL 7B (`qwen2.5vl:7b`)**: Đa phương thức, hiểu sâu văn bản kèm ảnh chụp màn hình, biểu đồ và giao diện phần mềm.
- 🧠 **DeepSeek-R1 7B (`deepseek-r1:7b`)**: Suy luận sâu với chuỗi tư duy (Chain-of-Thought), tự động bóc tách khối suy luận `<think>` trên UI.
- 🤖 **Llama 3.2 3B (`llama3.2:3b`)**: Trợ lý tổng quát đa năng, phản hồi ngắn gọn và chính xác.

### 2. 📸 Chế Độ Đọc Ảnh & Vision Mode (Multimodal)

- **Công tắc bật/tắt Vision Mode**: Người dùng có thể chủ động bật hoặc tắt phân tích ảnh đính kèm theo từng lượt chat.
- **Tự động dán ảnh từ Clipboard (`Ctrl + V`)**: Dễ dàng chụp màn hình lỗi bằng Snipping Tool và paste trực tiếp vào khung chat.
- **Tích hợp OCR (Tesseract) + Qwen Vision**: Trích xuất chính xác nhãn nút bấm, bảng biểu, trường dữ liệu và thông báo lỗi.

### 3. 🎯 Tìm Kiếm Lai & Phân Quyền (Hybrid Search & RBAC)

- **Vector Search 1024 Dimensions** sử dụng mô hình Embedding đa ngữ `BAAI/bge-m3` tối ưu qua **HuggingFace Text Embeddings Inference (TEI)**.
- **Full-Text Search (FTS)** trên Microsoft SQL Server, kết hợp thuật toán xếp hạng tương hỗ **Reciprocal Rank Fusion (RRF)**.
- **Phân quyền truy cập tài liệu (RBAC)**: Chỉ trả về ngữ cảnh và trích dẫn tài liệu mà người dùng được cấp quyền truy cập.

### 4. 💻 Giao Diện Web Google Gemini Độc Lập (`ui/`)

- Thiết kế chuẩn **Google Gemini Dark Theme** sang trọng, hiệu ứng kính mờ (Glassmorphism), gradient thương hiệu Gemini.
- **Streaming theo thời gian thực (Server-Sent Events - SSE)** mượt mà token-by-token.
- **Khối trích dẫn nguồn (Citations View)** hiển thị chính xác tên file, số trang/slide tham khảo.
- **Modal Quản lý Kho tri thức (Knowledge Base)**: Kéo thả nạp tài liệu (PDF, Word, Excel, PowerPoint, Ảnh), theo dõi thanh tiến trình Ingestion thời gian thực và quản lý xóa tài liệu.

---

## 🏗️ Kiến Trúc Hệ Thống (DDD Clean Architecture)

```
Rag/
├── app/                                 # FastAPI Backend Service (Clean Architecture)
│   ├── ai/                              # Vision OCR, Chunking, Guardrails, Hybrid Retrieval
│   │   ├── guardrails/                  # Bộ lọc Input & Output an toàn dữ liệu
│   │   ├── rag/                         # Embedding (TEI), Ingestion, Chunker, RRF Retriever
│   │   └── vision/                      # Tesseract OCR & Qwen-VL Screenshot Captioner
│   ├── core/                            # Config (Models catalog, Vision switch), Database ORM, Auth Middleware
│   ├── modules/
│   │   ├── chat/                        # Chat Service (Dynamic model, SSE Queue stream, Title generation)
│   │   ├── document/                    # Document Ingestion Pipeline & Hybrid Search
│   │   └── health/                      # Health check endpoints
│   ├── routers/                         # FastAPI Route Registration
│   ├── lifespan.py                      # Lifecycle Context Manager
│   └── main.py                          # FastAPI App & Phục vụ Web UI tại "/"
│
├── ui/                                  # Giao diện Web Standalone phong cách Google Gemini
│   ├── index.html                       # HTML5 Layout (Sidebar, Chat Area, Knowledge Base Modal)
│   ├── css/
│   │   └── style.css                    # Design System Gemini (Dark mode, Animations, Glassmorphism)
│   └── js/
│       ├── app.js                       # Logic SSE Stream, Model Switcher, Clipboard Paste, Upload
│       └── markdown.js                  # Markdown & Code syntax renderer
│
├── database/
│   └── setup.sql                        # Script SQL Standalone khởi tạo toàn bộ CSDL RagVectorDb
│
├── configs/
│   ├── pyproject.toml                   # Project metadata & tasks
│   ├── requirements.txt                 # Danh sách thư viện Python
│   └── .env.example                     # File cấu hình biến môi trường mẫu
│
├── infra/
│   └── docker/
│       ├── docker-compose.yml           # Chạy Ollama (GPU/CPU) + TEI Embedding
│       └── Dockerfile                   # Multi-stage Dockerfile cho Backend
│
├── scripts/
│   └── deploy_python.ps1                # Script triển khai tự động
│
└── docs/
    └── deployment_guide.md              # Tài liệu hướng dẫn cài đặt & vận hành chi tiết
```

---

## 🚀 Hướng Dẫn Cài Đặt & Khởi Chạy Nhanh

### Bước 1: Khởi tạo Cơ Sở Dữ Liệu SQL Server

Chạy script SQL tự chứa hoàn chỉnh trong thư mục `database/`:

```bash
sqlcmd -S localhost -U sa -P YourPassword -i database/setup.sql
```

_Script sẽ tự động tạo CSDL `RagVectorDb`, 7 bảng lưu trữ Vector 1024 dims, Full-Text Catalog và seed dữ liệu mẫu._

### Bước 2: Khởi chạy Hạ tầng Ollama & TEI qua Docker Compose

```bash
cd infra/docker
docker compose up -d
```

Tải các mô hình AI về Ollama:

```bash
docker exec -it rag-ollama ollama pull qwen2.5:3b
docker exec -it rag-ollama ollama pull qwen2.5vl:7b
docker exec -it rag-ollama ollama pull deepseek-r1:7b
docker exec -it rag-ollama ollama pull llama3.2:3b
```

### Bước 3: Cấu hình Môi trường & Khởi chạy Backend

1. Tạo file `.env` từ `.env.example`:

```bash
cp configs/.env.example .env
```

2. Cài đặt thư viện Python:

```bash
pip install -r configs/requirements.txt
```

3. Khởi chạy dịch vụ FastAPI:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 30001 --reload
```

### Bước 4: Trải nghiệm Giao diện Gemini Web UI

Mở trình duyệt truy cập:
👉 **`http://localhost:30001`** (hoặc `http://localhost:30001/ui`)

- Chọn mô hình AI từ dropdown phía trên.
- Bật/Tắt chế độ Vision Mode tùy theo nhu cầu.
- Mở **Kho Tri Thức Tài Liệu** để nạp tài liệu PDF, DOCX, PPTX, XLSX.
- Đặt câu hỏi và nhận câu trả lời dạng stream thời gian thực kèm trích dẫn nguồn!

---

## 📡 API Endpoints Chính

| Phương thức | Endpoint                              | Mô tả                                                     |
| ----------- | ------------------------------------- | --------------------------------------------------------- |
| `GET`       | `/`                                   | Phục vụ trang Web UI Google Gemini Standalone             |
| `GET`       | `/api/v1/models`                      | Lấy danh sách mô hình AI khả dụng & trạng thái Ollama     |
| `POST`      | `/api/v1/chat/stream`                 | Gửi câu hỏi chat và nhận SSE stream token-by-token        |
| `POST`      | `/api/v1/conversations`               | Tạo phiên hội thoại mới                                   |
| `GET`       | `/api/v1/conversations`               | Lấy danh sách lịch sử hội thoại của người dùng            |
| `GET`       | `/api/v1/conversations/{id}/messages` | Lấy chi tiết tin nhắn trong một phiên hội thoại           |
| `POST`      | `/api/v1/document/upload`             | Nạp file tài liệu vào Kho tri thức (Background Ingestion) |
| `GET`       | `/api/v1/document/tasks/{taskId}`     | Kiểm tra tiến độ xử lý Ingestion thời gian thực           |
| `GET`       | `/api/v1/document/documents`          | Lấy danh sách tài liệu đã được lập chỉ mục Vector         |
| `DELETE`    | `/api/v1/document/documents/{id}`     | Xóa tài liệu và toàn bộ các Vector Chunks liên quan       |

---

## 🛡️ Bản Quyền & Giấy Phép

Dự án được phân phối dưới giấy phép [MIT License](LICENSE).
Tự do sử dụng, tùy biến và tích hợp vào các giải pháp doanh nghiệp.
