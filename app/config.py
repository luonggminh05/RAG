from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    # API settings
    required_api_key: str = Field(default="", alias="RAG_API_REQUIRED_API_KEY")
    
    # LLM Settings (OpenAI-compatible vLLM/LM Studio)
    llm_endpoint: str = Field(default="http://192.168.18.1:1224/v1", alias="UPRAG_LMSTUDIOENDPOINT")
    llm_model_id: str = Field(default="qwen2.5-vl-7b-instruct", alias="UPRAG_MODELID")
    llm_api_key: str = Field(default="EMPTY", alias="UPRAG_APIKEY")
    
    # Embedding settings (TEI Server)
    tei_url: str = Field(default="http://localhost:8080", alias="TEI_URL")
    
    # SQL Server connection settings
    sql_connection_string: str = Field(
        default="Server=localhost;Database=RagVectorDb;User Id=rag_api_user;Password=REPLACE_WITH_SQLSERVER_SA_PASSWORD;TrustServerCertificate=True;",
        alias="SQLSERVER_CONNECTIONSTRING"
    )
    
    # Ingestion settings
    ingestion_chunk_size: int = Field(default=600, alias="INGESTION_CHUNKSIZE")
    ingestion_chunk_overlap: int = Field(default=100, alias="INGESTION_CHUNKOVERLAP")
    ingestion_batch_size: int = Field(default=32, alias="INGESTION_BATCHSIZE")
    ingestion_papers_dir: str = Field(default="papers", alias="INGESTION_PAPERSDIRECTORY")
    ingestion_enable_ocr: bool = Field(default=True, alias="INGESTION_ENABLEOCR")
    ingestion_enable_vision_caption: bool = Field(default=True, alias="INGESTION_ENABLEVISIONCAPTION")
    ingestion_vision_api_url: str = Field(default="http://192.168.18.1:1224/v1/chat/completions", alias="INGESTION_VISIONAPIURL")
    ingestion_vision_api_key: str = Field(default="lm-studio", alias="INGESTION_VISIONAPIKEY")
    ingestion_vision_model: str = Field(default="qwen2.5-vl-7b-instruct", alias="INGESTION_VISIONMODEL")
    ingestion_tessdata_path: str = Field(default="tessdata", alias="INGESTION_TESSDATAPATH")
    ingestion_min_vision_image_width: int = Field(default=100, alias="INGESTION_MINVISIONIMAGEWIDTH")
    ingestion_min_vision_image_height: int = Field(default=100, alias="INGESTION_MINVISIONIMAGEHEIGHT")
    ingestion_max_vision_images_per_slide: int = Field(default=0, alias="INGESTION_MAXVISIONIMAGESPERSLIDE")
    ingestion_max_vision_images_per_file: int = Field(default=0, alias="INGESTION_MAXVISIONIMAGESPERFILE")
    ingestion_vision_timeout_seconds: int = Field(default=160, alias="INGESTION_VISIONTIMEOUTSECONDS")
    frontend_cors_origins: list[str] = Field(default=["http://localhost:4200"], alias="FRONTEND_CORS_ORIGINS")
    
    # Search settings
    search_top_k_max: int = Field(default=50, alias="SEARCH_TOPKMAX")
    search_chat_top_k: int = Field(default=3, alias="SEARCH_CHATTOPK")
    search_vector_candidate_count: int = Field(default=200, alias="SEARCH_VECTORCANDIDATECOUNT")
    search_rrf_constant: int = Field(default=60, alias="SEARCH_RRFCONSTANT")
    search_query_embedding_cache_size: int = Field(default=1024, alias="SEARCH_QUERYEMBEDDINGCACHESIZE")
    search_query_embedding_cache_ttl_seconds: int = Field(default=3600, alias="SEARCH_QUERYEMBEDDINGCACHETTLSECONDS")

    # FastAPI settings
    host: str = "0.0.0.0"
    port: int = 8080

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True
    )

settings = Settings()
