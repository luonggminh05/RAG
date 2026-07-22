import re
from typing import List, Optional
from app.services.action_classifier import ActionKindClassifier

class ExtractedProcedureBlock:
    def __init__(self, text: str, instruction_role: str, action_kind: Optional[str], step_count: int):
        self.text = text
        self.instruction_role = instruction_role
        self.action_kind = action_kind
        self.step_count = step_count

class ProcedureBlockExtractor:
    STEP_PATTERN = r'\b(?:Bước|Buoc|Step|B)\s*\d+\b'
    STEP_1_PATTERN = r'\b(?:Bước|Buoc|Step|B)\s*1\b'
    
    @staticmethod
    def is_step_line(line: str) -> bool:
        return bool(re.match(r'^\s*(?:Bước|Buoc|Step|B)\s*\d+\b', line, re.IGNORECASE))

    @staticmethod
    def count_steps(text: str) -> int:
        return len(re.findall(ProcedureBlockExtractor.STEP_PATTERN, text, re.IGNORECASE))

    @staticmethod
    def extract(text: str, parent_action_kind: Optional[str] = None) -> List[ExtractedProcedureBlock]:
        if not text or not text.strip():
            return []

        # Find all step matches
        step_matches = list(re.finditer(ProcedureBlockExtractor.STEP_PATTERN, text, re.IGNORECASE))
        if not step_matches:
            action = ActionKindClassifier.determine_action_kind(text) or parent_action_kind
            return [ExtractedProcedureBlock(text, "ui_details", action, 0)]

        # Find all step 1 matches to split multiple procedure blocks
        step_1_matches = list(re.finditer(ProcedureBlockExtractor.STEP_1_PATTERN, text, re.IGNORECASE))
        if len(step_1_matches) <= 1:
            # Only one procedure block
            step_count = len(step_matches)
            action = ActionKindClassifier.determine_action_kind(text) or parent_action_kind
            return [ExtractedProcedureBlock(text.strip(), "procedure_steps", action, step_count)]

        # Multiple procedure blocks starting with Step 1
        blocks = []
        for i in range(len(step_1_matches)):
            start = step_1_matches[i].start()
            end = step_1_matches[i + 1].start() if i + 1 < len(step_1_matches) else len(text)
            block_text = text[start:end].strip()
            
            if block_text:
                block_step_count = len(re.findall(ProcedureBlockExtractor.STEP_PATTERN, block_text, re.IGNORECASE))
                action = ActionKindClassifier.determine_action_kind(block_text) or parent_action_kind
                blocks.append(ExtractedProcedureBlock(
                    text=block_text,
                    instruction_role="procedure_steps",
                    action_kind=action,
                    step_count=block_step_count
                ))

        return blocks
