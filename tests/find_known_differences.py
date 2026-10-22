"""List the corpus entries where abcpy currently differs from the stored abcjs fingerprints."""
import json, os, sys, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fingerprints import fingerprint
import reference_outputs as ro

known = {}
for name in ["tests", "examples", "fuzz"]:
    items = json.load(open(os.path.join(HERE, "corpus_%s.json" % name)))
    expected = json.load(open(os.path.join(HERE, "fixtures", "expected_%s.json" % name)))
    diffs = []
    for i, (item, exp) in enumerate(zip(items, expected)):
        for kind in ("parse", "audio", "midi", "svg", "transpose"):
            if kind not in exp:
                continue
            try:
                if kind == "transpose":
                    got = fingerprint(ro.transpose_output(item, exp[kind][0]))
                    want = exp[kind][1]
                else:
                    got = fingerprint(getattr(ro, kind + "_output")(item))
                    want = exp[kind]
            except Exception:
                got = "exception"
                want = exp[kind] if kind != "transpose" else exp[kind][1]
            if got != want:
                diffs.append([i, kind])
    known[name] = diffs
    print(name, len(diffs), diffs[:40])
json.dump(known, open(os.path.join(HERE, "fixtures", "known_differences.json"), "w"), indent=1)
