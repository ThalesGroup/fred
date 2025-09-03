import math
import datetime

def clean_json(obj):
    if isinstance(obj, dict):
        return {k: clean_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_json(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None  # ou str(obj) si tu veux garder "NaN", "inf"
    return obj

def safe_eval_function(func_str: str) -> callable:
    allowed_builtins = {
        "str": str, "int": int, "float": float, "bool": bool,
        "len": len, "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
        "lower": str.lower, "upper": str.upper, "title": str.title,
        "strip": str.strip, "replace": str.replace,
        "startswith": str.startswith, "endswith": str.endswith,
        "split": str.split, "join": str.join,
        "sorted": sorted, "range": range, "enumerate": enumerate,
        "zip": zip, "map": map, "filter": filter,
        "datetime": datetime,
        "__import__": __import__,
    }
    safe_globals = {"__builtins__": None}
    safe_globals.update(allowed_builtins)
    safe_locals = {}

    func = eval(func_str, safe_globals, safe_locals)
    if not callable(func):
        raise ValueError("The evaluated object is not callable.")
    return func