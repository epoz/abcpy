"""Estimating the size of text without a browser.

abcjs asks the browser for the bounding box of every piece of text it places.
abcpy computes it from font metrics instead: the advance widths of fonts that are
metric-compatible with Arial/Helvetica, Times New Roman and Courier New (the
Liberation fonts).  Any font family is mapped to the closest of those three.
"""

from ..jsutil import parse_float, is_nan
from .font_metrics import metrics

LINE_SPACING = 1.2  # the "dy" used between lines of a multi-line text element


def font_key(family, weight=None, style=None):
    """Map a CSS font-family/weight/style to one of the metric tables."""
    fam = (family or "").lower()
    if "mono" in fam or "courier" in fam:
        base = "mono"
    elif "sans" in fam:
        base = "sans"
    elif ("times" in fam or "serif" in fam or "georgia" in fam or "palatino" in fam or "bookman" in fam
          or "century" in fam or "garamond" in fam or "chancery" in fam or "cursive" in fam):
        base = "serif"
    else:
        base = "sans"
    w = str(weight or "").lower()
    bold = w == "bold" or w == "bolder" or (w.isdigit() and int(w) >= 600)
    s = str(style or "").lower()
    italic = s == "italic" or s == "oblique"
    if bold and italic:
        return base + "-bolditalic"
    if bold:
        return base + "-bold"
    if italic:
        return base + "-italic"
    return base + "-normal"


def _char_width(widths, ch):
    cp = ord(ch)
    w = widths.get(cp)
    if w is not None:
        return w
    if cp < 0x20 or 0x200B <= cp <= 0x200F or 0x0300 <= cp <= 0x036F or cp == 0xFEFF:
        return 0  # control characters, zero width and combining characters
    if (0x1100 <= cp <= 0x115F or 0x2E80 <= cp <= 0xA4CF or 0xAC00 <= cp <= 0xD7A3 or
            0xF900 <= cp <= 0xFAFF or 0xFE30 <= cp <= 0xFE4F or 0xFF00 <= cp <= 0xFF60 or
            0xFFE0 <= cp <= 0xFFE6 or 0x1F300 <= cp <= 0x1FAFF or 0x20000 <= cp <= 0x3FFFD):
        return 1000  # wide characters (CJK, emoji)
    return widths.get(ord('n'), 556)


def text_width(text, font_size, family=None, weight=None, style=None):
    """Width in pixels of a single line of text."""
    m = metrics[font_key(family, weight, style)]
    widths = m["widths"]
    total = 0
    for ch in text:
        total += _char_width(widths, ch)
    return total * font_size / 1000


def line_height(font_size, family=None, weight=None, style=None):
    """Height in pixels of the box of one line of text (ascent + descent)."""
    m = metrics[font_key(family, weight, style)]
    return (m["ascent"] + m["descent"]) * font_size / 1000


def ascent(font_size, family=None, weight=None, style=None):
    m = metrics[font_key(family, weight, style)]
    return m["ascent"] * font_size / 1000


def font_size_of(value, default=16):
    """Parse a font-size attribute (``12``, ``"12"`` or ``"12px"``)."""
    if value is None:
        return default
    v = parse_float(value)
    if is_nan(v):
        return default
    return v
