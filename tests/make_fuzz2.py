"""Fuzzed corpus with random render parameters (written to the path given, default scratch)."""
import json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
seed = int(sys.argv[1]); n = int(sys.argv[2]); out = sys.argv[3]
random.seed(seed)
items = json.load(open(os.path.join(HERE, "corpus_tests.json")))
param_sets = [x["params"] for x in items if x["params"]]
param_sets += [{"visualTranspose": 3}, {"responsive": "resize"}, {"oneSvgPerLine": True, "add_classes": True},
               {"tablature": [{"instrument": "violin"}]}, {"tablature": [{"instrument": "guitar", "capo": 2}]},
               {"staffwidth": 300, "wrap": {"minSpacing": 1.5, "maxSpacing": 2.5}}, {"jazzchords": True},
               {"format": {"titlefont": "Arial 30", "gchordfont": "Courier 14 box"}}, {"expandToWidest": True},
               {"timeBasedLayout": {"minPadding": 10, "align": "center"}}, {"print": True}, {"scale": 0.7},
               {"initialClef": True}, {"germanAlphabet": True}, {"selectTypes": True, "dragging": True}]
alphabet = list("abcdefgABCDEFGzxyZ|:[]()-_^=,'/<>{}!+\"~.0123456789 \n%&\\KMLVQTPw:")
res = []
for _ in range(n):
    it = random.choice(items)
    s = list(it["abc"])
    for _ in range(random.randint(0, 5)):
        op = random.random(); pos = random.randint(0, len(s))
        if op < 0.4:
            s.insert(pos, random.choice(alphabet))
        elif op < 0.7 and s:
            del s[min(pos, len(s) - 1)]
        elif s:
            a = random.randint(0, len(s) - 1); b = min(len(s), a + random.randint(1, 12)); s[pos:pos] = s[a:b]
    params = dict(random.choice(param_sets)) if random.random() < 0.8 else {}
    if random.random() < 0.3:
        params.update(random.choice(param_sets))
    res.append({"abc": "".join(s), "params": params})
json.dump(res, open(out, "w"))
