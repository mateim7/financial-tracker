from enum import Enum

class Urgency(Enum):
    FLASH = "FLASH"          # Breaking â€” requires immediate action
    HIGH = "HIGH"            # Significant â€” act within minutes
    STANDARD = "STANDARD"    # Notable â€” review within the hour
    LOW = "LOW"              # Informational â€” end-of-day digest



