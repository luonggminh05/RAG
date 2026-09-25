from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc)
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Unicode,
    UnicodeText,
)
from sqlalchemy.orm import relationship

from app.core.database import Base

class RagDocument(Base):
    __tablename__ = "RagDocuments"

    id = Column("Id", Integer, primary_key=True, autoincrement=True)
    document_name = Column("DocumentName", Unicode(500), nullable=False)
    file_name = Column("FileName", Unicode(500), nullable=False)
    file_path = Column("FilePath", Unicode(1000), nullable=False)
    file_size = Column("FileSize", BigInteger, nullable=False)
    category = Column("Category", Unicode(200), nullable=True)
    owner_department = Column("OwnerDepartment", Unicode(200), nullable=True)
    description = Column("Description", UnicodeText, nullable=True)
    tags = Column("Tags", UnicodeText, nullable=True)
    access_scope = Column("AccessScope", String(50), nullable=False, default="Public")
    effective_date = Column("EffectiveDate", DateTime, nullable=True)
    expiration_date = Column("ExpirationDate", DateTime, nullable=True)
    ingest_status = Column("IngestStatus", String(50), nullable=False, default="Pending")
    ingest_error = Column("IngestError", UnicodeText, nullable=True)
    chunk_count = Column("ChunkCount", Integer, nullable=False, default=0)
    uploaded_by = Column("UploadedBy", Unicode(100), nullable=True)
    tenant_id = Column("TenantId", Integer, nullable=True)
    creation_time = Column("CreationTime", DateTime, nullable=False, default=utc_now)
    last_modification_time = Column("LastModificationTime", DateTime, nullable=True)

    roles = relationship("RagDocumentRole", back_populates="document", cascade="all, delete-orphan")


class RagDocumentRole(Base):
    __tablename__ = "RagDocumentRoles"

    id = Column("Id", Integer, primary_key=True, autoincrement=True)
    rag_document_id = Column("RagDocumentId", Integer, ForeignKey("RagDocuments.Id", ondelete="CASCADE"), nullable=False)
    role_name = Column("RoleName", Unicode(200), nullable=False)

    document = relationship("RagDocument", back_populates="roles")


Index("IX_RagDocumentRoles_RagDocumentId", RagDocumentRole.rag_document_id)


class IngestionTask(Base):
    __tablename__ = "IngestionTasks"

    id = Column("Id", Integer, primary_key=True, autoincrement=True)
    task_id = Column("TaskId", String(36), unique=True, nullable=False, index=True)
    backend_document_id = Column("BackendDocumentId", Integer, nullable=True)
    file_name = Column("FileName", Unicode(500), nullable=False)
    status = Column("Status", String(50), nullable=False, default="PENDING")
    progress_percent = Column("ProgressPercent", Integer, nullable=False, default=0)
    chunk_count = Column("ChunkCount", Integer, nullable=False, default=0)
    error_message = Column("ErrorMessage", UnicodeText, nullable=True)
    created_at = Column("CreatedAt", DateTime, nullable=False, default=utc_now)
    updated_at = Column("UpdatedAt", DateTime, nullable=False, default=utc_now, onupdate=utc_now)
