from abc import ABC, abstractmethod
from typing import List, AsyncGenerator
from app.ingestion.text_splitter import IngestedDocument

class BaseDocumentParser(ABC):
    @abstractmethod
    def can_parse(self, extension: str) -> bool:
        pass

    @abstractmethod
    async def parse_async(self, file_path: str, file_name: str) -> List[IngestedDocument]:
        pass

    async def parse_stream_async(self, file_path: str, file_name: str) -> AsyncGenerator[IngestedDocument, None]:
        docs = await self.parse_async(file_path, file_name)
        for doc in docs:
            yield doc
class DocumentParser:
    def __init__(self, parsers: List[BaseDocumentParser]):
        self.parsers = parsers

    def get_parser(self, extension: str) -> BaseDocumentParser:
        for parser in self.parsers:
            if parser.can_parse(extension):
                return parser
        raise ValueError(f"No parser available for extension '{extension}'")
