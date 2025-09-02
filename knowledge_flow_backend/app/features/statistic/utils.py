
import datetime

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