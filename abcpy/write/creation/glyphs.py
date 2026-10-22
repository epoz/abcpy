"""Glyphs and some methods to adjust for their x and y baseline (port of ``glyphs.js``)."""

from ...jsutil import js_str
from ..helpers import spacing
from ..glyphs_data import glyphs


def _path_clone(path_array):
    return [list(p) for p in path_array]


def _path_scale(path_array, kx, ky):
    for p in path_array:
        for j in range(1, len(p)):
            p[j] *= kx if (j % 2) else ky


def _join(path_array):
    return "".join(" ".join(js_str(v) for v in p) for p in path_array)


def print_symbol(x, y, symb, paper, attrs):
    if not glyphs.get(symb):
        return None
    path_array = _path_clone(glyphs[symb]['d'])
    path_array[0][1] += x
    path_array[0][2] += y
    attrs['path'] = _join(path_array)
    return paper.path(attrs)


def get_path_for_symbol(x, y, symb, scalex=None, scaley=None):
    scalex = scalex or 1
    scaley = scaley or 1
    if not glyphs.get(symb):
        return None
    path_array = _path_clone(glyphs[symb]['d'])
    if scalex != 1 or scaley != 1:
        _path_scale(path_array, scalex, scaley)
    path_array[0][1] += x
    path_array[0][2] += y
    return path_array


def get_symbol_width(symbol):
    g = glyphs.get(symbol) if isinstance(symbol, str) else None
    if g:
        return g['w']
    return 0


def symbol_height_in_pitches(symbol):
    g = glyphs.get(symbol) if isinstance(symbol, str) else None
    height = g['h'] if g else 0
    return height / spacing.STEP


def get_symbol_align(symbol):
    if symbol[0:7] == "scripts" and symbol != "scripts.roll":
        return "center"
    return "left"


_ycorr = {
    "0": -2, "1": -2, "2": -2, "3": -2, "4": -2, "5": -2, "6": -2, "7": -2, "8": -2, "9": -2, "+": -2,
    "timesig.common": 0, "timesig.cut": 0,
    "flags.d32nd": -1, "flags.d64th": -2, "flags.u32nd": 1, "flags.u64th": 3,
    "rests.whole": 1, "rests.half": -1, "rests.8th": -1, "rests.quarter": -1, "rests.16th": -1,
    "rests.32nd": -1, "rests.64th": -1,
    "f": -4, "m": -4, "p": -4, "s": -4, "z": -4,
    "scripts.trill": -2, "scripts.upbow": -2, "scripts.downbow": -2,
    "scripts.ufermata": -1, "scripts.wedge": -1, "scripts.roll": -1, "scripts.shortphrase": -1,
    "scripts.longphrase": -1,
    "scripts.dfermata": 1,
}


def get_y_corr(symbol):
    return _ycorr.get(symbol, 0)


def set_symbol(name, path):
    """Replace (or add) a glyph: ``path`` is ``{'d': [[cmd, ...], ...], 'w': width, 'h': height}``."""
    glyphs[name] = path


# camelCase aliases (abcjs API)
printSymbol = print_symbol
getPathForSymbol = get_path_for_symbol
getSymbolWidth = get_symbol_width
symbolHeightInPitches = symbol_height_in_pitches
getSymbolAlign = get_symbol_align
getYCorr = get_y_corr
setSymbol = set_symbol
