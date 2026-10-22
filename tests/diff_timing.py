"""Differential test of Tune.set_timing() (after rendering) against abcjs."""
import json, os, subprocess, sys, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from abcpy.api.tunebook_svg import render_abc
from abcpy.write.dom import Element
from diff_parse import normalize, first_diff

corpus = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "corpus_tests.json")
items = json.load(open(corpus))
tmp = "/tmp/abcpy_tm_%d.json" % os.getpid()
json.dump(items, open(tmp, "w"))
js = json.loads(subprocess.run(["node", os.path.join(HERE, "js", "timing_dump.js"), "/repos/abcjs", tmp], capture_output=True, text=True, check=True).stdout)
bad = 0
show = int(os.environ.get("SHOW", "5"))
for i, it in enumerate(items):
    if isinstance(js[i], dict):
        continue
    try:
        tunes = render_abc(Element("div"), it["abc"], dict(it["params"]))
        tm = tunes[0].set_timing()
        py = json.loads(json.dumps(tm, default=lambda o: None))
        for ev in py:
            if 'elements' in ev:
                ev['elements'] = len(ev['elements'])
    except Exception:
        py = {"error": traceback.format_exc()}
    a, b = normalize(js[i]), normalize(py)
    if a != b:
        bad += 1
        if bad <= show:
            print(i, repr(it["abc"][:120]))
            print(py["error"][-1500:] if isinstance(py, dict) else first_diff(a, b))
print(bad, "/", len(items), "differ")
