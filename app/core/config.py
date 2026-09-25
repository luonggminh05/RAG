import os
from functools import lru_cache
from typing import List, Optional, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Danh mục các mô hình AI được hỗ trợ bởi hệ thống (được định nghĩa trước class để có thể import độc lập)
AVAILABLE_MODELS = [
    {
        "id": "qwen2.5:3b",
        "name": "Qwen 2.5 3B (Fast & Light)",
        "type": "text",
        "description": "Siêu nhanh, tối ưu cho hỏi đáp văn bản quy trình và tác vụ nhẹ",
    },
    {
        "id": "qwen2.5vl:7b",
        "name": "Qwen 2.5-VL 7B (Vision & Multimodal)",
        "type": "multimodal",
        "description": "Đa phương thức, hiểu sâu văn bản kèm ảnh chụp màn hình",
    },
    {
        "id": "deepseek-r1:7b",
        "name": "DeepSeek-R1 7B (Reasoning)",
        "type": "reasoning",
        "description": "Mô hình suy luận sâu với chuỗi tư duy (Chain-of-Thought)",
    },
    {
        "id": "llama3.2:3b",
        "name": "Llama 3.2 3B (General Assistant)",
        "type": "text",
        "description": "Trợ lý đa năng, phản hồi nhanh gọn và chính xác",
    },
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        case_sensitive=False,
    )

    # --- Core Application ---
    ENVIRONMENT: str = "local"
    PROJECT_NAME: str = "Rag Python AI Service (DDD Enterprise)"
    API_V1_STR: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8080

    # API Key để xác thực request nội bộ
    required_api_key: str = Field(default="", alias="RAG_API_REQUIRED_API_KEY")
    REQUIRED_API_KEY: str = Field(default="", alias="REQUIRED_API_KEY")

    @property
    def effective_api_key(self) -> str:
        return self.required_api_key or self.REQUIRED_API_KEY or ""

    # --- LLM Settings (Ollama / vLLM / OpenAI Compatible) ---
    llm_endpoint: str = Field(default="http://localhost:11434/v1", alias="UPRAG_LMSTUDIOENDPOINT")
    llm_model_id: str = Field(default="qwen2.5vl:7b", alias="UPRAG_MODELID")
    llm_api_key: str = Field(default="ollama", alias="UPRAG_APIKEY")
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=2048, alias="LLM_MAX_TOKENS")

    # --- Gemini & Multimodal STT Settings ---
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")

    # --- Embedding Settings (TEI Server) ---
    tei_url: str = Field(default="http://localhost:8080", alias="TEI_URL")
    embedding_dims: int = Field(default=1024, alias="EMBEDDING_DIMS")
    embedding_model: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL")

    # --- SQL Server Connection ---
    sql_connection_string: str = Field(
        default="Server=localhost;Database=RagVectorDb;User Id=rag_api_user;Password=REPLACE_WITH_SQLSERVER_SA_PASSWORD;TrustServerCertificate=True;",
        alias="SQLSERVER_CONNECTIONSTRING"
    )

    # --- Ingestion Settings ---
    ingestion_chunk_size: int = Field(default=600, alias="INGESTION_CHUNKSIZE")
    ingestion_chunk_overlap: int = Field(default=100, alias="INGESTION_CHUNKOVERLAP")
    ingestion_chunk_tokens_min: int = Field(default=300, alias="INGESTION_CHUNKTOKENS_MIN")
    ingestion_chunk_tokens_max: int = Field(default=500, alias="INGESTION_CHUNKTOKENS_MAX")
    ingestion_chunk_overlap_tokens: int = Field(default=75, alias="INGESTION_CHUNKOVERLAP_TOKENS")
    ingestion_batch_size: int = Field(default=16, alias="INGESTION_BATCHSIZE")
    ingestion_papers_dir: str = Field(default="papers", alias="INGESTION_PAPERSDIRECTORY")
    ingestion_enable_ocr: bool = Field(default=True, alias="INGESTION_ENABLEOCR")
    ingestion_tessdata_path: str = Field(default="tessdata", alias="INGESTION_TESSDATAPATH")

    # --- Vision & Multimodal Settings ---
    ingestion_enable_vision_caption: bool = Field(default=True, alias="INGESTION_ENABLEVISIONCAPTION")
    ingestion_vision_api_url: str = Field(default="http://localhost:11434/v1/chat/completions", alias="INGESTION_VISIONAPIURL")
    ingestion_vision_api_key: str = Field(default="ollama", alias="INGESTION_VISIONAPIKEY")
    ingestion_vision_model: str = Field(default="qwen2.5vl:7b", alias="INGESTION_VISIONMODEL")
    ingestion_min_vision_image_width: int = Field(default=100, alias="INGESTION_MINVISIONIMAGEWIDTH")
    ingestion_min_vision_image_height: int = Field(default=100, alias="INGESTION_MINVISIONIMAGEHEIGHT")
    ingestion_vision_large_image_min_side: int = Field(default=1200, alias="INGESTION_VISION_LARGE_IMAGE_MIN_SIDE")
    ingestion_vision_large_image_min_pixels: int = Field(default=1000000, alias="INGESTION_VISION_LARGE_IMAGE_MIN_PIXELS")
    ingestion_max_vision_images_per_slide: int = Field(default=0, alias="INGESTION_MAXVISIONIMAGESPERSLIDE")
    ingestion_max_vision_images_per_file: int = Field(default=0, alias="INGESTION_MAXVISIONIMAGESPERFILE")
    ingestion_vision_timeout_seconds: int = Field(default=160, alias="INGESTION_VISIONTIMEOUTSECONDS")
    ingestion_hierarchical_chunking: bool = Field(default=False, alias="INGESTION_HIERARCHICAL_CHUNKING")

    # --- Hybrid Search & RRF Settings ---
    search_top_k_max: int = Field(default=50, alias="SEARCH_TOPKMAX")
    search_chat_top_k: int = Field(default=5, alias="SEARCH_CHATTOPK")
    search_vector_candidate_count: int = Field(default=200, alias="SEARCH_VECTORCANDIDATECOUNT")
    search_rrf_constant: int = Field(default=60, alias="SEARCH_RRFCONSTANT")
    search_query_embedding_cache_size: int = Field(default=1024, alias="SEARCH_QUERYEMBEDDINGCACHESIZE")
    search_query_embedding_cache_ttl_seconds: int = Field(default=3600, alias="SEARCH_QUERYEMBEDDINGCACHETTLSECONDS")
    fts_enabled: bool = Field(default=True, alias="FTS_ENABLED")
    fts_max_candidates: int = Field(default=200, alias="FTS_MAX_CANDIDATES")
    rrf_vector_weight: float = Field(default=0.6, alias="RRF_VECTOR_WEIGHT")
    rrf_fts_weight: float = Field(default=0.4, alias="RRF_FTS_WEIGHT")

    # --- Reranker Settings ---
    reranker_type: str = Field(default="disabled", alias="RERANKER_TYPE")  # disabled | flashrank | bge | cross_encoder
    reranker_model: Optional[str] = Field(default=None, alias="RERANKER_MODEL")
    reranker_top_k: int = Field(default=5, alias="RERANKER_TOP_K")
    hybrid_top_k_candidates: int = Field(default=20, alias="HYBRID_TOP_K_CANDIDATES")

    # --- RAG Dynamic Top-K & Adaptive Retrieval Settings ---
    rag_dynamic_top_k_enabled: bool = Field(default=True, alias="RAG_DYNAMIC_TOP_K_ENABLED")
    rag_min_top_k: int = Field(default=3, alias="RAG_MIN_TOP_K")
    rag_max_top_k: int = Field(default=15, alias="RAG_MAX_TOP_K")
    rag_specific_top_k: int = Field(default=3, alias="RAG_SPECIFIC_TOP_K")
    rag_exhaustive_top_k: int = Field(default=12, alias="RAG_EXHAUSTIVE_TOP_K")
    rag_enable_vietnamese_normalization: bool = Field(default=True, alias="RAG_ENABLE_VIETNAMESE_NORMALIZATION")
    rag_candidate_multiplier: int = Field(default=3, alias="RAG_CANDIDATE_MULTIPLIER")


    # --- CORS Origins ---
    frontend_cors_origins: Union[List[str], str] = Field(
        default=["*"],
        alias="FRONTEND_CORS_ORIGINS"
    )
    backend_cors_origins: Union[List[str], str] = Field(
        default=["*"],
        alias="BACKEND_CORS_ORIGINS"
    )

    @field_validator("frontend_cors_origins", "backend_cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, str)):
            return v
        return ["*"]

    # --- Rate Limiting & User Roles (RBAC 6-Tier) ---
    rate_limit_enabled: bool = Field(default=False, alias="RATE_LIMIT_ENABLED")
    rate_limit_master_rpm: int = Field(default=240, alias="RATE_LIMIT_MASTER_RPM")
    rate_limit_coleader_rpm: int = Field(default=180, alias="RATE_LIMIT_COLEADER_RPM")
    rate_limit_tier3_rpm: int = Field(default=120, alias="RATE_LIMIT_TIER3_RPM")
    rate_limit_elite_rpm: int = Field(default=60, alias="RATE_LIMIT_ELITE_RPM")
    rate_limit_member_rpm: int = Field(default=30, alias="RATE_LIMIT_MEMBER_RPM")
    rate_limit_recruit_rpm: int = Field(default=20, alias="RATE_LIMIT_RECRUIT_RPM")

    chat_concurrency_master: int = Field(default=15, alias="CHAT_CONCURRENCY_MASTER")
    chat_concurrency_coleader: int = Field(default=10, alias="CHAT_CONCURRENCY_COLEADER")
    chat_concurrency_tier3: int = Field(default=5, alias="CHAT_CONCURRENCY_TIER3")
    chat_concurrency_elite: int = Field(default=3, alias="CHAT_CONCURRENCY_ELITE")
    chat_concurrency_member: int = Field(default=2, alias="CHAT_CONCURRENCY_MEMBER")
    chat_concurrency_recruit: int = Field(default=1, alias="CHAT_CONCURRENCY_RECRUIT")

    valid_roles: List[str] = Field(
        default=["Master", "Admin", "Co-Leader", "Officer", "Staff", "Raid Leader", "Elite", "Member", "Recruit"],
        alias="VALID_ROLES"
    )

    # --- Agent & Chat History Settings ---
    chat_history_window: int = Field(default=6, alias="CHAT_HISTORY_WINDOW")

    # --- LangSmith / Langfuse ---
    langsmith_tracing: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")
    langsmith_api_key: Optional[str] = Field(default=None, alias="LANGCHAIN_API_KEY")
    langsmith_project: str = Field(default="rag-service", alias="LANGCHAIN_PROJECT")
    langfuse_enabled: bool = Field(default=False, alias="LANGFUSE_ENABLED")
    langfuse_public_key: Optional[str] = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: Optional[str] = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="http://localhost:3000", alias="LANGFUSE_HOST")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
