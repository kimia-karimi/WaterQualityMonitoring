"""
Station ID → Clean Name mapping

Used for:
- output file naming
- reporting
- future metadata standardization
"""

STATION_NAME_MAP = {
    5106941840719872: "BaffinBay",
    6387509350170624: "CCBay",
}


def get_station_name(location_id):
    """
    Safe lookup with fallback
    """
    return STATION_NAME_MAP.get(location_id, str(location_id))


def normalize_name(name: str) -> str:
    """
    Clean filename-safe name
    """
    return name.replace(" ", "").replace("/", "_")
