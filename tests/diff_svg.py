"""Differential test of the SVG engraver against abcjs running on a fake DOM in node.

usage: python3 tests/diff_svg.py [corpus.json] ; env SHOW=n ONLY=i
"""
import json, os, subprocess, sys, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import abcpy
from abcpy.api.tunebook_svg import render_abc
from abcpy.api.tunebook import number_of_tunes
from abcpy.write.dom import Element


def py_render(item):
    try:
        n = number_of_tunes(item["abc"])
        divs = [Element("div") for _ in range(n)]
        render_abc(divs, item["abc"], dict(item.get("params") or {}))
        return [[s.to_string(xmlns=True) for s in d.query_selector_all("svg")] for d in divs]
    except Exception:
        return {"error": "PY " + traceback.format_exc()}


def main():
    corpus = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "corpus_tests.json")
    items = [x for x in json.load(open(corpus)) if os.environ.get("TAB") or not x["params"].get("tablature")]
    only = os.environ.get("ONLY")
    if only:
        items = [items[int(only)]]
    start = int(os.environ.get("START", "0"))
    count = int(os.environ.get("COUNT", "100000"))
    items = items[start:start + count]
    tmp = "/tmp/abcpy_svg_%d.json" % os.getpid()
    json.dump(items, open(tmp, "w"))
    js = json.loads(subprocess.run(["node", os.path.join(HERE, "js", "svg_dump.js"), "/repos/abcjs", tmp], capture_output=True, text=True, check=True).stdout)
    os.unlink(tmp)
    show = int(os.environ.get("SHOW", "3"))
    bad = 0
    js_err = 0
    for i, it in enumerate(items):
        j = js[i]
        if isinstance(j, dict):
            js_err += 1
            continue
        p = py_render(it)
        if p != j:
            bad += 1
            if bad <= show:
                print("=" * 70)
                print("#%d" % (start + i if not only else int(only)), repr(it["abc"][:200]), it.get("params"))
                if isinstance(p, dict):
                    print(p["error"][-2500:])
                    continue
                if len(p) != len(j):
                    print("tune count", len(j), len(p))
                    continue
                for t in range(len(j)):
                    if len(p[t]) != len(j[t]):
                        print("svg count", len(j[t]), len(p[t]))
                        break
                    for s in range(len(j[t])):
                        a, b = j[t][s], p[t][s]
                        if a != b:
                            k = next((x for x in range(min(len(a), len(b))) if a[x] != b[x]), min(len(a), len(b)))
                            print("JS:", a[max(0, k - 300):k + 200])
                            print("PY:", b[max(0, k - 300):k + 200])
                            break
                    else:
                        continue
                    break
    print("%d / %d differ (%d abcjs errors skipped)" % (bad, len(items), js_err))


if __name__ == "__main__":
    main()
