# Hướng Dẫn Cài Đặt & Triển Khai Chi Tiết

> 🌐 Ngôn ngữ: **Tiếng Việt** | [English](deployment_guide.md)

Tài liệu này hướng dẫn chi tiết từng bước thiết lập, cấu hình, vận hành và bảo trì hệ thống **Rag Assistant**. Hệ thống được xây dựng bằng Python FastAPI, hỗ trợ xử lý Đa phương thức (Văn bản & Hình ảnh), Tìm kiếm lai True Hybrid Search (SQL Server Vector + Full-Text Search + RRF), Dynamic Top-K, Re-ranking đa tầng và luồng phản hồi thời gian thực qua Server-Sent Events (SSE).

---

## Mục Lục

1. [Yêu Cầu Tiên Quyết Của Hệ Thống](#1-yeu-cau-tien-quyet-cua-he-thong)
2. [Khởi Chạy Hạ Tầng (Docker: Ollama & TEI)](#2-khoi-chay-ha-tang-docker-ollama--tei)
3. [Thiết Lập Cơ Sở Dữ Liệu (SQL Server Vector & FTS)](#3-thiet-lap-co-so-du-lieu-sql-server-vector--fts)
4. [Môi Trường Python & Cài Đặt Thư Viện](#4-moi-truong-python--cai-dat-thu-vien)
5. [Cấu Hình Biến Môi Trường (.env)](#5-cau-hinh-bien-moi-truong-env)
6. [Khởi Chạy Ứng Dụng](#6-khoi-chay-ung-dung)
7. [Kiểm Thử & Xác Minh](#7-kiem-thu--xac-minh)
8. [Danh Mục API Endpoints](#8-danh-muc-api-endpoints)
9. [Khắc Phục Sự Cố & Lỗi Thường Gặp](#9-khac-phuc-su-co--loi-thuong-gap)
10. [Hướng Dẫn Triển Khai Production](#10-huong-dan-trien-khai-production)

---

## 1. Yêu Cầu Tiên Quyết Của Hệ Thống

Trước khi bắt đầu, hãy đảm bảo máy chủ hoặc thiết bị của bạn đáp ứng các tiêu chuẩn sau:

### Yêu Cầu Phần Cứng
- **CPU**: Tối thiểu 4 nhân (khuyến nghị 8 nhân để chạy embedding và mô hình AI mượt mà).
- **RAM**: Tối thiểu 16 GB (khuyến nghị 32 GB nếu chạy các mô hình 7B cục bộ hoàn toàn trên RAM/CPU).
- **GPU (Tùy chọn)**: Card đồ họa NVIDIA với CUDA 12+ (VRAM từ 8GB trở lên) giúp tăng tốc độ suy luận của Ollama và TEI đáng kể.
- **Dung lượng ổ đĩa**: Trống tối thiểu 25 GB để lưu trữ trọng số mô hình và cơ sở dữ liệu vector.

### Yêu Cầu Phần Mềm
- **Hệ điều hành**: Windows 10/11 (64-bit), Ubuntu 20.04+ hoặc macOS (Apple Silicon).
- **Python**: Phiên bản `3.11` hoặc `3.12`.
- **Docker & Docker Compose**: Docker Desktop (Windows/macOS) hoặc Docker Engine + Docker Compose v2 (Linux).
- **Microsoft ODBC Driver for SQL Server**: Phiên bản 17 hoặc 18 ([Tải về từ Microsoft](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)).
- **Tesseract OCR (Tùy chọn cho phân tích chữ từ hình ảnh)**:
  - Windows: Tải bản cài đặt [UB-Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) (chọn thêm gói ngôn ngữ tiếng Việt `vie`). Thêm thư mục cài đặt (ví dụ: `C:\Program Files\Tesseract-OCR`) vào biến môi trường hệ thống `PATH`.
  - Linux: `sudo apt-get install tesseract-ocr tesseract-ocr-vie`
  - macOS: `brew install tesseract tesseract-lang`

---

## 2. Khởi Chạy Hạ Tầng (Docker: Ollama & TEI)

Hệ thống phụ thuộc vào 2 dịch vụ AI nền tảng chạy trong container Docker:
- **Ollama**: Cung cấp các mô hình ngôn ngữ lớn (LLM) và mô hình thị giác (Vision).
- **HuggingFace TEI (Text Embeddings Inference)**: Tạo vector dense 1024 chiều bằng mô hình `BAAI/bge-m3`.

### 2.1 Khởi Động Container Bằng Docker Compose

Từ thư mục gốc của dự án, di chuyển vào thư mục docker và chạy lệnh:

```bash
cd infra/docker
docker compose up -d
```

Kiểm tra trạng thái container:

```bash
docker compose ps
```

Kết quả hiển thị 2 container đang hoạt động:
- `rag-ollama`: Lắng nghe tại `http://localhost:11434`
- `rag-tei`: Lắng nghe tại `http://localhost:8080`

### 2.2 Tải Các Mô Hình AI Vào Ollama

Chạy các lệnh sau để tải các mô hình AI cần thiết:

```bash
# 1. Mô hình văn bản nhẹ, tốc độ cao (mặc định)
docker exec -it rag-ollama ollama pull qwen2.5:3b

# 2. Mô hình đa phương thức (xử lý hình ảnh, ảnh chụp màn hình, biểu đồ)
docker exec -it rag-ollama ollama pull qwen2.5vl:7b

# 3. Mô hình suy luận chuyên sâu Chain-of-Thought
docker exec -it rag-ollama ollama pull deepseek-r1:7b

# 4. Mô hình tổng quát đa năng
docker exec -it rag-ollama ollama pull llama3.2:3b
```

Kiểm tra danh sách mô hình đã tải thành công:

```bash
docker exec -it rag-ollama ollama list
```

### 2.3 Kiểm Tra Dịch Vụ Embedding (TEI)

Gửi thử request kiểm tra TEI hoạt động:

```bash
curl -X POST http://localhost:8080/embed \
  -H "Content-Type: application/json" \
  -d "{\"inputs\": \"Xin chào thế giới\"}"
```

Kết quả trả về một mảng JSON gồm 1024 số thực (float).

---

## 3. Thiết Lập Cơ Sở Dữ Liệu (SQL Server Vector & FTS)

Hệ thống sử dụng Microsoft SQL Server để lưu trữ tài liệu, đoạn văn bản (chunks), vector 1024 chiều (`VECTOR(1024)`), Full-Text catalog, phiên hội thoại và tin nhắn.

### 3.1 Chạy Script Khởi Tạo CSDL

Chạy file script `database/setup.sql` bằng công cụ dòng lệnh `sqlcmd` hoặc phần mềm quản trị (Azure Data Studio, SSMS):

```bash
# Sử dụng sqlcmd (thay thế localhost, sa và YourPassword bằng thông tin tài khoản của bạn):
sqlcmd -S localhost -U sa -P YourPassword -i database/setup.sql
```

### 3.2 Các Thành Phần Script Tự Động Thiết Lập
1. **Cơ sở dữ liệu**: `RagVectorDb`.
2. **Các bảng lưu trữ**:
   - `RagDocuments`: Lưu thông tin tài liệu gốc (tên file, phạm vi truy cập, vai trò cho phép, phòng ban, mã băm, số lượng chunk).
   - `RagDocumentChunks`: Lưu trữ từng đoạn trích xuất, số thứ tự chunk, trang/slide, ngữ cảnh phân cấp tiêu đề (breadcrumbs) và cột vector `VECTOR(1024)`.
   - `Conversations`: Quản lý các phiên hội thoại, ID người dùng và tiêu đề tự sinh.
   - `Messages`: Lưu lịch sử tin nhắn của người dùng và trợ lý AI, thông tin trích dẫn nguồn (citations) và mã trace.
3. **Full-Text Catalog & Index**:
   - Tạo Full-Text Catalog (`RagFTCatalog`) trên cột `content` của bảng `RagDocumentChunks` phục vụ truy vấn từ khóa `CONTAINSTABLE`.
4. **Phân quyền RBAC**: Các cột `accessScope`, `allowedRoles` và `departmentId` để lọc tài liệu theo quyền người dùng trực tiếp trong câu lệnh SQL.

---

## 4. Môi Trường Python & Cài Đặt Thư Viện

### 4.1 Khởi Tạo Môi Trường Ảo (Virtual Environment)

Di chuyển vào thư mục gốc của dự án:

```powershell
cd "f:\BKU\Nam 3\Intern\Intern\Rag"

# Tạo môi trường ảo riêng biệt
python -m venv .venv

# Kích hoạt trên Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# Kích hoạt trên Windows (Command Prompt):
.\.venv\Scripts\activate.bat

# Kích hoạt trên Linux / macOS:
source .venv/bin/activate
```

### 4.2 Cài Đặt Các Gói Phụ Thuộc

Nâng cấp `pip` và cài đặt các thư viện từ file `requirements.txt`:

```bash
python -m pip install --upgrade pip
pip install -r configs/requirements.txt
```

---

## 5. Cấu Hình Biến Môi Trường (.env)

Sao chép file cấu hình mẫu để tạo file `.env`:

```bash
cp configs/.env.example .env
```

Mở file `.env` và điều chỉnh các giá trị phù hợp với môi trường của bạn:

```env
# ==============================================================================
# Cấu hình Cơ Sở Dữ Liệu SQL Server
# ==============================================================================
# Thay đổi Server, Database, User Id và Password phù hợp.
# Nếu dùng ODBC Driver 18 trên môi trường phát triển chưa có chứng chỉ SSL, giữ TrustServerCertificate=True.
SQLSERVER_CONNECTIONSTRING=Driver={ODBC Driver 18 for SQL Server};Server=localhost;Database=RagVectorDb;User Id=sa;Password=YourPassword;TrustServerCertificate=True;

# ==============================================================================
# Dịch vụ Embedding (HuggingFace TEI)
# ==============================================================================
TEI_URL=http://localhost:8080
EMBEDDING_DIMS=1024
EMBEDDING_MODEL=BAAI/bge-m3

# ==============================================================================
# Dịch vụ Suy Luận LLM (Ollama / vLLM / LM Studio)
# ==============================================================================
UPRAG_LMSTUDIOENDPOINT=http://localhost:11434/v1
UPRAG_MODELID=qwen2.5:3b
UPRAG_APIKEY=ollama

# ==============================================================================
# Cấu hình Reranker Đa Tầng
# ==============================================================================
# Các lựa chọn: 'disabled' (tốc độ tối đa), 'flashrank' (chạy ONNX nhẹ cục bộ), 'cross_encoder' (chính xác nhất)
RERANKER_TYPE=disabled
RERANKER_MODEL=BAAI/bge-reranker-base

# ==============================================================================
# Cấu hình Truy Xuất Động Dynamic Top-K
# ==============================================================================
RAG_DYNAMIC_TOP_K_ENABLED=true
RAG_DYNAMIC_TOP_K_BASE=5
RAG_DYNAMIC_TOP_K_MIN=3
RAG_DYNAMIC_TOP_K_MAX=10
RAG_DYNAMIC_TOP_K_COMPLEX_BONUS=2
RAG_DYNAMIC_TOP_K_SIMPLE_DISCOUNT=1
RAG_DYNAMIC_TOP_K_LOW_CONF_BOOST=2
RAG_DYNAMIC_TOP_K_CONF_THRESHOLD=0.6

# ==============================================================================
# Mở Rộng Đoạn Lân Cận (Adjacent Sibling Chunk Expansion)
# ==============================================================================
RAG_ADJACENT_EXPANSION_ENABLED=true
RAG_ADJACENT_EXPANSION_WINDOW=1

# ==============================================================================
# Chuẩn Hóa Văn Bản Tiếng Việt
# ==============================================================================
RAG_ENABLE_VIETNAMESE_NORMALIZATION=true
RAG_NORMALIZATION_USE_SEGMENTATION=false

# ==============================================================================
# Theo Dõi LLMOps (Tùy chọn)
# ==============================================================================
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## 6. Khởi Chạy Ứng Dụng

Khởi chạy ứng dụng FastAPI bằng máy chủ Uvicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 30001 --reload
```

Khi khởi động thành công, màn hình console sẽ hiển thị:
- Vòng đời ứng dụng (lifespan) khởi tạo thành công.
- Các dịch vụ Singleton (Embedding, Retriever, Repositories, Guardrails) đã sẵn sàng.
- Ứng dụng đang lắng nghe tại `http://0.0.0.0:30001`.

### Địa Chỉ Truy Cập Giao Diện
- **Giao diện Web UI (Dark Theme)**: Mở trình duyệt tại [http://localhost:30001](http://localhost:30001)
- **Tài liệu Swagger / OpenAPI tương tác**: [http://localhost:30001/docs](http://localhost:30001/docs)
- **Tài liệu ReDoc**: [http://localhost:30001/redoc](http://localhost:30001/redoc)

---

## 7. Kiểm Thử & Xác Minh

Hệ thống tích hợp sẵn các bộ kiểm thử tự động để kiểm tra toàn bộ luồng hoạt động:

```bash
# 1. Kiểm tra tiêu chuẩn kiến trúc & đăng ký route
pytest tests/test_verify.py -v

# 2. Kiểm tra Guardrails, Evaluation metrics và RBAC Rate Limiter 6 cấp độ
pytest tests/test_advanced_features.py -v

# 3. Kiểm tra Dynamic Top-K, Reranker, Normalizer và Adjacent Chunk Expansion
pytest tests/test_rag_improvements.py -v

# 4. Chạy toàn bộ test suite
pytest tests/ -v
```

### Kiểm Tra Nhanh Bằng Lệnh `curl`

```bash
# Kiểm tra máy chủ hoạt động cơ bản (Liveness probe)
curl http://localhost:30001/health

# Kiểm tra trạng thái toàn diện kết nối CSDL, TEI và LLM
curl http://localhost:30001/api/v1/health

# Xem danh sách mô hình AI đang khả dụng
curl http://localhost:30001/api/v1/models
```

---

## 8. Danh Mục API Endpoints

| Phương thức | Endpoint | Mô tả |
| ----------- | -------- | ----- |
| `GET` | `/` | Giao diện Web UI độc lập phong cách Google Gemini |
| `GET` | `/health` | Kiểm tra trạng thái máy chủ (Liveness probe) |
| `GET` | `/api/v1/health` | Kiểm tra kết nối sâu hệ thống (CSDL, TEI, LLM) |
| `GET` | `/api/v1/models` | Danh sách mô hình AI khả dụng và trạng thái |
| `POST` | `/api/v1/chat/stream` | Gửi câu hỏi và nhận stream phản hồi qua SSE theo thời gian thực |
| `POST` | `/api/v1/conversations` | Tạo phiên hội thoại mới |
| `GET` | `/api/v1/conversations` | Lấy danh sách lịch sử hội thoại của người dùng |
| `GET` | `/api/v1/conversations/{id}/messages` | Lấy danh sách tin nhắn chi tiết trong một phiên |
| `POST` | `/api/v1/document/upload` | Tải tài liệu lên kho tri thức (Chạy ngầm Background Task) |
| `GET` | `/api/v1/document/tasks/{taskId}` | Theo dõi tiến độ nạp tài liệu theo thời gian thực |
| `GET` | `/api/v1/document/documents` | Lấy danh sách tài liệu đã lập chỉ mục vector |
| `DELETE` | `/api/v1/document/documents/{id}` | Xóa tài liệu và toàn bộ các chunk vector liên quan |

---

## 9. Khắc Phục Sự Cố & Lỗi Thường Gặp

### 9.1 Lỗi Kết Nối SQL Server (`pyodbc.Error`)
- **Triệu chứng**: `ODBC Driver 18 for SQL Server: SSL Provider: The certificate chain was issued by an authority that is not trusted.`
- **Xử lý**: Đảm bảo chuỗi kết nối trong file `.env` đã có tham số `TrustServerCertificate=True;`.
- **Triệu chứng**: `Could not open a connection to SQL Server [2].`
- **Xử lý**: Kiểm tra dịch vụ SQL Server đang chạy trong `services.msc`, đảm bảo giao thức TCP/IP đã được bật trong SQL Server Configuration Manager (Port mặc định 1433).

### 9.2 Lỗi Kết Nối Hoặc Timeout Dịch Vụ TEI
- **Triệu chứng**: `Cannot connect to host localhost:8080` hoặc mã lỗi HTTP 500 khi sinh vector embedding.
- **Xử lý**:
  1. Kiểm tra trạng thái container: `docker ps`
  2. Xem log của TEI: `docker logs rag-tei`
  3. Đảm bảo mô hình `BAAI/bge-m3` đã tải xong trọng số về máy.

### 9.3 Lỗi Tràn Bộ Nhớ Ollama (Out of Memory - OOM)
- **Triệu chứng**: Phản hồi mất quá nhiều thời gian hoặc trả về token rỗng.
- **Xử lý**:
  1. Sử dụng mô hình nhẹ `qwen2.5:3b` làm mô hình mặc định.
  2. Tăng giới hạn RAM cấp cho Docker Desktop (Settings -> Resources -> Memory -> cấp tối thiểu 8 GB).

### 9.4 Không Tìm Thấy File Thực Thi Tesseract OCR
- **Triệu chứng**: `pytesseract.TesseractNotFoundError: tesseract is not installed or it's not in your PATH`.
- **Xử lý**: Thêm đường dẫn thư mục cài đặt Tesseract (`C:\Program Files\Tesseract-OCR`) vào biến môi trường hệ thống `PATH`.

### 9.5 Trùng Lặp Cổng 30001
- **Triệu chứng**: `[Errno 10048] error while attempting to bind on address ('0.0.0.0', 30001)`.
- **Xử lý**:
  - Tìm tiến trình đang chiếm cổng: `netstat -ano | findstr 30001`
  - Đóng tiến trình đó: `taskkill /PID <PID> /F`
  - Hoặc khởi chạy Uvicorn trên một cổng khác: `--port 30002`

---

## 10. Hướng Dẫn Triển Khai Production

### 10.1 Đóng Gói Docker Container

Tạo image Docker phục vụ production:

```bash
docker build -f infra/docker/Dockerfile -t rag-assistant:latest .
```

Khởi chạy container với file môi trường:

```bash
docker run -d \
  --name rag-assistant \
  -p 30001:30001 \
  --env-file .env \
  --restart unless-stopped \
  rag-assistant:latest
```

### 10.2 Triển Khai Kubernetes

File manifest Kubernetes mẫu đã được chuẩn bị tại `infra/k8s/rag-python.yaml`. Triển khai bằng lệnh `kubectl`:

```bash
kubectl apply -f infra/k8s/rag-python.yaml
```

Manifest bao gồm:
- Tự động mở rộng số lượng Pod (Horizontal Pod Autoscaler - HPA) theo ngưỡng sử dụng CPU 70%.
- Đầu kiểm tra Liveness Probe và Readiness Probe liên kết với `/health` và `/api/v1/health`.
- Cấu hình giới hạn tài nguyên CPU/RAM cho Pod.
- Quản lý biến môi trường qua ConfigMap và Secret.
