# Detailed Installation & Deployment Guide

> 🌐 Language: **English** | [Tiếng Việt](deployment_guide_vi.md)

This comprehensive guide walks you through setting up, configuring, running, and maintaining the **Rag Assistant** service. The system is built with Python FastAPI, featuring Multimodal Vision & Text processing, True Hybrid Search (SQL Server Vector + Full-Text Search + RRF), Dynamic Top-K, Multi-Tier Reranking, and real-time Server-Sent Events (SSE) streaming.

---

## Table of Contents

1. [System Prerequisites](#1-system-prerequisites)
2. [Infrastructure Setup (Docker: Ollama & TEI)](#2-infrastructure-setup-docker-ollama--tei)
3. [Database Setup (SQL Server Vector & FTS)](#3-database-setup-sql-server-vector--fts)
4. [Python Environment & Dependencies](#4-python-environment--dependencies)
5. [Environment Variables Configuration](#5-environment-variables-configuration)
6. [Starting the Application](#6-starting-the-application)
7. [Testing & Verification](#7-testing--verification)
8. [API Endpoints Reference](#8-api-endpoints-reference)
9. [Troubleshooting & Common Issues](#9-troubleshooting--common-issues)
10. [Production Deployment Guidelines](#10-production-deployment-guidelines)

---

## 1. System Prerequisites

Before starting, ensure your system meets the following software and hardware requirements:

### Hardware Requirements
- **CPU**: 4 cores minimum (8 cores recommended for local embeddings and inference).
- **RAM**: 16 GB minimum (32 GB recommended if running 7B models locally on CPU/RAM).
- **GPU (Optional)**: NVIDIA GPU with CUDA 12+ (8GB+ VRAM) enables fast local inference with Ollama and TEI.
- **Disk Space**: At least 25 GB free disk space (to store model weights and vector embeddings).

### Software Requirements
- **Operating System**: Windows 10/11 (64-bit), Ubuntu 20.04+, or macOS (Apple Silicon).
- **Python**: Version `3.11` or `3.12`.
- **Docker & Docker Compose**: Docker Desktop (Windows/macOS) or Docker Engine + Docker Compose v2 (Linux).
- **Microsoft ODBC Driver for SQL Server**: Version 17 or 18 ([Download from Microsoft](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)).
- **Tesseract OCR (Optional for image text extraction)**:
  - Windows: [UB-Mannheim Tesseract installer](https://github.com/UB-Mannheim/tesseract/wiki) (Install with Vietnamese `vie` language pack). Add installation folder (e.g. `C:\Program Files\Tesseract-OCR`) to system `PATH`.
  - Linux: `sudo apt-get install tesseract-ocr tesseract-ocr-vie`
  - macOS: `brew install tesseract tesseract-lang`

---

## 2. Infrastructure Setup (Docker: Ollama & TEI)

The system relies on two containerized AI engines:
- **Ollama**: Serves local Large Language Models (LLMs) and Vision Models.
- **HuggingFace TEI (Text Embeddings Inference)**: Computes 1024-dimensional dense vectors using `BAAI/bge-m3`.

### 2.1 Start Containers via Docker Compose

From the project root directory, navigate to the docker directory and launch the services:

```bash
cd infra/docker
docker compose up -d
```

Verify that both containers are running and healthy:

```bash
docker compose ps
```

You should see:
- `rag-ollama`: listening on `http://localhost:11434`
- `rag-tei`: listening on `http://localhost:8080`

### 2.2 Download AI Models into Ollama

Run the following commands to pull the models required by the system:

```bash
# 1. Fast text-only model (default)
docker exec -it rag-ollama ollama pull qwen2.5:3b

# 2. Multimodal vision-language model (for screenshot and image analysis)
docker exec -it rag-ollama ollama pull qwen2.5vl:7b

# 3. Chain-of-Thought reasoning model
docker exec -it rag-ollama ollama pull deepseek-r1:7b

# 4. General versatile model
docker exec -it rag-ollama ollama pull llama3.2:3b
```

Verify installed models:

```bash
docker exec -it rag-ollama ollama list
```

### 2.3 Verify Embedding Service (TEI)

Test the embedding service by sending an HTTP POST request:

```bash
curl -X POST http://localhost:8080/embed \
  -H "Content-Type: application/json" \
  -d "{\"inputs\": \"Hello world\"}"
```

A JSON array containing 1024 float numbers should be returned.

---

## 3. Database Setup (SQL Server Vector & FTS)

The service uses Microsoft SQL Server to store documents, chunk metadata, 1024-dimensional dense vectors (`VECTOR(1024)`), full-text catalogs, chat conversations, and messages.

### 3.1 Run Setup Script

Run `database/setup.sql` against your SQL Server instance using `sqlcmd` or a graphical tool (Azure Data Studio, SQL Server Management Studio):

```bash
# Using sqlcmd (replace localhost, sa, and YourPassword with your credentials):
sqlcmd -S localhost -U sa -P YourPassword -i database/setup.sql
```

### 3.2 What the Setup Script Creates
1. **Database**: `RagVectorDb` (if not already existing).
2. **Tables**:
   - `RagDocuments`: Stores document metadata (filename, access scope, allowed roles, department, hash, chunk count).
   - `RagDocumentChunks`: Stores individual chunks, chunk index, page/slide info, heading context breadcrumbs, text content, and `VECTOR(1024)` embedding column.
   - `Conversations`: Stores user chat sessions, user IDs, and auto-generated titles.
   - `Messages`: Stores conversation history, role (`user`, `assistant`), message text, citations, and tracing IDs.
3. **Full-Text Catalog & Index**:
   - Creates a Full-Text Catalog (`RagFTCatalog`) on `RagDocumentChunks(content)` supporting `CONTAINSTABLE` lexical retrieval.
4. **RBAC Metadata Fields**: Columns `accessScope`, `allowedRoles`, and `departmentId` for row-level document access filtering.

---

## 4. Python Environment & Dependencies

### 4.1 Create Virtual Environment

Navigate to the project root directory:

```powershell
cd "f:\BKU\Nam 3\Intern\Intern\Rag"

# Create a clean virtual environment
python -m venv .venv

# Activate on Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# Activate on Windows (Command Prompt):
.\.venv\Scripts\activate.bat

# Activate on Linux / macOS:
source .venv/bin/activate
```

### 4.2 Install Dependencies

Upgrade `pip` and install all required packages:

```bash
python -m pip install --upgrade pip
pip install -r configs/requirements.txt
```

---

## 5. Environment Variables Configuration

Copy the provided example file to create your `.env` file:

```bash
cp configs/.env.example .env
```

Open `.env` in your editor and configure the parameters according to your environment:

```env
# ==============================================================================
# Database Configuration
# ==============================================================================
# Replace Server, Database, User Id, and Password with your credentials.
# If using ODBC Driver 18 on a local dev machine without SSL certificate, set TrustServerCertificate=True.
SQLSERVER_CONNECTIONSTRING=Driver={ODBC Driver 18 for SQL Server};Server=localhost;Database=RagVectorDb;User Id=sa;Password=YourPassword;TrustServerCertificate=True;

# ==============================================================================
# Embedding Service (HuggingFace TEI)
# ==============================================================================
TEI_URL=http://localhost:8080
EMBEDDING_DIMS=1024
EMBEDDING_MODEL=BAAI/bge-m3

# ==============================================================================
# LLM Inference Service (Ollama / vLLM / LM Studio)
# ==============================================================================
UPRAG_LMSTUDIOENDPOINT=http://localhost:11434/v1
UPRAG_MODELID=qwen2.5:3b
UPRAG_APIKEY=ollama

# ==============================================================================
# Multi-Tier Reranker Configuration
# ==============================================================================
# Options: 'disabled' (fastest), 'flashrank' (fast ONNX local), 'cross_encoder' (highest accuracy)
RERANKER_TYPE=disabled
RERANKER_MODEL=BAAI/bge-reranker-base

# ==============================================================================
# Dynamic Top-K Retrieval Configuration
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
# Adjacent Sibling Chunk Expansion
# ==============================================================================
RAG_ADJACENT_EXPANSION_ENABLED=true
RAG_ADJACENT_EXPANSION_WINDOW=1

# ==============================================================================
# Vietnamese Text Normalization
# ==============================================================================
RAG_ENABLE_VIETNAMESE_NORMALIZATION=true
RAG_NORMALIZATION_USE_SEGMENTATION=false

# ==============================================================================
# LLMOps & Observability (Optional)
# ==============================================================================
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## 6. Starting the Application

Run the FastAPI application with Uvicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 30001 --reload
```

Upon successful startup, the console displays:
- Application startup lifecycle completed.
- Singleton services initialized (Embedding, Retriever, Repositories, Guardrails).
- Uvicorn running on `http://0.0.0.0:30001`.

### Accessing the Interfaces
- **Web UI (Gemini Dark Theme)**: Open your browser at [http://localhost:30001](http://localhost:30001)
- **Interactive OpenAPI / Swagger Documentation**: [http://localhost:30001/docs](http://localhost:30001/docs)
- **Alternative ReDoc API Documentation**: [http://localhost:30001/redoc](http://localhost:30001/redoc)

---

## 7. Testing & Verification

The project includes automated verification test suites:

```bash
# 1. Verify system architecture & route registration
pytest tests/test_verify.py -v

# 2. Verify Guardrails, Evaluation metrics, and 6-Tier RBAC Rate Limiter
pytest tests/test_advanced_features.py -v

# 3. Verify Dynamic Top-K, Multi-tier Reranker, Normalizer, and Adjacent Chunk Expansion
pytest tests/test_rag_improvements.py -v

# 4. Run all test suites
pytest tests/ -v
```

### Manual Health Check Verification via `curl`

```bash
# Basic Liveness check
curl http://localhost:30001/health

# Comprehensive subsystem readiness check (SQL Server, TEI, Ollama)
curl http://localhost:30001/api/v1/health

# Available AI models check
curl http://localhost:30001/api/v1/models
```

---

## 8. API Endpoints Reference

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| `GET` | `/` | Standalone Google Gemini-style Web UI |
| `GET` | `/health` | Lightweight liveness probe |
| `GET` | `/api/v1/health` | Deep health check (Database, TEI, LLM) |
| `GET` | `/api/v1/models` | List of available models and connectivity status |
| `POST` | `/api/v1/chat/stream` | Stream chat response token-by-token via SSE |
| `POST` | `/api/v1/conversations` | Create a new conversation session |
| `GET` | `/api/v1/conversations` | Retrieve user conversation history list |
| `GET` | `/api/v1/conversations/{id}/messages` | Retrieve message history for a conversation |
| `POST` | `/api/v1/document/upload` | Upload documents for ingestion (Background task) |
| `GET` | `/api/v1/document/tasks/{taskId}` | Poll real-time document ingestion progress |
| `GET` | `/api/v1/document/documents` | List all indexed documents in the database |
| `DELETE` | `/api/v1/document/documents/{id}` | Delete a document and its associated vector chunks |

---

## 9. Troubleshooting & Common Issues

### 9.1 Database Connection Errors (`pyodbc.Error`)
- **Symptom**: `ODBC Driver 18 for SQL Server: SSL Provider: The certificate chain was issued by an authority that is not trusted.`
- **Solution**: Add `TrustServerCertificate=True;` to `SQLSERVER_CONNECTIONSTRING` in `.env`.
- **Symptom**: `Could not open a connection to SQL Server [2].`
- **Solution**: Ensure the SQL Server service is running in Windows Services (`services.msc`) and TCP/IP protocol is enabled in SQL Server Configuration Manager (Port 1433).

### 9.2 TEI Service Timeout or Connection Refused
- **Symptom**: `Cannot connect to host localhost:8080` or HTTP 500 when creating embeddings.
- **Solution**:
  1. Check container status: `docker ps`
  2. Inspect TEI logs: `docker logs rag-tei`
  3. Verify that model weights `BAAI/bge-m3` finished downloading.

### 9.3 Ollama Out of Memory (OOM)
- **Symptom**: Response takes very long or returns empty tokens.
- **Solution**:
  1. Default to lightweight model `qwen2.5:3b` for general queries.
  2. Increase Docker Desktop memory limit (Settings -> Resources -> Memory -> allocate at least 8 GB).

### 9.4 Tesseract OCR Executable Not Found
- **Symptom**: `pytesseract.TesseractNotFoundError: tesseract is not installed or it's not in your PATH`.
- **Solution**: Add Tesseract directory (`C:\Program Files\Tesseract-OCR`) to your system Environment `PATH`, or set `TESSERACT_CMD` environment variable.

### 9.5 Port Conflict on Port 30001
- **Symptom**: `[Errno 10048] error while attempting to bind on address ('0.0.0.0', 30001)`.
- **Solution**:
  - Find the process using port 30001: `netstat -ano | findstr 30001`
  - Terminate the conflicting process: `taskkill /PID <PID> /F`
  - Or run Uvicorn on an alternate port: `--port 30002`

---

## 10. Production Deployment Guidelines

### 10.1 Docker Containerization

Build the production Docker container:

```bash
docker build -f infra/docker/Dockerfile -t rag-assistant:latest .
```

Run container with environment file:

```bash
docker run -d \
  --name rag-assistant \
  -p 30001:30001 \
  --env-file .env \
  --restart unless-stopped \
  rag-assistant:latest
```

### 10.2 Kubernetes Deployment

A production Kubernetes manifest is provided at `infra/k8s/rag-python.yaml`. Deploy via `kubectl`:

```bash
kubectl apply -f infra/k8s/rag-python.yaml
```

The manifest configures:
- Horizontal Pod Autoscaler (HPA) targeting 70% CPU utilization.
- Liveness and readiness probes pointing to `/health` and `/api/v1/health`.
- Resource requests and limits for memory and CPU.
- ConfigMaps and Secrets for environment variables.
