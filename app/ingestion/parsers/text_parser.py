import anyio
from typing import List
from app.ingestion.parsers.base import BaseDocumentParser
from app.ingestion.text_splitter import IngestedDocument

class TextParser(BaseDocumentParser):
    def can_parse(self, extension: str) -> bool:
        return extension.lower() in [".txt", ".md"]

    async def parse_async(self, file_path: str, file_name: str) -> List[IngestedDocument]:
        # Read file asynchronously using anyio
        path = anyio.Path(file_path)
        content = await path.read_text(encoding="utf-8")
        return [
            IngestedDocument(
                page_content=content,
                metadata={"source": file_name}
            )
        ]
