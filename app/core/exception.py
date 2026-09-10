class DomainException(Exception):
    """Base exception cho các lỗi nghiệp vụ trong hệ thống."""
    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class DocumentNotFoundException(DomainException):
    def __init__(self, doc_id: int | str):
        super().__init__(f"Document with ID {doc_id} not found.", code="DOCUMENT_NOT_FOUND")


class IngestionFailedException(DomainException):
    def __init__(self, file_name: str, reason: str):
        super().__init__(f"Ingestion failed for file '{file_name}': {reason}", code="INGESTION_FAILED")


class GuardrailViolationException(DomainException):
    def __init__(self, reason: str):
        super().__init__(f"Guardrail violation: {reason}", code="GUARDRAIL_VIOLATION")
