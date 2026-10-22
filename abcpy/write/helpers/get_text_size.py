"""Measures text using the renderer (port of ``get-text-size.js``)."""

from ...jsutil import Obj
from .get_font_and_attr import get_family


class GetTextSize:
    def __init__(self, get_font_and_attr, svg):
        self.getFontAndAttr = get_font_and_attr
        self.svg = svg

    def update_fonts(self, font_overrides):
        self.getFontAndAttr.update_fonts(font_overrides)

    def attr(self, typ, klass=None):
        return self.getFontAndAttr.calc(typ, klass)

    get_family = staticmethod(get_family)

    def calc(self, text, typ, klass=None, el=None):
        # This can be passed in either a string or a font. If it is a string it names one of the standard fonts.
        if isinstance(typ, str):
            h = self.attr(typ, klass)
        else:
            attr = Obj()
            attr["font-size"] = typ.size
            attr["font-style"] = typ.style
            attr["font-family"] = get_family(typ.face)
            attr["font-weight"] = typ.weight
            attr["text-decoration"] = typ.decoration
            attr["class"] = self.getFontAndAttr.classes.generate(klass)
            h = Obj(font=Obj(face=typ.face, size=typ.size, decoration=typ.decoration, style=typ.style, weight=typ.weight), attr=attr)
        size = self.svg.get_text_size(text, h.attr, el)
        if h.font.box:
            # Add padding and an equal margin to each side.
            return Obj(height=size.height + h.font.padding * 4, width=size.width + h.font.padding * 4)
        return size

    def baseline_to_center(self, text, typ, klass, index, total):
        # This is for the case where SVG wants to use the baseline of the first line as the Y coordinate.
        # If there are multiple lines of text or there is an array of text then that will not be centered so this adjusts it.
        height = self.calc(text, typ, klass).height
        font_height = self.attr(typ, klass).font.size
        return height * 0.5 + (total - index - 2) * font_height
