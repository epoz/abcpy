"""Differential test of str_transpose against abcjs's strTranspose."""
import json, os, subprocess, sys, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import abcpy
from abcpy.str.output import str_transpose

corpus = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "corpus_tests.json")
items = [x for x in json.load(open(corpus)) if not x["params"].get("tablature")]
random.seed(5)
work = []
for it in items:
    for steps in random.sample([-14, -12, -7, -5, -3, -2, -1, 1, 2, 3, 4, 5, 6, 7, 11, 12, 13], 3):
        work.append({"abc": it["abc"], "steps": steps})
tmp = "/tmp/abcpy_tr_%d.json" % os.getpid()
json.dump(work, open(tmp, "w"))
js = json.loads(subprocess.run(["node", os.path.join(HERE, "js", "transpose_dump.js"), "/repos/abcjs", tmp], capture_output=True, text=True, check=True).stdout)
bad = 0
for i, w in enumerate(work):
    try:
        py = str_transpose(w["abc"], abcpy.parse_only(w["abc"]), w["steps"])
    except Exception as e:
        import traceback
        py = {"error": "PY " + traceback.format_exc()}
    if py != js[i] and not isinstance(js[i], dict) and "undefined" not in js[i]:
        bad += 1
        if bad <= int(os.environ.get("SHOW", "5")):
            print("=" * 60)
            print(i, w["steps"], repr(w["abc"][:200]))
            print("JS:", repr(js[i])[:400])
            print("PY:", repr(py)[:1400])
print(bad, "/", len(work), "differ")
