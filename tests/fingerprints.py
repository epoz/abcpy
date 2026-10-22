"""Fingerprints (hashes) of normalized outputs, shared by the fixture generator and the tests."""
import hashlib
import json
import math


def normalize(v):
    if isinstance(v, dict):
        return {k: normalize(x) for k, x in v.items()}
    if isinstance(v, list):
        return [normalize(x) for x in v]
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        if float(v) == int(v) and abs(v) < 1e15:
            return int(v)
        return round(v, 9)
    return v


def drop_none(v):
    if isinstance(v, dict):
        return {k: drop_none(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [drop_none(x) for x in v]
    return v


def fingerprint(value):
    text = json.dumps(normalize(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()[:20]
