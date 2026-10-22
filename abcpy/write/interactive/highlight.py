"""Highlighting of drawn elements (port of ``highlight.js`` and ``unhighlight.js``)."""

from ..helpers.set_class import set_class


def highlight(abs_elem, klass=None, color=None):
    if klass is None:
        klass = "abcjs-note_selected"
    if color is None:
        color = "#ff0000"
    set_class(abs_elem.elemset, klass, "", color)


def unhighlight(abs_elem, klass=None, color=None):
    if klass is None:
        klass = "abcjs-note_selected"
    if color is None:
        color = "#000000"
    set_class(abs_elem.elemset, "", klass, color)
