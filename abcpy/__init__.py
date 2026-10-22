"""abcpy - a Python port of abcjs for reading, parsing, manipulating and engraving ABC music notation.

Quick start::

    import abcpy

    tunes = abcpy.parse_only(abc_text)          # list of Tune objects
    tune = tunes[0]
    tune.metaText["title"], tune.get_key_signature(), tune.get_meter_fraction()
    for line in tune.lines: ...                 # the same structure as the abcjs tune object

    transposed = abcpy.transpose(abc_text, 2)   # rewrite the abc text up a whole step
    svgs = abcpy.render_svg(abc_text)            # one SVG document (string) per tune
    abcpy.write_svg(abc_text, "tune.svg")
    midi = abcpy.get_midi_file(abc_text)[0]      # bytes of a standard MIDI file
"""

from .api.tunebook import number_of_tunes, TuneBook, parse_only, extract_measures, render_engine
from .api.tunebook_svg import render_abc, render_svg, write_svg, tune_metrics
from .parse.parse import Parse
from .data.tune import Tune
from .str.output import str_transpose
from .synth.midi import get_midi_file, write_midi_file
from .synth.sequencer import sequence
from .synth.flattener import flatten
from .write.creation.glyphs import set_symbol as set_glyph
from .write.dom import Element
from .jsutil import Obj

__version__ = "0.1.0"
signature = "abcpy v" + __version__ + " (port of abcjs-basic v6.7.2)"


def read_file(path, encoding="utf-8"):
    """Read an abc file (newlines are normalized by the parser)."""
    with open(path, encoding=encoding, errors="replace") as f:
        return f.read()


def parse_file(path, params=None, encoding="utf-8"):
    """Parse every tune in the abc file at ``path``; returns a list of :class:`Tune`."""
    return parse_only(read_file(path, encoding), params)


def transpose(abc, steps, params=None):
    """Return ``abc`` transposed by ``steps`` half steps (the text itself is rewritten)."""
    return str_transpose(abc, parse_only(abc, params), steps)


# camelCase aliases that match the abcjs API
numberOfTunes = number_of_tunes
parseOnly = parse_only
extractMeasures = extract_measures
renderEngine = render_engine
renderAbc = render_abc
tuneMetrics = tune_metrics
strTranspose = str_transpose
setGlyph = set_glyph
getMidiFile = get_midi_file

__all__ = [
    "number_of_tunes", "TuneBook", "parse_only", "extract_measures", "render_engine",
    "render_abc", "render_svg", "write_svg", "tune_metrics",
    "Parse", "Tune", "str_transpose", "transpose", "read_file", "parse_file",
    "get_midi_file", "write_midi_file", "sequence", "flatten",
    "set_glyph", "Element", "Obj",
]
