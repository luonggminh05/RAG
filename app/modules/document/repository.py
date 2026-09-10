import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import pyodbc
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.modules.document.model import RagDocument, RagDocumentRole, IngestionTask
from app.ai.rag.citation.helper import CitationHelper
from app.shared.utils.action_classifier import ActionKindClassifier

logger = logging.getLogger(__name__)

class DocumentRepository:
    def __init__(self):
        self.dims = getattr(settings, "embedding_dims", 1024)

    def _get_raw_connection(self):
        return engine.raw_connection()

    # --- Schema Initialization ---
    def initialize(self) -> None:
        """Khởi tạo bảng Documents (Vector & FTS) trong CSDL SQL Server."""
        try:
            conn = self._get_raw_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM sys.tables WHERE name = 'Documents'")
            exists = cursor.fetchone()

            if not exists:
                logger.info("[DB] Table 'Documents' not found. Creating table...")
                cursor.execute(f"""
                CREATE TABLE Documents (
                    Id NVARCHAR(255) NOT NULL PRIMARY KEY,
                    Document NVARCHAR(MAX) NOT NULL,
                    Metadata NVARCHAR(MAX) NULL,
                    Embedding VECTOR({self.dims}) NOT NULL,
                    ParentChunkId NVARCHAR(255) NULL
                );
                """)
                conn.commit()
                logger.info("[OK] Table 'Documents' created successfully.")
            else:
                try:
                    cursor.execute("IF COL_LENGTH('Documents', 'ParentChunkId') IS NULL ALTER TABLE Documents ADD ParentChunkId NVARCHAR(255) NULL;")
                    conn.commit()
                except Exception:
                    pass

            # Full Text Search Catalog & Index
            cursor.execute("SELECT 1 FROM sys.fulltext_catalogs WHERE name = 'RagFullTextCatalog'")
            if not cursor.fetchone():
                try:
                    cursor.execute("CREATE FULLTEXT CATALOG RagFullTextCatalog AS DEFAULT;")
                    conn.commit()
                except Exception as ex:
                    logger.warning(f"[DB] FullText Catalog creation warning: {ex}")

            cursor.execute("""
                SELECT 1 FROM sys.fulltext_indexes fi
                JOIN sys.tables t ON fi.object_id = t.object_id
                WHERE t.name = 'Documents'
            """)
            if not cursor.fetchone():
                try:
                    cursor.execute("CREATE FULLTEXT INDEX ON Documents(Document) KEY INDEX PK__Document__3214EC07... ON RagFullTextCatalog;")
                except Exception:
                    # Generic create fulltext index
                    try:
                        cursor.execute("""
                            DECLARE @pk_name NVARCHAR(128);
                            SELECT @pk_name = name FROM sys.key_constraints WHERE parent_object_id = OBJECT_ID('Documents') AND type = 'PK';
                            IF @pk_name IS NOT NULL
                            BEGIN
                                EXEC('CREATE FULLTEXT INDEX ON Documents(Document) KEY INDEX ' + @pk_name + ' ON RagFullTextCatalog;');
                            END
                        """)
                        conn.commit()
                    except Exception as ex:
                        logger.warning(f"[DB] FullText Index creation warning: {ex}")

            cursor.close()
            conn.close()
        except Exception as ex:
            logger.warning(f"[DB] DocumentRepository.initialize encountered: {ex}")

    # --- RagDocuments Metadata ORM CRUD ---
    def create_rag_document(
        self,
        document_name: str,
        file_name: str,
        file_path: str,
        file_size: int,
        category: Optional[str] = None,
        owner_department: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[str] = None,
        access_scope: str = "Public",
        effective_date: Optional[str] = None,
        expiration_date: Optional[str] = None,
        uploaded_by: Optional[str] = None,
        tenant_id: Optional[int] = None,
        allowed_roles: Optional[List[str]] = None,
    ) -> int:
        allowed_roles = allowed_roles or []
        db: Session = SessionLocal()
        try:
            doc = RagDocument(
                document_name=document_name,
                file_name=file_name,
                file_path=file_path,
                file_size=file_size,
                category=category,
                owner_department=owner_department,
                description=description,
                tags=tags,
                access_scope=access_scope,
                effective_date=datetime.fromisoformat(effective_date) if effective_date else None,
                expiration_date=datetime.fromisoformat(expiration_date) if expiration_date else None,
                uploaded_by=uploaded_by,
                tenant_id=tenant_id,
                ingest_status="Pending",
                creation_time=datetime.now(timezone.utc),
            )
            db.add(doc)
            db.flush()

            if access_scope.lower() == "restricted" and allowed_roles:
                for role in allowed_roles:
                    if role.strip():
                        db.add(RagDocumentRole(rag_document_id=doc.id, role_name=role.strip()))

            db.commit()
            return doc.id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_rag_document(self, doc_id: int) -> Optional[Dict[str, Any]]:
        db: Session = SessionLocal()
        try:
            doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
            if not doc:
                return None
            return {
                "id": doc.id,
                "document_name": doc.document_name,
                "file_name": doc.file_name,
                "file_path": doc.file_path,
                "file_size": doc.file_size,
                "category": doc.category,
                "owner_department": doc.owner_department,
                "description": doc.description,
                "tags": doc.tags,
                "access_scope": doc.access_scope,
                "effective_date": doc.effective_date.isoformat() if doc.effective_date else None,
                "expiration_date": doc.expiration_date.isoformat() if doc.expiration_date else None,
                "ingest_status": doc.ingest_status,
                "ingest_error": doc.ingest_error,
                "chunk_count": doc.chunk_count,
                "uploaded_by": doc.uploaded_by,
                "tenant_id": doc.tenant_id,
                "creation_time": doc.creation_time.isoformat() if doc.creation_time else None,
                "allowed_roles": [r.role_name for r in doc.roles],
            }
        finally:
            db.close()

    def get_rag_documents_list(self) -> List[Dict[str, Any]]:
        db: Session = SessionLocal()
        try:
            docs = db.query(RagDocument).order_by(RagDocument.id.desc()).all()
            result = []
            for doc in docs:
                result.append({
                    "id": doc.id,
                    "document_name": doc.document_name,
                    "file_name": doc.file_name,
                    "file_path": doc.file_path,
                    "file_size": doc.file_size,
                    "category": doc.category,
                    "owner_department": doc.owner_department,
                    "description": doc.description,
                    "tags": doc.tags,
                    "access_scope": doc.access_scope,
                    "effective_date": doc.effective_date.isoformat() if doc.effective_date else None,
                    "expiration_date": doc.expiration_date.isoformat() if doc.expiration_date else None,
                    "ingest_status": doc.ingest_status,
                    "ingest_error": doc.ingest_error,
                    "chunk_count": doc.chunk_count,
                    "uploaded_by": doc.uploaded_by,
                    "tenant_id": doc.tenant_id,
                    "creation_time": doc.creation_time.isoformat() if doc.creation_time else None,
                    "allowed_roles": [r.role_name for r in doc.roles],
                })
            return result
        finally:
            db.close()

    def get_rag_document_roles(self, doc_id: int) -> List[str]:
        db: Session = SessionLocal()
        try:
            roles = db.query(RagDocumentRole).filter(RagDocumentRole.rag_document_id == doc_id).all()
            return [r.role_name for r in roles]
        finally:
            db.close()

    def update_rag_document_status(
        self, doc_id: int, status: str, chunk_count: int = 0, error: Optional[str] = None
    ) -> None:
        db: Session = SessionLocal()
        try:
            doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
            if doc:
                doc.ingest_status = status
                if chunk_count > 0:
                    doc.chunk_count = chunk_count
                doc.ingest_error = error
                doc.last_modification_time = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def update_rag_document(
        self,
        doc_id: int,
        document_name: Optional[str] = None,
        category: Optional[str] = None,
        access_scope: Optional[str] = None,
        allowed_roles: Optional[List[str]] = None,
    ) -> None:
        db: Session = SessionLocal()
        try:
            doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
            if doc:
                if document_name:
                    doc.document_name = document_name
                if category:
                    doc.category = category
                if access_scope:
                    doc.access_scope = access_scope

                if allowed_roles is not None:
                    db.query(RagDocumentRole).filter(RagDocumentRole.rag_document_id == doc_id).delete()
                    if (access_scope or doc.access_scope).lower() == "restricted":
                        for r in allowed_roles:
                            if r.strip():
                                db.add(RagDocumentRole(rag_document_id=doc_id, role_name=r.strip()))

                doc.last_modification_time = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def delete_rag_document(self, doc_id: int) -> Optional[str]:
        file_path = None
        db: Session = SessionLocal()
        try:
            doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
            if doc:
                file_path = doc.file_path
                db.delete(doc)
                db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        return file_path

    # --- Ingestion Tasks CRUD ---
    def create_ingestion_task(self, task_id: str, file_name: str, backend_document_id: Optional[int] = None) -> None:
        db: Session = SessionLocal()
        try:
            task = IngestionTask(
                task_id=task_id,
                file_name=file_name,
                backend_document_id=backend_document_id,
                status="PENDING",
                progress_percent=0,
                chunk_count=0,
            )
            db.add(task)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_ingestion_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        db: Session = SessionLocal()
        try:
            t = db.query(IngestionTask).filter(IngestionTask.task_id == task_id).first()
            if not t:
                return None
            return {
                "id": t.id,
                "task_id": t.task_id,
                "file_name": t.file_name,
                "backend_document_id": t.backend_document_id,
                "status": t.status,
                "progress_percent": t.progress_percent,
                "chunk_count": t.chunk_count,
                "error_message": t.error_message,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
        finally:
            db.close()

    def update_ingestion_task(
        self,
        task_id: str,
        status: str,
        progress_percent: int,
        chunk_count: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        db: Session = SessionLocal()
        try:
            t = db.query(IngestionTask).filter(IngestionTask.task_id == task_id).first()
            if t:
                t.status = status
                t.progress_percent = progress_percent
                if chunk_count is not None:
                    t.chunk_count = chunk_count
                if error_message is not None:
                    t.error_message = error_message
                t.updated_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    # --- Vector & Chunks CRUD ---
    def delete_documents_by_backend_id(self, backend_id: int, file_name: Optional[str] = None) -> None:
        conn = self._get_raw_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM Documents WHERE JSON_VALUE(Metadata, '$.backend_document_id') = ? OR JSON_VALUE(Metadata, '$.backendId') = ?",
                str(backend_id), str(backend_id)
            )
            if file_name:
                cursor.execute(
                    "DELETE FROM Documents WHERE JSON_VALUE(Metadata, '$.source') = ?",
                    file_name
                )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def delete_documents_for_file(self, file_name: str) -> None:
        conn = self._get_raw_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM Documents WHERE JSON_VALUE(Metadata, '$.source') = ?",
                file_name
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def upsert_documents(
        self,
        ids: List[str],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        embeddings: List[List[float]],
        parent_chunk_ids: Optional[List[Optional[str]]] = None,
    ) -> None:
        if not ids:
            return
        conn = self._get_raw_connection()
        cursor = conn.cursor()
        try:
            sql = """
            MERGE INTO Documents AS target
            USING (VALUES (?, ?, ?, CAST(? AS VECTOR(?)), ?)) AS source (Id, Document, Metadata, Embedding, ParentChunkId)
            ON target.Id = source.Id
            WHEN MATCHED THEN
                UPDATE SET target.Document = source.Document,
                           target.Metadata = source.Metadata,
                           target.Embedding = source.Embedding,
                           target.ParentChunkId = source.ParentChunkId
            WHEN NOT MATCHED THEN
                INSERT (Id, Document, Metadata, Embedding, ParentChunkId)
                VALUES (source.Id, source.Document, source.Metadata, source.Embedding, source.ParentChunkId);
            """
            for i in range(len(ids)):
                emb_str = json.dumps(embeddings[i])
                meta_item = metadatas[i] if metadatas and i < len(metadatas) else {}
                meta_str = json.dumps(meta_item, ensure_ascii=False) if meta_item else "{}"

                parent_id = None
                if parent_chunk_ids and i < len(parent_chunk_ids):
                    parent_id = parent_chunk_ids[i]
                elif isinstance(meta_item, dict):
                    parent_id = meta_item.get("parent_chunk_id") or meta_item.get("ParentChunkId")

                cursor.execute(sql, ids[i], documents[i], meta_str, emb_str, self.dims, parent_id)
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    # --- True Hybrid Search (Vector + FTS + RRF + RBAC 2 Lớp) ---
    def search(
        self,
        query: str,
        query_embedding: List[float],
        top_k: int = 5,
        content_kind: Optional[str] = None,
        user_roles: Optional[str] = None,
        user_department: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = self._get_raw_connection()
        cursor = conn.cursor()
        try:
            embedding_json = json.dumps(query_embedding)
            parsed_roles: List[str] = []
            if user_roles:
                parsed_roles = [r.strip() for r in user_roles.split(",") if r.strip()]

            # Build RBAC WHERE Clause
            # Document accessible if:
            # 1. AccessScope is Public (or missing)
            # 2. AccessScope is Restricted AND user has overlapping role in allowedRoles JSON array
            rbac_filter_sql = ""
            is_admin = any(r.lower() == "admin" for r in parsed_roles)
            if is_admin:
                # Admin has full access to all Public and Restricted documents
                rbac_filter_sql = ""
            elif parsed_roles:
                roles_json = json.dumps(parsed_roles, ensure_ascii=False)
                rbac_filter_sql = f"""
                AND (
                    JSON_VALUE(Metadata, '$.accessScope') IS NULL 
                    OR JSON_VALUE(Metadata, '$.accessScope') = 'Public'
                    OR (
                        JSON_VALUE(Metadata, '$.accessScope') = 'Restricted'
                        AND EXISTS (
                            SELECT 1 
                            FROM OPENJSON(Metadata, '$.allowedRoles') AS doc_roles
                            CROSS JOIN OPENJSON(N'{roles_json}') AS user_roles
                            WHERE LOWER(doc_roles.value) = LOWER(user_roles.value)
                        )
                    )
                )
                """
            else:
                rbac_filter_sql = """
                AND (
                    JSON_VALUE(Metadata, '$.accessScope') IS NULL 
                    OR JSON_VALUE(Metadata, '$.accessScope') = 'Public'
                )
                """

            # Vector Search SQL
            vector_k = getattr(settings, "search_vector_candidate_count", 200)
            vector_sql = f"""
            SELECT TOP ({vector_k})
                Id,
                Document,
                Metadata,
                VECTOR_DISTANCE('cosine', Embedding, CAST(? AS VECTOR({self.dims}))) AS Distance,
                ParentChunkId
            FROM Documents
            WHERE 1=1
            {rbac_filter_sql}
            ORDER BY Distance ASC
            """

            cursor.execute(vector_sql, embedding_json)
            vector_rows = cursor.fetchall()

            # Full-Text Search SQL
            fts_rows = []
            if getattr(settings, "fts_enabled", True) and query.strip():
                try:
                    # Clean search query for CONTAINSTABLE
                    clean_fts_query = re.sub(r'[^\w\s]', ' ', query).strip()
                    words = [w for w in clean_fts_query.split() if len(w) > 1]
                    if words:
                        fts_expr = f'"{words[0]}*"' if len(words) == 1 else ' OR '.join(f'"{w}*"' for w in words[:6])
                        fts_sql = f"""
                        SELECT TOP ({vector_k})
                            d.Id,
                            d.Document,
                            d.Metadata,
                            ft.[RANK] AS FtsRank,
                            d.ParentChunkId
                        FROM Documents d
                        INNER JOIN CONTAINSTABLE(Documents, Document, ?) AS ft ON d.Id = ft.[KEY]
                        WHERE 1=1
                        {rbac_filter_sql.replace("Metadata", "d.Metadata")}
                        ORDER BY ft.[RANK] DESC
                        """
                        cursor.execute(fts_sql, fts_expr)
                        fts_rows = cursor.fetchall()
                except Exception as ex:
                    logger.debug(f"[FTS] Fallback or FTS not available: {ex}")

            # RRF Fusion
            rrf_k = getattr(settings, "search_rrf_constant", 60)
            weight_vec = getattr(settings, "rrf_vector_weight", 0.6)
            weight_fts = getattr(settings, "rrf_fts_weight", 0.4)

            scores: Dict[str, float] = {}
            doc_map: Dict[str, Tuple[str, Dict[str, Any], float, Optional[str]]] = {}

            # Vector RRF
            for rank, row in enumerate(vector_rows, 1):
                doc_id = str(row[0])
                doc_text = str(row[1])
                meta_val = json.loads(row[2]) if row[2] else {}
                dist = float(row[3])
                parent_chunk_id = str(row[4]) if len(row) > 4 and row[4] else (meta_val.get("parent_chunk_id") or meta_val.get("ParentChunkId"))
                doc_map[doc_id] = (doc_text, meta_val, dist, parent_chunk_id)
                scores[doc_id] = scores.get(doc_id, 0.0) + weight_vec * (1.0 / (rrf_k + rank))

            # FTS RRF
            for rank, row in enumerate(fts_rows, 1):
                doc_id = str(row[0])
                doc_text = str(row[1])
                meta_val = json.loads(row[2]) if row[2] else {}
                parent_chunk_id = str(row[4]) if len(row) > 4 and row[4] else (meta_val.get("parent_chunk_id") or meta_val.get("ParentChunkId"))
                if doc_id not in doc_map:
                    doc_map[doc_id] = (doc_text, meta_val, 1.0, parent_chunk_id)
                scores[doc_id] = scores.get(doc_id, 0.0) + weight_fts * (1.0 / (rrf_k + rank))

            # Sort by RRF score descending
            sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

            # Resolve parent chunks for hierarchical chunking
            parent_ids_to_fetch = set()
            for doc_id, _ in sorted_items:
                doc_text, meta, dist, parent_chunk_id = doc_map[doc_id]
                if not meta.get("parent_content") and parent_chunk_id:
                    parent_ids_to_fetch.add(parent_chunk_id)

            parent_docs_map: Dict[str, str] = {}
            if parent_ids_to_fetch:
                try:
                    placeholders = ", ".join("?" for _ in parent_ids_to_fetch)
                    parent_sql = f"SELECT Id, Document FROM Documents WHERE Id IN ({placeholders})"
                    cursor.execute(parent_sql, *list(parent_ids_to_fetch))
                    for p_row in cursor.fetchall():
                        parent_docs_map[str(p_row[0])] = str(p_row[1])
                except Exception as ex:
                    logger.warning(f"[PARENT_CHUNK] Could not fetch parent chunks: {ex}")

            ids_list = []
            docs_list = []
            metas_list = []
            dists_list = []
            cits_list = []

            for doc_id, score in sorted_items:
                doc_text, meta, dist, parent_chunk_id = doc_map[doc_id]
                parent_text = meta.get("parent_content") or (parent_docs_map.get(parent_chunk_id) if parent_chunk_id else None)

                if parent_text and str(parent_text).strip():
                    effective_text = str(parent_text).strip()
                    is_hierarchical = True
                else:
                    effective_text = doc_text
                    is_hierarchical = False

                ids_list.append(doc_id)
                docs_list.append(effective_text)
                metas_list.append(meta)
                dists_list.append(dist)

                meta_copy = dict(meta)
                meta_copy["chunk_id"] = doc_id
                meta_copy["score"] = score
                if parent_chunk_id:
                    meta_copy["parent_chunk_id"] = parent_chunk_id

                # If hierarchical, keep child_content in metadata for citation/debugging
                if is_hierarchical:
                    meta_copy["child_content"] = doc_text
                    meta_copy["parent_content"] = effective_text

                cits_list.append(meta_copy)

            full_citations = CitationHelper.build_full_citations(cits_list)

            return {
                "ids": [ids_list],
                "documents": [docs_list],
                "metadatas": [metas_list],
                "distances": [dists_list],
                "citations": [full_citations],
            }
        finally:
            cursor.close()
            conn.close()
