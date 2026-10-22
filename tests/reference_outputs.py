"""Compute abcpy's outputs in the same shape as the node dumpers in tests/js."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import abcpy  # noqa: E402
from abcpy.data.tune import _strip_engraver_refs  # noqa: E402
from abcpy.api.tunebook_svg import render_abc  # noqa: E402
from abcpy.api.tunebook import number_of_tunes  # noqa: E402
from abcpy.write.dom import Element  # noqa: E402
from abcpy.str.output import str_transpose  # noqa: E402
from fingerprints import drop_none, normalize  # noqa: E402


def _plain(v):
    return json.loads(json.dumps(v, default=lambda o: None))


def parse_output(item):
    tunes = abcpy.parse_only(item["abc"], item.get("params") or {})
    return [_plain(_strip_engraver_refs(t.to_dict())) for t in tunes]


def _strip_elem(v):
    if isinstance(v, dict):
        return {k: _strip_elem(x) for k, x in v.items() if k != 'elem'}
    if isinstance(v, list):
        return [_strip_elem(x) for x in v]
    return v


def audio_output(item):
    t = abcpy.parse_only(item["abc"], item.get("params") or {})[0]
    return drop_none(normalize(_plain(_strip_elem(t.set_up_audio(item.get("params") or {})))))


def midi_output(item):
    params = dict(item.get("params") or {})
    params["midiOutputType"] = "encoded"
    return abcpy.get_midi_file(item["abc"], params)[0]


def svg_output(item):
    n = number_of_tunes(item["abc"])
    divs = [Element("div") for _ in range(n)]
    render_abc(divs, item["abc"], dict(item.get("params") or {}))
    return [[s.to_string(xmlns=True) for s in d.query_selector_all("svg")] for d in divs]


def transpose_output(item, steps):
    return str_transpose(item["abc"], abcpy.parse_only(item["abc"]), steps)
