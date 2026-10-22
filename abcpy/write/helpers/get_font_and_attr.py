"""Turns a font description into SVG attributes (port of ``get-font-and-attr.js``)."""

from ...jsutil import Obj, js_round


def get_family(face):
    if face and face[0] == '"' and face[-1] == '"':
        return face[1:len(face) - 1]
    return face


class GetFontAndAttr:
    def __init__(self, formatting, classes):
        self.formatting = formatting
        self.classes = classes

    def update_fonts(self, font_overrides):
        if font_overrides.gchordfont:
            self.formatting.gchordfont = font_overrides.gchordfont
        if font_overrides.tripletfont:
            self.formatting.tripletfont = font_overrides.tripletfont
        if font_overrides.annotationfont:
            self.formatting.annotationfont = font_overrides.annotationfont
        if font_overrides.vocalfont:
            self.formatting.vocalfont = font_overrides.vocalfont

    get_family = staticmethod(get_family)

    def calc(self, typ, klass=None):
        if isinstance(typ, str):
            font = self.formatting[typ]
            # Raphael deliberately changes the font units to pixels for some reason, so we need to change points to pixels here.
            if font:
                font = Obj(face=font.face, size=js_round(font.size * 4 / 3), decoration=font.decoration, style=font.style, weight=font.weight, box=font.box)
            else:
                font = Obj(face="Arial", size=js_round(12 * 4 / 3), decoration="underline", style="normal", weight="normal")
        else:
            font = Obj(face=typ.face, size=js_round(typ.size * 4 / 3), decoration=typ.decoration, style=typ.style, weight=typ.weight, box=typ.box)
        padding_percent = self.formatting.fontboxpadding if self.formatting.fontboxpadding else 0.1
        font.padding = font.size * padding_percent

        attr = Obj()
        attr["font-size"] = font.size
        attr['font-style'] = font.style
        attr["font-family"] = get_family(font.face)
        attr['font-weight'] = font.weight
        attr['text-decoration'] = font.decoration
        attr['class'] = self.classes.generate(klass)
        return Obj(font=font, attr=attr)
