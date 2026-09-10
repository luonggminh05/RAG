import os
import csv
import logging
from typing import List
from openpyxl import load_workbook
from app.ai.rag.ingestion.parsers.base import BaseDocumentParser, IngestedDocument

logger = logging.getLogger(__name__)

class TabularParser(BaseDocumentParser):
    def can_parse(self, extension: str) -> bool:
        return extension.lower() in [".xlsx", ".csv"]

    async def parse_async(self, file_path: str, file_name: str) -> List[IngestedDocument]:
        docs = []
        extension = os.path.splitext(file_path)[1].lower()

        try:
            if extension == ".xlsx":
                wb = load_workbook(file_path, data_only=True, read_only=True)
                ws = wb.active if wb.worksheets else None
                if ws:
                    headers = {}
                    first_row = True
                    row_idx = 1
                    for row in ws.iter_rows(values_only=True):
                        if first_row:
                            headers = {i: str(val).strip() for i, val in enumerate(row, start=1) if val is not None}
                            first_row = False
                        else:
                            row_idx += 1
                            row_data = []
                            for col_idx, val in enumerate(row, start=1):
                                if val is not None and col_idx in headers:
                                    row_data.append(f"{headers[col_idx]}: {str(val).strip()}")
                            if row_data:
                                page_content = ", ".join(row_data)
                                docs.append(IngestedDocument(
                                    page_content=page_content,
                                    metadata={
                                        "source": file_name,
                                        "row": row_idx,
                                        "type": "xlsx_row"
                                    }
                                ))
                wb.close()

            elif extension == ".csv":
                encodings = ["utf-8-sig", "utf-8", "latin-1"]
                reader = None
                file_handle = None
                for encoding in encodings:
                    try:
                        file_handle = open(file_path, mode="r", encoding=encoding, errors="replace")
                        file_handle.readline()
                        file_handle.seek(0)
                        reader = csv.reader(file_handle)
                        break
                    except Exception:
                        if file_handle:
                            file_handle.close()
                        file_handle = None

                if reader and file_handle:
                    try:
                        headers = next(reader, None)
                        if headers:
                            headers = [h.strip() for h in headers]
                            row_idx = 2
                            for row in reader:
                                row_data = []
                                for col_idx, val in enumerate(row):
                                    if val is not None and col_idx < len(headers) and val.strip():
                                        row_data.append(f"{headers[col_idx]}: {val.strip()}")
                                if row_data:
                                    page_content = ", ".join(row_data)
                                    docs.append(IngestedDocument(
                                        page_content=page_content,
                                        metadata={
                                            "source": file_name,
                                            "row": row_idx,
                                            "type": "csv_row"
                                        }
                                    ))
                                row_idx += 1
                    finally:
                        file_handle.close()

        except Exception as ex:
            logger.error(f"[TABULAR] Error parsing {file_name}: {ex}")

        return docs
