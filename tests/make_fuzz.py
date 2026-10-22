"""Create a fuzzed corpus by mutating the test corpus (deterministic)."""
import json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
items = [x for x in json.load(open(os.path.join(HERE, "corpus_tests.json"))) if not x["params"].get("tablature")]
alphabet = list("abcdefgABCDEFGzxyZ|:[]()-_^=,'/<>{}!+\"~.0123456789 \n%&\\KMLVQTPw:")
out = []
for n in range(int(sys.argv[2]) if len(sys.argv) > 2 else 3000):
    it = random.choice(items)
    s = list(it["abc"])
    for _ in range(random.randint(1, 6)):
        op = random.random()
        pos = random.randint(0, len(s))
        if op < 0.4:
            s.insert(pos, random.choice(alphabet))
        elif op < 0.7 and s:
            del s[min(pos, len(s) - 1)]
        elif s:
            # duplicate a chunk
            a = random.randint(0, len(s) - 1); b = min(len(s), a + random.randint(1, 12))
            s[pos:pos] = s[a:b]
    out.append({"abc": "".join(s), "params": it["params"]})
json.dump(out, open(os.path.join(HERE, "corpus_fuzz.json"), "w"))
