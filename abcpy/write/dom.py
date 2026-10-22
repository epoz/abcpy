"""A very small DOM, just enough for the engraver to build SVG documents in memory.

It stands in for the browser DOM that abcjs uses.  Elements can be serialized
to markup with :meth:`Element.to_string`, and :meth:`Element.get_bbox`
estimates bounding boxes (text sizes come from :mod:`abcpy.write.text_metrics`).
"""

import math
import re

from ..jsutil import js_str
from . import text_metrics

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


class BBox:
    __slots__ = ("x", "y", "width", "height")

    def __init__(self, x=0, y=0, width=0, height=0):
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def __repr__(self):
        return "BBox(x=%r, y=%r, width=%r, height=%r)" % (self.x, self.y, self.width, self.height)


class Style:
    """The ``style`` property of an element: writes through to the ``style`` attribute."""

    def __init__(self, element):
        object.__setattr__(self, "_element", element)

    def _props(self):
        text = self._element.attrs.get("style") or ""
        props = []
        for part in text.split(";"):
            if ":" in part:
                k, v = part.split(":", 1)
                props.append([k.strip(), v.strip()])
        return props

    def __getitem__(self, name):
        name = _css_name(name)
        for k, v in self._props():
            if k == name:
                return v
        return ""

    def __setitem__(self, name, value):
        name = _css_name(name)
        value = js_str(value) if not isinstance(value, str) else value
        props = self._props()
        for p in props:
            if p[0] == name:
                if value == "":
                    props.remove(p)
                else:
                    p[1] = value
                break
        else:
            if value != "":
                props.append([name, value])
        if props:
            self._element.attrs["style"] = " ".join("%s: %s;" % (k, v) for k, v in props)
        else:
            self._element.attrs.pop("style", None)

    __getattr__ = __getitem__
    __setattr__ = __setitem__


def _css_name(name):
    if name.startswith("-"):
        return name
    return re.sub(r"[A-Z]", lambda m: "-" + m.group(0).lower(), name)


class Node:
    parent = None

    @property
    def parentNode(self):
        return self.parent

    @property
    def parentElement(self):
        return self.parent


class TextNode(Node):
    def __init__(self, text):
        self.text = text

    def to_string(self):
        return _escape_text(self.text)

    def clone(self):
        return TextNode(self.text)


class Element(Node):
    def __init__(self, tag, namespace=None):
        self.tag = tag
        self.namespace = namespace
        self.attrs = {}
        self.childNodes = []
        self.style = Style(self)

    # -- attributes ---------------------------------------------------------
    def set_attribute(self, name, value):
        self.attrs[name] = value if isinstance(value, str) else js_str(value)

    def get_attribute(self, name):
        return self.attrs.get(name)

    def remove_attribute(self, name):
        self.attrs.pop(name, None)

    setAttribute = set_attribute
    getAttribute = get_attribute
    removeAttribute = remove_attribute

    def setAttributeNS(self, ns, name, value):
        self.set_attribute(name, value)

    # -- tree ----------------------------------------------------------------
    @property
    def children(self):
        return [c for c in self.childNodes if isinstance(c, Element)]

    @property
    def firstChild(self):
        return self.childNodes[0] if self.childNodes else None

    @property
    def tagName(self):
        return self.tag

    def append_child(self, child):
        if child.parent is not None:
            child.parent.remove_child(child)
        child.parent = self
        self.childNodes.append(child)
        return child

    def insert_before(self, child, ref):
        if child.parent is not None:
            child.parent.remove_child(child)
        child.parent = self
        if ref is None or ref not in self.childNodes:
            self.childNodes.append(child)
        else:
            self.childNodes.insert(self.childNodes.index(ref), child)
        return child

    def remove_child(self, child):
        for i, c in enumerate(self.childNodes):
            if c is child:
                del self.childNodes[i]
                child.parent = None
                return child
        return child

    appendChild = append_child
    insertBefore = insert_before
    removeChild = remove_child

    @property
    def textContent(self):
        out = []
        for c in self.childNodes:
            if isinstance(c, TextNode):
                out.append(c.text)
            else:
                out.append(c.textContent)
        return "".join(out)

    @textContent.setter
    def textContent(self, value):
        for c in self.childNodes:
            c.parent = None
        self.childNodes = []
        value = value if isinstance(value, str) else js_str(value)
        if value != "":
            t = TextNode(value)
            t.parent = self
            self.childNodes.append(t)

    @property
    def innerHTML(self):
        return "".join(c.to_string() for c in self.childNodes)

    @innerHTML.setter
    def innerHTML(self, value):
        # Only the few forms that the engraver uses are supported.
        if value == "&nbsp;":
            self.textContent = "\xa0"
            return
        self.textContent = ""
        m = re.match(r'^<(\w+)(?: class="([^"]*)")?></\1>$', value or "")
        if m:
            el = Element(m.group(1))
            if m.group(2) is not None:
                el.set_attribute("class", m.group(2))
            self.append_child(el)
        elif value:
            self.textContent = value

    def clone_node(self, deep=False):
        el = Element(self.tag, self.namespace)
        el.attrs = dict(self.attrs)
        if deep:
            for c in self.childNodes:
                el.append_child(c.clone() if isinstance(c, TextNode) else c.clone_node(True))
        return el

    cloneNode = clone_node

    def clone(self):
        return self.clone_node(True)

    def query_selector_all(self, selector):
        """Supports ``tag`` and ``parent > child`` selectors."""
        parts = [p.strip() for p in selector.split(">")]
        results = []

        def walk(el):
            for c in el.children:
                if c.tag == parts[-1]:
                    ok = True
                    p = c.parent
                    for anc in reversed(parts[:-1]):
                        if p is None or p.tag != anc:
                            ok = False
                            break
                        p = p.parent
                    if ok:
                        results.append(c)
                walk(c)

        walk(self)
        return results

    def query_selector(self, selector):
        r = self.query_selector_all(selector)
        return r[0] if r else None

    querySelector = query_selector
    querySelectorAll = query_selector_all

    # -- serialization ---------------------------------------------------
    def to_string(self, xmlns=False):
        attrs = []
        if xmlns and self.tag == "svg" and "xmlns" not in self.attrs:
            attrs.append(' xmlns="%s"' % SVG_NS)
        for k, v in self.attrs.items():
            attrs.append(' %s="%s"' % (k, _escape_attr(v)))
        inner = "".join(c.to_string() for c in self.childNodes)
        return "<%s%s>%s</%s>" % (self.tag, "".join(attrs), inner, self.tag)

    def __str__(self):
        return self.to_string()

    # -- geometry --------------------------------------------------------
    def get_bbox(self):
        box = _bbox(self)
        if box is None:
            return BBox(0, 0, 0, 0)
        return BBox(box[0], box[1], box[2] - box[0], box[3] - box[1])

    getBBox = get_bbox


def create_element(tag):
    return Element(tag)


def _escape_text(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(s):
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


# -- bounding boxes -------------------------------------------------------------

def _num(v, default=0.0):
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        m = re.match(r"^\s*(-?\d*\.?\d+(?:[eE][-+]?\d+)?)", str(v))
        return float(m.group(1)) if m else default


def _inherited(el, name):
    while el is not None:
        if isinstance(el, Element):
            v = el.attrs.get(name)
            if v is not None:
                return v
        el = el.parent
    return None


def _font_size(el):
    return text_metrics.font_size_of(_inherited(el, "font-size"), 16)


def _text_runs(tspan, size):
    """The pieces of a line of text with their font sizes."""
    runs = []
    for c in tspan.childNodes:
        if isinstance(c, TextNode):
            runs.append((c.text, size))
        elif isinstance(c, Element):
            st = c.attrs.get("style") or ""
            m = re.search(r"font-size:\s*([\d.]+)em", st)
            sub = size * float(m.group(1)) if m else size
            for t, s in _text_runs(c, sub):
                runs.append((t, s))
    return runs


def _text_bbox(el):
    size = _font_size(el)
    family = _inherited(el, "font-family")
    weight = _inherited(el, "font-weight")
    style = _inherited(el, "font-style")
    anchor = _inherited(el, "text-anchor") or "start"
    baseline = el.attrs.get("dominant-baseline")
    x0 = _num(el.attrs.get("x"))
    y0 = _num(el.attrs.get("y"))
    lines = [c for c in el.childNodes if isinstance(c, Element) and c.tag == "tspan"]
    if not lines:
        text = el.textContent
        if text == "":
            return None
        lines_text = [[(text, size)]]
        xs = [x0]
    else:
        lines_text = [_text_runs(t, size) for t in lines]
        xs = [_num(t.attrs.get("x"), x0) for t in lines]
    widths = [sum(text_metrics.text_width(t, s, family, weight, style) for t, s in runs) for runs in lines_text]
    if all(w == 0 for w in widths) and all(not "".join(t for t, s in runs).strip() for runs in lines_text):
        return None
    height = text_metrics.line_height(size, family, weight, style) + (len(lines_text) - 1) * text_metrics.LINE_SPACING * size
    left = None
    right = None
    for x, w in zip(xs, widths):
        if anchor == "middle":
            lx = x - w / 2
        elif anchor == "end":
            lx = x - w
        else:
            lx = x
        left = lx if left is None else min(left, lx)
        right = lx + w if right is None else max(right, lx + w)
    if baseline == "middle":
        top = y0 - text_metrics.line_height(size, family, weight, style) / 2
    else:
        top = y0 - text_metrics.ascent(size, family, weight, style)
    return [left, top, right, top + height]


_path_token = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?")
_arg_counts = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


def _path_bbox(d):
    tokens = _path_token.findall(d or "")
    xs = []
    ys = []
    cx = cy = 0.0
    sx = sy = 0.0
    i = 0
    cmd = None
    while i < len(tokens):
        t = tokens[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in "Zz":
                cx, cy = sx, sy
                continue
        if cmd is None:
            i += 1
            continue
        n = _arg_counts[cmd.upper()]
        args = []
        while len(args) < n and i < len(tokens) and not tokens[i].isalpha():
            args.append(float(tokens[i]))
            i += 1
        if len(args) < n:
            break
        rel = cmd.islower()
        c = cmd.upper()
        if c == "H":
            cx = cx + args[0] if rel else args[0]
            pts = [(cx, cy)]
        elif c == "V":
            cy = cy + args[0] if rel else args[0]
            pts = [(cx, cy)]
        elif c == "A":
            ex = cx + args[5] if rel else args[5]
            ey = cy + args[6] if rel else args[6]
            pts = [(cx, cy), (ex, ey)]
            r = max(abs(args[0]), abs(args[1]))
            mx, my = (cx + ex) / 2, (cy + ey) / 2
            pts.append((mx - r, my - r))
            pts.append((mx + r, my + r))
            cx, cy = ex, ey
        else:
            pts = []
            for k in range(0, n, 2):
                px = cx + args[k] if rel else args[k]
                py = cy + args[k + 1] if rel else args[k + 1]
                pts.append((px, py))
            cx, cy = pts[-1]
        if c == "M":
            sx, sy = cx, cy
            cmd = "l" if rel else "L"  # subsequent pairs are line-to commands
        for px, py in pts:
            xs.append(px)
            ys.append(py)
    if not xs:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def _bbox(el):
    if not isinstance(el, Element):
        return None
    tag = el.tag
    if tag == "text":
        return _text_bbox(el)
    if tag == "path":
        return _path_bbox(el.attrs.get("d"))
    if tag == "line":
        x1, x2 = _num(el.attrs.get("x1")), _num(el.attrs.get("x2"))
        y1, y2 = _num(el.attrs.get("y1")), _num(el.attrs.get("y2"))
        return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
    if tag == "rect":
        x, y = _num(el.attrs.get("x")), _num(el.attrs.get("y"))
        return [x, y, x + _num(el.attrs.get("width")), y + _num(el.attrs.get("height"))]
    if tag in ("title", "style", "desc", "defs"):
        return None
    box = None
    for c in el.children:
        b = _bbox(c)
        if b is None:
            continue
        if box is None:
            box = list(b)
        else:
            box = [min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3])]
    return box
