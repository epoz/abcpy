"""Regression tests: abcpy must reproduce the stored fingerprints of abcjs's outputs.

The fingerprints in tests/fixtures were made with tests/make_fixtures.py, which runs abcjs in node.
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fingerprints import fingerprint  # noqa: E402
import reference_outputs as ro  # noqa: E402

KNOWN = json.load(open(os.path.join(HERE, "fixtures", "known_differences.json")))
CORPORA = ["tests", "examples", "fuzz"]
KINDS = ["parse", "audio", "midi", "svg", "transpose"]


def _load(name):
    items = json.load(open(os.path.join(HERE, "corpus_%s.json" % name)))
    expected = json.load(open(os.path.join(HERE, "fixtures", "expected_%s.json" % name)))
    return items, expected


@pytest.mark.parametrize("name", CORPORA)
@pytest.mark.parametrize("kind", KINDS)
def test_matches_abcjs(name, kind):
    items, expected = _load(name)
    known = set((i, k) for i, k in KNOWN.get(name, []))
    failures = []
    for i, (item, exp) in enumerate(zip(items, expected)):
        if kind not in exp or (i, kind) in known:
            continue
        try:
            if kind == "transpose":
                got = fingerprint(ro.transpose_output(item, exp[kind][0]))
                want = exp[kind][1]
            else:
                got = fingerprint(getattr(ro, kind + "_output")(item))
                want = exp[kind]
        except Exception as e:  # pragma: no cover - reported below
            got = "exception: %r" % e
            want = exp[kind] if kind != "transpose" else exp[kind][1]
        if got != want:
            failures.append((i, item["abc"][:80], got))
    assert not failures, "%d differences, first: %r" % (len(failures), failures[:5])
