"""Differential test: compare abcpy's parser output with abcjs's (run through node).

usage: python3 tests/diff_parse.py [corpus.json] [--show N] [--only IDX]
"""
import json
import math
import os
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
ABCJS = os.environ.get("ABCJS_ROOT", "/repos/abcjs")

import abcpy  # noqa: E402
from abcpy.data.tune import _strip_engraver_refs  # noqa: E402


def normalize(v):
    if isinstance(v, dict):
        return {k: normalize(x) for k, x in v.items() if not (x is None and False)}
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


def py_parse(item):
    try:
        tunes = abcpy.parse_only(item["abc"], item.get("params") or {})
        return [json.loads(json.dumps(_strip_engraver_refs(t.to_dict()), default=lambda o: None)) for t in tunes]
    except Exception as e:
        return {"error": "PY: " + repr(e), "tb": traceback.format_exc()}


def first_diff(a, b, path=""):
    if type(a) != type(b):
        return path, a, b
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return path + "." + k, a.get(k, "<missing>"), b.get(k, "<missing>")
            d = first_diff(a[k], b[k], path + "." + k)
            if d:
                return d
        return None
    if isinstance(a, list):
        for i in range(min(len(a), len(b))):
            d = first_diff(a[i], b[i], path + "[%d]" % i)
            if d:
                return d
        if len(a) != len(b):
            return path + ".length", len(a), len(b)
        return None
    if a != b:
        return path, a, b
    return None


def main():
    args = sys.argv[1:]
    corpus = os.path.join(HERE, "corpus_tests.json")
    show = 10
    only = None
    i = 0
    while i < len(args):
        if args[i] == "--show":
            show = int(args[i + 1]); i += 2
        elif args[i] == "--only":
            only = int(args[i + 1]); i += 2
        else:
            corpus = args[i]; i += 1
    items = json.load(open(corpus))
    if only is not None:
        items = [items[only]]
    tmp = os.path.join(os.environ.get("TMPDIR", "/tmp"), "abcpy_corpus_%d.json" % os.getpid())
    json.dump(items, open(tmp, "w"))
    js = json.loads(subprocess.run(["node", os.path.join(HERE, "js", "parse_dump.js"), ABCJS, tmp], capture_output=True, text=True, check=True).stdout)
    os.unlink(tmp)
    bad = 0
    for idx, item in enumerate(items):
        expected = normalize(js[idx])
        actual = normalize(py_parse(item))
        if expected != actual:
            if isinstance(expected, dict) and "error" in expected and not (isinstance(actual, dict) and "tb" in actual):
                continue  # abcjs crashed on this input; abcpy is allowed to do better
            d = first_diff(expected, actual)
            if d and isinstance(d[1], str) and "TypeError" in d[1] and "warnings" in d[0]:
                continue  # abcjs leaked a JavaScript error message into a warning
            bad += 1
            if bad <= show:
                print("=" * 70)
                print("#%d" % (idx if only is None else only), repr(item["abc"][:300]), item.get("params"))
                if isinstance(actual, dict) and "tb" in actual:
                    print(actual["tb"])
                else:
                    print(first_diff(expected, actual))
    print("%d / %d differ" % (bad, len(items)))


if __name__ == "__main__":
    main()
