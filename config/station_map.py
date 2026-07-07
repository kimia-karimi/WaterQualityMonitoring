"""
Station ID → Clean Name mapping

Used for:
- output file naming
- reporting
- future metadata standardization
"""

STATION_NAME_MAP = {
    "CCBay": {
        "hydrovu_names": ["default-1031419"],
    },
    "BaffinBay": {
        "hydrovu_names": ["default-1031425"],
    },
}



def normalize_name(name: str) -> str:
    """
    Clean filename-safe name
    """
    return name.replace(" ", "").replace("/", "_")

def get_station_names():
    return list(STATION_NAME_MAP.keys())


def find_candidate_locations(locations, station_name):
    candidates = []

    aliases = STATION_NAME_MAP[station_name]["hydrovu_names"]

    for loc in locations:
        if loc.get("name") in aliases:
            candidates.append(loc)

    return candidates
#Move filename logic into a reusable function
def build_output_filename(location_id, start=None, end=None):
    name = normalize_name(get_station_names(location_id))

    def clean(ts):
        if not ts:
            return None
        return ts[:10].replace("-", "")

    start_s = clean(start)
    end_s = clean(end)

    if start_s and end_s:
        return f"{name}_{start_s}_{end_s}.csv"
    elif start_s:
        return f"{name}_{start_s}.csv"
    else:
        return f"{name}.csv"
