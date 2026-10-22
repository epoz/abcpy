"""Generate tests/fixtures/*.json: fingerprints of what abcjs produces for the corpora.

Needs node and an abcjs checkout (ABCJS_ROOT, default /repos/abcjs).
usage: python3 tests/make_fixtures.py
"""
import json, os, random, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fingerprints import fingerprint, drop_none

ABCJS = os.environ.get("ABCJS_ROOT", "/repos/abcjs")
CORPORA = ["corpus_tests.json", "corpus_examples.json", "corpus_fuzz.json"]


def run(script, items):
    tmp = "/tmp/abcpy_fx_%d.json" % os.getpid()
    json.dump(items, open(tmp, "w"))
    out = subprocess.run(["node", os.path.join(HERE, "js", script), ABCJS, tmp], capture_output=True, text=True, check=True).stdout
    os.unlink(tmp)
    return json.loads(out)


def transpose_steps(i):
    return [-14, -12, -7, -5, -3, -2, -1, 1, 2, 3, 4, 5, 6, 7, 11, 12, 13][i % 17]


for name in CORPORA:
    items = json.load(open(os.path.join(HERE, name)))
    parse = run("parse_dump.js", items)
    audio = run("audio_dump.js", items)
    svg = run("svg_dump.js", items)
    tr_items = [{"abc": it["abc"], "steps": transpose_steps(i)} for i, it in enumerate(items)]
    tr = run("transpose_dump.js", tr_items)
    result = []
    for i in range(len(items)):
        rec = {}
        if not isinstance(parse[i], dict):
            rec["parse"] = fingerprint(parse[i])
        a = audio[i]
        if not (isinstance(a["audio"], dict) and "error" in a["audio"]):
            rec["audio"] = fingerprint(drop_none(a["audio"]))
        if isinstance(a["midi"], str):
            rec["midi"] = fingerprint(a["midi"])
        if not isinstance(svg[i], dict):
            rec["svg"] = fingerprint(svg[i])
        if isinstance(tr[i], str) and "undefined" not in tr[i]:
            rec["transpose"] = [tr_items[i]["steps"], fingerprint(tr[i])]
        result.append(rec)
    out = os.path.join(HERE, "fixtures", name.replace("corpus_", "expected_"))
    json.dump(result, open(out, "w"), separators=(",", ":"))
    print(name, len(result))
