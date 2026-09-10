from enum import Enum

class QueryIntent(str, Enum):
    TaskInstruction = "TaskInstruction"
    UiLocation = "UiLocation"
    General = "General"
