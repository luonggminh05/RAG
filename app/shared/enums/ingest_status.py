from enum import Enum

class IngestStatus(str, Enum):
    Pending = "Pending"
    Processing = "Processing"
    Completed = "Completed"
    Failed = "Failed"
