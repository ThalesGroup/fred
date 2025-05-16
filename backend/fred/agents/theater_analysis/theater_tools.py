
from typing import Dict, List, Dict, Any, Tuple

import yaml
from langchain_core.tools import tool

@tool
def generate_map_configuration(locations: List[Tuple[float, float]],
                      statuses: List[str],
                      protocols: List[str],
                      frequencies: List[float],
                      bandwidths: List[int]) -> List[Dict[str, Any]]:
    expected_keys = {"location", "status", "protocol", "frequency", "bandwidth"}
    entries = zip(locations, statuses, protocols, frequencies, bandwidths)
    validated_data = []
    for entry in entries:
        if not expected_keys.issubset(entry.keys()):
            raise ValueError(f"Entry is missing one of the required keys: {expected_keys}")

        if not isinstance(entry["location"], tuple) or len(entry["location"]) != 2:
            raise ValueError("Invalid location format; must be a tuple of (latitude, longitude).")
        if not isinstance(entry["status"], str):
            raise ValueError("Invalid status; must be a string.")
        if not isinstance(entry["protocol"], str):
            raise ValueError("Invalid protocol; must be a string.")
        if not isinstance(entry["frequency"], (float, int)):
            raise ValueError("Invalid frequency; must be a number.")
        if not isinstance(entry["bandwidth"], int):
            raise ValueError("Invalid bandwidth; must be an integer.")
        
        validated_data.append(entry)

    return validated_data

data_entries = [
    {"location": (42.626327, 5.629789), "status": "Normal", "protocol": "STANAG-4204", "frequency": 68.0125, "bandwidth": 25},
    {"location": (43.163566, 4.847013), "status": "Normal", "protocol": "STANAG-4204", "frequency": 68.0125, "bandwidth": 25},
    {"location": (42.166307, 6.529822), "status": "Abnormal", "protocol": "Link-11", "frequency": 382.5625, "bandwidth": 30},
    {"location": (43.059710, 6.914343), "status": "Abnormal", "protocol": "Link-11", "frequency": 382.5625, "bandwidth": 30},
    {"location": (41.634572, 4.577305), "status": "Normal", "protocol": "STANAG-4204", "frequency": 51.3, "bandwidth": 25},
    {"location": (42.902763, 6.966831), "status": "Normal", "protocol": "STANAG-4204", "frequency": 51.3, "bandwidth": 25},
    {"location": (42.930923, 6.022007), "status": "Normal", "protocol": "STANAG-4204", "frequency": 68.01254, "bandwidth": 25}
]

try:
    validated_data = generate_data(data_entries)
    print(validated_data)
except ValueError as e:
    print("Validation error:", e)
