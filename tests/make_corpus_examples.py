"""Collect abc tunes found in the abcjs examples and docs (textareas, JS strings and template literals)."""
import glob, html, json, os, re, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else "/repos/abcjs"
HERE = os.path.dirname(os.path.abspath(__file__))
found = []
seen = set()


def add(s):
    s = s.strip("\n")
    if "K:" in s and len(s) > 10 and s not in seen:
        seen.add(s)
        found.append({"abc": s, "params": {}})


files = glob.glob(os.path.join(ROOT, "examples", "**", "*.html"), recursive=True) + \
    glob.glob(os.path.join(ROOT, "docs", "**", "*.md"), recursive=True) + \
    glob.glob(os.path.join(ROOT, "docs", "**", "*.vue"), recursive=True) + \
    glob.glob(os.path.join(ROOT, "docs", "**", "*.js"), recursive=True)
for f in files:
    if "node_modules" in f:
        continue
    text = open(f, encoding="utf-8", errors="replace").read()
    for m in re.finditer(r"<textarea[^>]*>(.*?)</textarea>", text, re.S):
        add(html.unescape(m.group(1)))
    for m in re.finditer(r"`([^`]*X:[^`]*)`", text, re.S):
        if "${" not in m.group(1):
            add(m.group(1))
    # concatenated JS strings: "X:1\n" + "T:..."
    for m in re.finditer(r'((?:"(?:[^"\\\n]|\\.)*"\s*\+?\s*){2,})', text):
        chunk = m.group(1)
        parts = re.findall(r'"((?:[^"\\\n]|\\.)*)"', chunk)
        try:
            s = "".join(json.loads('"' + p + '"') for p in parts)
        except Exception:
            continue
        if "X:" in s:
            add(s)
    for m in re.finditer(r"```(?:abc)?\n(.*?)```", text, re.S):
        if "X:" in m.group(1):
            add(m.group(1))
json.dump(found, open(os.path.join(HERE, "corpus_examples.json"), "w"), indent=1)
print(len(found))
