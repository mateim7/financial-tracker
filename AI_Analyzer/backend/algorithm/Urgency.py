from enum import Enum

class Urgency(Enum):
    FLASH = "FLASH"          # Breaking " requires immediate action
    HIGH = "HIGH"            # Significant " act within minutes
    STANDARD = "STANDARD"    # Notable " review within the hour
    LOW = "LOW"              # Informational " end-of-day digest



