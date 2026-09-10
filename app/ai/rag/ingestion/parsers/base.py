from abc import ABC, abstractmethod
from typing import List, Dict, Any, AsyncGenerator
from dataclasses import dataclass, field

@dataclass
class IngestedDocument:
    page_content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_content": self.page_content,
            "metadata": self.metadata
        }

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

class DocumentParserRegistry:
    def __init__(self, parsers: List[BaseDocumentParser]):
        self.parsers = parsers

    def get_parser(self, extension: str) -> BaseDocumentParser:
        for parser in self.parsers:
            if parser.can_parse(extension):
                return parser
        raise ValueError(f"No parser available for extension '{extension}'")
