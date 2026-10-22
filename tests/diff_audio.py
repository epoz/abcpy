"""Differential test of set_up_audio() and MIDI creation against abcjs."""
import json, os, subprocess, sys, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import abcpy
from abcpy.synth import get_midi_file
from diff_parse import normalize, first_diff

corpus = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "corpus_tests.json")
items = [x for x in json.load(open(corpus)) if not x["params"].get("tablature")]
only = int(os.environ["ONLY"]) if os.environ.get("ONLY") else None
if only is not None:
    items = [items[only]]
tmp = "/tmp/abcpy_au_%d.json" % os.getpid()
json.dump(items, open(tmp, "w"))
js = json.loads(subprocess.run(["node", os.path.join(HERE, "js", "audio_dump.js"), "/repos/abcjs", tmp], capture_output=True, text=True, check=True).stdout)
bad_a = bad_m = 0
show = int(os.environ.get("SHOW", "5"))
def strip_elem(v):
    if isinstance(v, dict):
        return {k: strip_elem(x) for k, x in v.items() if k != 'elem' and x is not None}
    if isinstance(v, list):
        return [strip_elem(x) for x in v]
    return v
for i, it in enumerate(items):
    try:
        t = abcpy.parse_only(it["abc"], it["params"])[0]
        a = normalize(json.loads(json.dumps(strip_elem(t.set_up_audio(it["params"])), default=lambda o: None)))
    except Exception:
        a = {"error": traceback.format_exc()}
    try:
        m = get_midi_file(it["abc"], dict(it["params"], midiOutputType="encoded"))[0]
    except Exception:
        m = {"error": traceback.format_exc()}
    ja = normalize(js[i]["audio"])
    if ja != a and not ("error" in ja):
        bad_a += 1
        if bad_a <= show:
            print("AUDIO", i if only is None else only, repr(it["abc"][:150]))
            print(a["error"] if "error" in a else first_diff(ja, a))
    if js[i]["midi"] != m and not isinstance(js[i]["midi"], dict) and not (ja != a):
        if isinstance(m, dict):
            print(m['error']); bad_m += 1; continue
        bad_m += 1
        if bad_m <= show:
            print("MIDI", i if only is None else only, repr(it["abc"][:150]))
            print(m["error"] if isinstance(m, dict) else "")
            jm = js[i]["midi"]
            k = next((x for x in range(min(len(jm), len(m))) if jm[x] != m[x]), None)
            print(k, jm[max(0,(k or 0)-40):(k or 0)+60]); print(k, m[max(0,(k or 0)-40):(k or 0)+60])
print("audio diffs:", bad_a, " midi diffs:", bad_m, "of", len(items))
