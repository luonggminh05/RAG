import json
import logging
import time
import pyodbc
from typing import List, Dict, Any, Tuple, Optional
from app.config import settings

logger = logging.getLogger(__name__)

class SqlDocumentRepository:
    def __init__(self):
        conn_str = settings.sql_connection_string
        # Normalize connection string boolean values for pyodbc/unixODBC compatibility
        if conn_str:
            import re
            conn_str = re.sub(r'(?i)\bTrustServerCertificate\s*=\s*True\b', 'TrustServerCertificate=yes', conn_str)
            conn_str = re.sub(r'(?i)\bTrustServerCertificate\s*=\s*False\b', 'TrustServerCertificate=no', conn_str)
            conn_str = re.sub(r'(?i)\bEncrypt\s*=\s*True\b', 'Encrypt=yes', conn_str)
            conn_str = re.sub(r'(?i)\bEncrypt\s*=\s*False\b', 'Encrypt=no', conn_str)
            conn_str = re.sub(r'(?i)\bUser\s+Id\b', 'UID', conn_str)
            conn_str = re.sub(r'(?i)\bPassword\b', 'PWD', conn_str)

        # Auto-inject ODBC Driver for Linux environment if not specified in connection string
        if conn_str and "driver=" not in conn_str.lower():
            driver = "ODBC Driver 18 for SQL Server"
            if not conn_str.rstrip().endswith(";"):
                conn_str += ";"
            conn_str = f"Driver={{{driver}}};{conn_str}"
            logger.info(f"Auto-injected default database driver: {driver}")
        self.connection_string = conn_str

    def _get_connection(self):
        # pyodbc connection
        return pyodbc.connect(self.connection_string)

    def initialize(self):
        max_retries = 10
        for attempt in range(1, max_retries + 1):
            try:
                self._ensure_database()
                
                with self._get_connection() as conn:
                    with conn.cursor() as cursor:
                        # Enable preview features for Vector type in SQL Server (optional, if preview/2026 version is used)
                        try:
                            cursor.execute("ALTER DATABASE SCOPED CONFIGURATION SET PREVIEW_FEATURES = ON;")
                            conn.commit()
                        except Exception as ex:
                            logger.warning(f"Optional PREVIEW_FEATURES DDL failed: {ex}")

                        # Check if Documents table exists
                        cursor.execute("SELECT 1 FROM sysobjects WHERE name='Documents' AND xtype='U'")
                        if not cursor.fetchone():
                            cursor.execute("""
                                CREATE TABLE Documents (
                                    id_int   INT IDENTITY(1,1) CONSTRAINT PK_Documents PRIMARY KEY CLUSTERED,
                                    id       VARCHAR(255) NOT NULL CONSTRAINT UQ_Documents_id UNIQUE,
                                    document NVARCHAR(MAX),
                                    metadata NVARCHAR(MAX),
                                    embedding VECTOR(1024)
                                );
                            """)
                            conn.commit()
                            logger.info("Created Documents table.")

                         # Check if IngestionFiles table exists
                        cursor.execute("SELECT 1 FROM sysobjects WHERE name='IngestionFiles' AND xtype='U'")
                        if not cursor.fetchone():
                            cursor.execute("""
                                CREATE TABLE IngestionFiles (
                                    relative_path NVARCHAR(512) NOT NULL CONSTRAINT PK_IngestionFiles PRIMARY KEY,
                                    source NVARCHAR(512) NOT NULL,
                                    last_write_time_utc DATETIME2 NOT NULL,
                                    length BIGINT NOT NULL,
                                    fingerprint NVARCHAR(1024) NOT NULL,
                                    status NVARCHAR(32) NOT NULL,
                                    chunk_count INT NOT NULL CONSTRAINT DF_IngestionFiles_chunk_count DEFAULT 0,
                                    updated_at_utc DATETIME2 NOT NULL,
                                    error NVARCHAR(MAX) NULL
                                );
                            """)
                            conn.commit()
                            logger.info("Created IngestionFiles table.")

                        # Check if RagDocuments table exists
                        cursor.execute("SELECT 1 FROM sysobjects WHERE name='RagDocuments' AND xtype='U'")
                        if not cursor.fetchone():
                            cursor.execute("""
                                CREATE TABLE RagDocuments (
                                    Id                  INT IDENTITY(1,1) CONSTRAINT PK_RagDocuments PRIMARY KEY,
                                    DocumentName        NVARCHAR(500) NOT NULL,
                                    FileName            NVARCHAR(500) NOT NULL,
                                    FilePath            NVARCHAR(1000) NOT NULL,
                                    FileSize            BIGINT NOT NULL,
                                    Category            NVARCHAR(200) NULL,
                                    OwnerDepartment     NVARCHAR(200) NULL,
                                    Description         NVARCHAR(MAX) NULL,
                                    Tags                NVARCHAR(MAX) NULL, -- JSON array of strings
                                    AccessScope         NVARCHAR(50) NOT NULL CONSTRAINT DF_RagDocuments_AccessScope DEFAULT 'Public',
                                    EffectiveDate       DATETIME2 NULL,
                                    ExpirationDate      DATETIME2 NULL,
                                    IngestStatus        NVARCHAR(50) NOT NULL CONSTRAINT DF_RagDocuments_IngestStatus DEFAULT 'Pending',
                                    IngestError         NVARCHAR(MAX) NULL,
                                    ChunkCount          INT NOT NULL CONSTRAINT DF_RagDocuments_ChunkCount DEFAULT 0,
                                    UploadedBy          NVARCHAR(100) NULL,
                                    TenantId            INT NULL,
                                    CreationTime        DATETIME2 NOT NULL CONSTRAINT DF_RagDocuments_CreationTime DEFAULT GETUTCDATE(),
                                    LastModificationTime DATETIME2 NULL
                                );
                            """)
                            conn.commit()
                            logger.info("Created RagDocuments table.")

                        # Check if RagDocumentRoles table exists
                        cursor.execute("SELECT 1 FROM sysobjects WHERE name='RagDocumentRoles' AND xtype='U'")
                        if not cursor.fetchone():
                            cursor.execute("""
                                CREATE TABLE RagDocumentRoles (
                                    Id              INT IDENTITY(1,1) CONSTRAINT PK_RagDocumentRoles PRIMARY KEY,
                                    RagDocumentId   INT NOT NULL CONSTRAINT FK_RagDocumentRoles_RagDocuments REFERENCES RagDocuments(Id) ON DELETE CASCADE,
                                    RoleName        NVARCHAR(200) NOT NULL
                                );
                                CREATE INDEX IX_RagDocumentRoles_RagDocumentId ON RagDocumentRoles(RagDocumentId);
                            """)
                            conn.commit()
                            logger.info("Created RagDocumentRoles table.")

                        # Ensure Full-Text index
                        self._ensure_full_text(cursor, conn)
                        # Ensure Vector index
                        self._ensure_vector_index(cursor, conn)
                        
                logger.info("DB initialized successfully.")
                return
            except Exception as ex:
                if attempt < max_retries:
                    logger.warning(f"Waiting for SQL Server ({attempt}/{max_retries}). Error: {ex}")
                    time.sleep(5)
                else:
                    raise RuntimeError("Could not initialize DB after retries.") from ex

    def _ensure_database(self):
        # Ensure target database exists by connecting to master
        params = {}
        for tok in self.connection_string.split(";"):
            if tok and "=" in tok:
                k, _, v = tok.partition("=")
                params[k.strip()] = v.strip()
        database_name = params.get("Database") or params.get("database") or params.get("Initial Catalog") or params.get("initial catalog")
        
        if not database_name or database_name.lower() in ["master", "tempdb", "model", "msdb"]:
            return

        # Connect to master
        master_conn_str = self.connection_string
        for k, v in params.items():
            if k.lower() in ["database", "initial catalog"]:
                master_conn_str = master_conn_str.replace(f"{k}={v}", f"{k}=master")
                break
                
        try:
            with pyodbc.connect(master_conn_str, autocommit=True) as conn:
                with conn.cursor() as cursor:
                    escaped_name = database_name.replace("'", "''")
                    cursor.execute(f"IF DB_ID(N'{escaped_name}') IS NULL CREATE DATABASE [{database_name.replace(']', ']]')}];")
            logger.info(f"Ensured SQL Server database {database_name} exists.")
        except Exception as ex:
            logger.warning(f"Failed to ensure database exists: {ex}")

    def _ensure_full_text(self, cursor, conn):
        try:
            # Check catalog
            cursor.execute("SELECT 1 FROM sys.fulltext_catalogs WHERE name = 'ftCatalog'")
            if not cursor.fetchone():
                cursor.execute("CREATE FULLTEXT CATALOG ftCatalog AS DEFAULT;")
                conn.commit()
                time.sleep(2)

            # Check index
            cursor.execute("SELECT 1 FROM sys.fulltext_indexes WHERE object_id = OBJECT_ID('Documents')")
            if not cursor.fetchone():
                cursor.execute("""
                    CREATE FULLTEXT INDEX ON Documents(document)
                    KEY INDEX UQ_Documents_id ON ftCatalog
                    WITH CHANGE_TRACKING AUTO;
                """)
                conn.commit()
                time.sleep(2)
        except Exception as ex:
            logger.warning(f"Full-text catalog/index check failed: {ex}. Hybrid search will use fallback search.")

    def _ensure_vector_index(self, cursor, conn):
        try:
            cursor.execute("SELECT 1 FROM sys.indexes WHERE name = 'idx_documents_embedding'")
            if not cursor.fetchone():
                cursor.execute("""
                    CREATE VECTOR INDEX idx_documents_embedding
                    ON Documents(embedding)
                    WITH (METRIC = 'cosine', TYPE = 'diskann');
                """)
                conn.commit()
        except Exception as ex:
            logger.warning(f"Vector Index check failed (diskann index may not be supported or ready): {ex}")

    def delete_documents_for_file(self, relative_path: str):
        # Normalize relative path
        norm_path = relative_path.replace("\\", "/").strip("/")
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM Documents
                    WHERE JSON_VALUE(metadata, '$.relative_path') = ?;
                """, (norm_path,))
                conn.commit()
                logger.info(f"Deleted existing chunks for relative path '{norm_path}'")

    def delete_documents_by_backend_id(self, backend_id: int):
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. First get the relative paths of chunks to delete from IngestionFiles
                cursor.execute("""
                    SELECT DISTINCT JSON_VALUE(metadata, '$.relative_path')
                    FROM Documents
                    WHERE TRY_CAST(JSON_VALUE(metadata, '$.backend_document_id') AS INT) = ?;
                """, (backend_id,))
                paths = [row[0] for row in cursor.fetchall() if row[0]]
                
                # 2. Delete chunks from Documents table
                cursor.execute("""
                    DELETE FROM Documents
                    WHERE TRY_CAST(JSON_VALUE(metadata, '$.backend_document_id') AS INT) = ?;
                """, (backend_id,))
                
                # 3. Clean up IngestionFiles entry for each path
                for path in paths:
                    cursor.execute("DELETE FROM IngestionFiles WHERE relative_path = ?;", (path,))
                    
                conn.commit()
                logger.info(f"Deleted all vector data for backend document id '{backend_id}'")

    def upsert_documents(self, ids: List[str], documents: List[str], metadatas: List[Dict[str, Any]], embeddings: List[List[float]]) -> None:
        if not ids or not documents or not embeddings:
            return

        # Vector dimension guard check
        expected_dims = settings.embedding_dims
        for idx, emb in enumerate(embeddings):
            if len(emb) != expected_dims:
                raise ValueError(f"Vector dimension mismatch at chunk '{ids[idx]}': expected {expected_dims}, got {len(emb)}")

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Create a local temp table for loading
                cursor.execute("""
                    CREATE TABLE #DocumentUpsert (
                        id VARCHAR(255) NOT NULL PRIMARY KEY,
                        document NVARCHAR(MAX),
                        metadata NVARCHAR(MAX),
                        embedding_json NVARCHAR(MAX)
                    );
                """)
                
                # Prepare rows
                rows = []
                for idx, doc_id in enumerate(ids):
                    meta_str = json.dumps(metadatas[idx], ensure_ascii=False)
                    emb_str = json.dumps(embeddings[idx])
                    rows.append((doc_id, documents[idx], meta_str, emb_str))

                # 2. Insert into temp table
                cursor.executemany("""
                    INSERT INTO #DocumentUpsert (id, document, metadata, embedding_json)
                    VALUES (?, ?, ?, ?);
                """, rows)

                # 3. Merge temp table into Documents
                cursor.execute(f"""
                    MERGE Documents AS target
                    USING (
                        SELECT
                            id,
                            document,
                            metadata,
                            CAST(CAST(embedding_json AS VARCHAR(MAX)) AS VECTOR({expected_dims})) AS embedding
                        FROM #DocumentUpsert
                    ) AS source
                    ON (target.id = source.id)
                    WHEN MATCHED THEN
                        UPDATE SET document = source.document, metadata = source.metadata, embedding = source.embedding
                    WHEN NOT MATCHED THEN
                        INSERT (id, document, metadata, embedding)
                        VALUES (source.id, source.document, source.metadata, source.embedding);
                """)
                conn.commit()
                logger.info(f"Upserted {len(documents)} chunks to SQL Server vector DB.")

    def search(self, query: str, query_embedding: List[float], top_k: int, content_kind: Optional[str] = None, user_roles: Optional[str] = None) -> Dict[str, Any]:
        top_k = max(1, min(top_k, settings.search_top_k_max))
        vector_candidate_count = max(top_k, settings.search_vector_candidate_count)
        rrf_constant = settings.search_rrf_constant if settings.search_rrf_constant > 0 else 60
        query_embedding_json = json.dumps(query_embedding)
        
        # Regex or simple check to extract 6+ digit exact keywords
        # C# code uses System.Text.RegularExpressions.Regex.Match(query, @" \d{6,} ").Value
        # Let's match any contiguous 6+ digits in query
        import re
        match = re.search(r'\b\d{6,}\b', query)
        exact_keyword = match.group(0) if match else ""

        sql = """
            WITH FilteredDocuments AS (
                SELECT id, document, metadata, embedding
                FROM Documents
                WHERE (? IS NULL OR JSON_VALUE(metadata, '$.content_kind') = ?)
                  AND (
                      JSON_VALUE(metadata, '$.accessScope') IS NULL 
                      OR JSON_VALUE(metadata, '$.accessScope') = 'Public'
                      OR (
                          JSON_VALUE(metadata, '$.accessScope') = 'Restricted'
                          AND ? IS NOT NULL
                          AND (
                              CHARINDEX('admin', LOWER(?)) > 0
                              OR EXISTS (
                                  SELECT 1 
                                  FROM OPENJSON(metadata, '$.allowedRoles') WITH (role NVARCHAR(100) '$')
                                  WHERE role IN (SELECT value FROM STRING_SPLIT(?, ','))
                              )
                          )
                      )
                  )
            ),
            VectorBase AS (
                SELECT
                    id,
                    document,
                    metadata,
                    VECTOR_DISTANCE('cosine', embedding, CAST(CAST(? AS VARCHAR(MAX)) AS VECTOR(1024))) AS distance
                FROM FilteredDocuments
            ),
            VectorSearch AS (
                SELECT TOP (?)
                    id,
                    document,
                    metadata,
                    distance,
                    ROW_NUMBER() OVER (ORDER BY distance ASC) AS vector_rank
                FROM VectorBase
                ORDER BY distance ASC
            ),
            ExactMatchSearch AS (
                SELECT id, 10000 AS exact_score
                FROM FilteredDocuments
                WHERE ? <> '' AND document LIKE '%' + ? + '%'
            ),
            CandidateIds AS (
                SELECT id FROM VectorSearch
                UNION
                SELECT id FROM ExactMatchSearch
            ),
            RankedScores AS (
                SELECT c.id, d.document, d.metadata, v.distance,
                       v.vector_rank,
                       e.exact_score
                FROM CandidateIds c
                INNER JOIN FilteredDocuments d ON d.id = c.id
                LEFT JOIN VectorSearch v ON v.id = c.id
                LEFT JOIN ExactMatchSearch e ON e.id = c.id
            )
            SELECT TOP (?)
                id, document, metadata, distance,
                (1.0 / (? + ISNULL(vector_rank, 9999))) + ISNULL(exact_score, 0) AS RRF_Score
            FROM RankedScores
            ORDER BY RRF_Score DESC;
        """

        ids = []
        documents = []
        metadatas = []
        distances = []
        citations = []

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                params = (
                    content_kind, content_kind,
                    user_roles, user_roles, user_roles,
                    query_embedding_json,
                    vector_candidate_count,
                    exact_keyword, exact_keyword,
                    top_k,
                    rrf_constant
                )
                cursor.execute(sql, params)
                for row in cursor.fetchall():
                    doc_id, doc_text, meta_json, dist, score = row
                    meta = json.loads(meta_json) if meta_json else {}
                    dist_val = dist if dist is not None else 9999.0
                    
                    ids.append(doc_id)
                    documents.append(doc_text)
                    metadatas.append(meta)
                    distances.append(dist_val)
                    
                    # Build citation dict
                    citations.append({
                        "source": meta.get("source"),
                        "page": meta.get("page") or meta.get("slide"),
                        "chunk_id": doc_id,
                        "score": score
                    })

        # Return SearchResponse-like structure
        return {
            "ids": [ids],
            "documents": [documents],
            "metadatas": [metadatas],
            "distances": [distances],
            "citations": [citations]
        }

    def get_related_chunks(self, source_metadatas: List[Dict[str, Any]], content_kind: str, limit: int, user_roles: Optional[str] = None) -> List[Tuple[str, Dict[str, Any]]]:
        if not source_metadatas or limit <= 0:
            return []

        # Find location anchors
        anchors = []
        for meta in source_metadatas:
            source = meta.get("source")
            if source:
                anchors.append({
                    "source": source,
                    "page": meta.get("page"),
                    "slide": meta.get("slide"),
                    "paragraph_index": meta.get("paragraph_index")
                })
        
        # Unique anchors up to 20
        unique_anchors = []
        seen = set()
        for a in anchors:
            k = (a["source"], a["page"], a["slide"], a["paragraph_index"])
            if k not in seen:
                seen.add(k)
                unique_anchors.append(a)
        unique_anchors = unique_anchors[:20]

        if not unique_anchors:
            return []

        # Build query dynamically
        predicates = []
        params = [content_kind, limit]

        for i, a in enumerate(unique_anchors):
            source_param = a["source"]
            params.append(source_param)
            
            location_parts = []
            if a["page"]:
                location_parts.append("JSON_VALUE(metadata, '$.page') = ?")
                params.append(a["page"])
            if a["slide"]:
                location_parts.append("JSON_VALUE(metadata, '$.slide') = ?")
                params.append(a["slide"])
            if a["paragraph_index"]:
                location_parts.append("JSON_VALUE(metadata, '$.paragraph_index') = ?")
                params.append(a["paragraph_index"])
                
            if location_parts:
                predicates.append(f"(JSON_VALUE(metadata, '$.source') = ? AND ({' OR '.join(location_parts)}))")
            else:
                predicates.append("(JSON_VALUE(metadata, '$.source') = ?)")

        sql = f"""
            SELECT TOP (?) document, metadata
            FROM Documents
            WHERE JSON_VALUE(metadata, '$.content_kind') = ?
              AND ({' OR '.join(predicates)})
              AND (
                  JSON_VALUE(metadata, '$.accessScope') IS NULL 
                  OR JSON_VALUE(metadata, '$.accessScope') = 'Public'
                  OR (
                      JSON_VALUE(metadata, '$.accessScope') = 'Restricted'
                      AND ? IS NOT NULL
                      AND (
                          CHARINDEX('admin', LOWER(?)) > 0
                          OR EXISTS (
                              SELECT 1 
                              FROM OPENJSON(metadata, '$.allowedRoles') WITH (role NVARCHAR(100) '$')
                              WHERE role IN (SELECT value FROM STRING_SPLIT(?, ','))
                          )
                      )
                  )
              )
            ORDER BY id_int ASC;
        """

        # Re-arrange params: top limit first, content_kind second, then predicates params, then role params
        query_params = [limit, content_kind] + params[2:] + [user_roles, user_roles, user_roles]

        results = []
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, query_params)
                for row in cursor.fetchall():
                    doc_text, meta_json = row
                    meta = json.loads(meta_json) if meta_json else {}
                    results.append((doc_text, meta))
        return results

    def get_procedure_chunks_by_action(self, source_metadatas: List[Dict[str, Any]], action_kind: str, limit: int, user_roles: Optional[str] = None) -> List[Tuple[str, Dict[str, Any]]]:
        if not source_metadatas or not action_kind or limit <= 0:
            return []

        # Normalize action_kind (lowercase, etc.)
        normalized_action = action_kind.strip().lower()
        if not normalized_action:
            return []

        sources = list(set(meta.get("source") for meta in source_metadatas if meta.get("source")))[:10]
        if not sources:
            return []

        # Map 'phe_duyet' etc. legacy mapping
        legacy_action = "phe_duyet" if normalized_action == "duyet" else normalized_action

        # Build placeholders for IN clause
        placeholders = ", ".join("?" for _ in sources)
        sql = f"""
            SELECT TOP (?) document, metadata
            FROM Documents
            WHERE JSON_VALUE(metadata, '$.content_kind') = 'instruction_text'
              AND JSON_VALUE(metadata, '$.instruction_role') = 'procedure_steps'
              AND (JSON_VALUE(metadata, '$.action_kind') = ? OR JSON_VALUE(metadata, '$.action_kind') = ?)
              AND JSON_VALUE(metadata, '$.source') IN ({placeholders})
              AND (
                  JSON_VALUE(metadata, '$.accessScope') IS NULL 
                  OR JSON_VALUE(metadata, '$.accessScope') = 'Public'
                  OR (
                      JSON_VALUE(metadata, '$.accessScope') = 'Restricted'
                      AND ? IS NOT NULL
                      AND (
                          CHARINDEX('admin', LOWER(?)) > 0
                          OR EXISTS (
                              SELECT 1 
                              FROM OPENJSON(metadata, '$.allowedRoles') WITH (role NVARCHAR(100) '$')
                              WHERE role IN (SELECT value FROM STRING_SPLIT(?, ','))
                          )
                      )
                  )
              )
            ORDER BY JSON_VALUE(metadata, '$.source') ASC,
                     ISNULL(TRY_CONVERT(int, JSON_VALUE(metadata, '$.chunkIndex')), TRY_CONVERT(int, JSON_VALUE(metadata, '$.chunk_index'))) ASC,
                     id_int ASC;
        """

        params = [limit, normalized_action, legacy_action] + sources + [user_roles, user_roles, user_roles]
        results = []
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                for row in cursor.fetchall():
                    doc_text, meta_json = row
                    meta = json.loads(meta_json) if meta_json else {}
                    results.append((doc_text, meta))
        return results

    # Ingestion State methods
    def get_all_ingestion_states(self) -> Dict[str, Dict[str, Any]]:
        states = {}
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT relative_path, source, last_write_time_utc, length, fingerprint, status, chunk_count, updated_at_utc, error FROM IngestionFiles;")
                for row in cursor.fetchall():
                    rel_path = row[0]
                    # Normalize key
                    norm_key = rel_path.replace("\\", "/").strip("/").lower()
                    states[norm_key] = {
                        "relative_path": row[0],
                        "source": row[1],
                        "last_write_time_utc": row[2],
                        "length": row[3],
                        "fingerprint": row[4],
                        "status": row[5],
                        "chunk_count": row[6],
                        "updated_at_utc": row[7],
                        "error": row[8]
                    }
        return states

    def get_ingestion_state(self, relative_path: str) -> Optional[Dict[str, Any]]:
        norm_path = relative_path.replace("\\", "/").strip("/")
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT relative_path, source, last_write_time_utc, length, fingerprint, status, chunk_count, updated_at_utc, error FROM IngestionFiles WHERE relative_path = ?;", (norm_path,))
                row = cursor.fetchone()
                if row:
                    return {
                        "relative_path": row[0],
                        "source": row[1],
                        "last_write_time_utc": row[2],
                        "length": row[3],
                        "fingerprint": row[4],
                        "status": row[5],
                        "chunk_count": row[6],
                        "updated_at_utc": row[7],
                        "error": row[8]
                    }
        return None

    def mark_ingestion_started(self, relative_path: str, source: str, last_write_time_utc, length: int, fingerprint: str):
        norm_path = relative_path.replace("\\", "/").strip("/")
        from datetime import datetime
        now = datetime.utcnow()

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                # Merge logic
                cursor.execute("""
                    MERGE IngestionFiles AS target
                    USING (
                        SELECT
                            ? AS relative_path,
                            ? AS source,
                            ? AS last_write_time_utc,
                            ? AS length,
                            ? AS fingerprint,
                            'Processing' AS status,
                            ? AS updated_at_utc
                    ) AS source
                    ON (target.relative_path = source.relative_path)
                    WHEN MATCHED THEN
                        UPDATE SET 
                            source = source.source,
                            last_write_time_utc = source.last_write_time_utc,
                            length = source.length,
                            fingerprint = source.fingerprint,
                            status = source.status,
                            updated_at_utc = source.updated_at_utc,
                            chunk_count = 0,
                            error = NULL
                    WHEN NOT MATCHED THEN
                        INSERT (relative_path, source, last_write_time_utc, length, fingerprint, status, updated_at_utc)
                        VALUES (source.relative_path, source.source, source.last_write_time_utc, source.length, source.fingerprint, source.status, source.updated_at_utc);
                """, (norm_path, source, last_write_time_utc, length, fingerprint, now))
                conn.commit()

    def mark_ingestion_completed(self, relative_path: str, chunk_count: int):
        norm_path = relative_path.replace("\\", "/").strip("/")
        from datetime import datetime
        now = datetime.utcnow()
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE IngestionFiles
                    SET status = 'Completed', chunk_count = ?, updated_at_utc = ?, error = NULL
                    WHERE relative_path = ?;
                """, (chunk_count, now, norm_path))
                conn.commit()

    def mark_ingestion_failed(self, relative_path: str, error_msg: str):
        norm_path = relative_path.replace("\\", "/").strip("/")
        from datetime import datetime
        now = datetime.utcnow()
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE IngestionFiles
                    SET status = 'Failed', updated_at_utc = ?, error = ?
                    WHERE relative_path = ?;
                """, (now, error_msg, norm_path))
                conn.commit()

    # === RagDocuments CRUD Helpers ===
    def create_rag_document(
        self,
        document_name: str,
        file_name: str,
        file_path: str,
        file_size: int,
        category: Optional[str],
        owner_department: Optional[str],
        description: Optional[str],
        tags: Optional[str],
        access_scope: str,
        effective_date: Optional[str],
        expiration_date: Optional[str],
        uploaded_by: Optional[str],
        tenant_id: Optional[int],
        allowed_roles: List[str]
    ) -> int:
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Insert metadata
                cursor.execute("""
                    INSERT INTO RagDocuments (DocumentName, FileName, FilePath, FileSize, Category, OwnerDepartment, Description, Tags, AccessScope, EffectiveDate, ExpirationDate, IngestStatus, UploadedBy, TenantId)
                    OUTPUT INSERTED.Id
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Processing', ?, ?);
                """, (
                    document_name, file_name, file_path, file_size, category, owner_department, description, tags, access_scope,
                    effective_date, expiration_date, uploaded_by, tenant_id
                ))
                doc_id = int(cursor.fetchone()[0])
                
                # 2. Insert roles if Restricted
                if access_scope == "Restricted" and allowed_roles:
                    for role in allowed_roles:
                        cursor.execute("""
                            INSERT INTO RagDocumentRoles (RagDocumentId, RoleName)
                            VALUES (?, ?);
                        """, (doc_id, role))
                
                conn.commit()
                return doc_id

    def get_rag_document(self, doc_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT Id, DocumentName, FileName, FilePath, FileSize, Category, OwnerDepartment, Description, Tags, AccessScope, EffectiveDate, ExpirationDate, IngestStatus, IngestError, ChunkCount, UploadedBy, TenantId, CreationTime
                    FROM RagDocuments WHERE Id = ?;
                """, (doc_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "document_name": row[1],
                        "file_name": row[2],
                        "file_path": row[3],
                        "file_size": row[4],
                        "category": row[5],
                        "owner_department": row[6],
                        "description": row[7],
                        "tags": row[8],
                        "access_scope": row[9],
                        "effective_date": row[10].isoformat() if row[10] else None,
                        "expiration_date": row[11].isoformat() if row[11] else None,
                        "ingest_status": row[12],
                        "ingest_error": row[13],
                        "chunk_count": row[14],
                        "uploaded_by": row[15],
                        "tenant_id": row[16],
                        "creation_time": (row[17].isoformat() + "Z") if row[17] else None
                    }
        return None

    def get_rag_documents_list(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT Id, DocumentName, FileName, FilePath, FileSize, Category, OwnerDepartment, Description, Tags, AccessScope, EffectiveDate, ExpirationDate, IngestStatus, IngestError, ChunkCount, UploadedBy, TenantId, CreationTime
                    FROM RagDocuments ORDER BY CreationTime DESC;
                """)
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "id": row[0],
                        "document_name": row[1],
                        "file_name": row[2],
                        "file_path": row[3],
                        "file_size": row[4],
                        "category": row[5],
                        "owner_department": row[6],
                        "description": row[7],
                        "tags": row[8],
                        "access_scope": row[9],
                        "effective_date": row[10].isoformat() if row[10] else None,
                        "expiration_date": row[11].isoformat() if row[11] else None,
                        "ingest_status": row[12],
                        "ingest_error": row[13],
                        "chunk_count": row[14],
                        "uploaded_by": row[15],
                        "tenant_id": row[16],
                        "creation_time": (row[17].isoformat() + "Z") if row[17] else None
                    })
                return results

    def get_rag_document_roles(self, doc_id: int) -> List[str]:
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT RoleName FROM RagDocumentRoles WHERE RagDocumentId = ?;", (doc_id,))
                return [row[0] for row in cursor.fetchall()]

    def update_rag_document_status(self, doc_id: int, status: str, chunk_count: int, error: Optional[str] = None):
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE RagDocuments
                    SET IngestStatus = ?, ChunkCount = ?, IngestError = ?, LastModificationTime = GETUTCDATE()
                    WHERE Id = ?;
                """, (status, chunk_count, error, doc_id))
                conn.commit()

    def delete_rag_document(self, doc_id: int) -> Optional[str]:
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Fetch file_path first before deleting
                cursor.execute("SELECT FilePath FROM RagDocuments WHERE Id = ?;", (doc_id,))
                row = cursor.fetchone()
                file_path = row[0] if row else None
                
                if file_path:
                    # 2. Get relative_path from Documents before deleting
                    cursor.execute("""
                        SELECT DISTINCT JSON_VALUE(metadata, '$.relative_path')
                        FROM Documents
                        WHERE JSON_VALUE(metadata, '$.backend_document_id') = ?
                           OR JSON_VALUE(metadata, '$.documentId') = ?;
                    """, (str(doc_id), str(doc_id)))
                    paths = [r[0] for r in cursor.fetchall() if r[0]]

                    # 3. Delete from IngestionFiles
                    if paths:
                        for path in paths:
                            cursor.execute("DELETE FROM IngestionFiles WHERE relative_path = ?;", (path,))

                    # 4. Delete metadata (cascade delete will purge RagDocumentRoles)
                    cursor.execute("DELETE FROM RagDocuments WHERE Id = ?;", (doc_id,))

                    # 5. Delete related vector chunks in Documents table
                    cursor.execute("""
                        DELETE FROM Documents
                        WHERE JSON_VALUE(metadata, '$.backend_document_id') = ?
                           OR JSON_VALUE(metadata, '$.documentId') = ?;
                    """, (str(doc_id), str(doc_id)))
                    conn.commit()
                return file_path
