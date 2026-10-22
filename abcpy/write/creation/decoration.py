"""Creates the decorations of notes and bars (port of ``decoration.js``)."""

from ...jsutil import Obj, js_floor, js_max, js_min
from . import glyphs
from .elements import RelativeElement, TieElem, DynamicDecoration, CrescendoElem, GlissandoElem


def _close_decoration(voice, decoration, pitch, width, abselem, roomtaken, d, min_pitch, accent_above):
    y_pos = None
    for dec in decoration:
        if dec == "staccato" or dec == "tenuto" or (dec == "accent" and not accent_above):
            symbol = "scripts." + dec
            if dec == "accent":
                symbol = "scripts.sforzato"
            if y_pos is None:
                y_pos = pitch + 2 if d == "down" else min_pitch - 2
            else:
                y_pos = y_pos + 2 if d == "down" else y_pos - 2
            if dec == "accent":
                # Always place the accent three pitches away, no matter whether that is a line or space.
                if d == "up":
                    y_pos -= 1
                else:
                    y_pos += 1
            else:
                # don't place on a stave line. The stave lines are 2,4,6,8,10
                if y_pos in (2, 4, 6, 8, 10):
                    if d == "up":
                        y_pos -= 1
                    else:
                        y_pos += 1
            if pitch > 9:
                y_pos += 1  # take up some room of those that are above
            delta_x = width / 2
            if glyphs.get_symbol_align(symbol) != "center":
                delta_x -= (glyphs.get_symbol_width(symbol) / 2)
            abselem.add_fixed_x(RelativeElement(symbol, delta_x, glyphs.get_symbol_width(symbol), y_pos))
        if dec == "slide" and abselem.heads and abselem.heads[0]:
            y_pos2 = abselem.heads[0].pitch
            y_pos2 -= 2  # TODO-PER: not sure what this fudge factor is.
            blank1 = RelativeElement("", -roomtaken - 15, 0, y_pos2 - 1)
            blank2 = RelativeElement("", -roomtaken - 5, 0, y_pos2 + 1)
            abselem.add_fixed_x(blank1)
            abselem.add_fixed_x(blank2)
            voice.add_other(TieElem(Obj(anchor1=blank1, anchor2=blank2, fixedY=True)))
    if y_pos is None:
        y_pos = pitch

    return Obj(above=y_pos, below=abselem.bottom)


def _volume_decoration(voice, decoration, abselem, positioning):
    for dec in decoration:
        if dec in ("p", "mp", "pp", "ppp", "pppp", "f", "ff", "fff", "ffff", "sfz", "mf"):
            elem = DynamicDecoration(abselem, dec, positioning)
            voice.add_other(elem)


def _compound_decoration(decoration, pitch, width, abselem, d):
    def highest_pitch():
        if len(abselem.heads) == 0:
            return 10  # TODO-PER: I don't know if this can happen, but we'll return the top of the staff if so.
        p = abselem.heads[0].pitch
        for h in abselem.heads[1:]:
            p = max(p, h.pitch)
        return p

    def lowest_pitch():
        if len(abselem.heads) == 0:
            return 2  # TODO-PER: I don't know if this can happen, but we'll return the bottom of the staff if so.
        p = abselem.heads[0].pitch
        for h in abselem.heads[1:]:
            p = min(p, h.pitch)
        return p

    def compound(symbol, count):
        placement = lowest_pitch() + 1 if d == 'down' else highest_pitch() + 9
        if d != 'down' and count == 1:
            placement -= 1
        delta_x = width / 2
        delta_x += -5 if d == 'down' else 3
        for _ in range(count):
            placement -= 1
            abselem.add_fixed_x(RelativeElement(symbol, delta_x, glyphs.get_symbol_width(symbol), placement))

    for dec in decoration:
        if dec == "/":
            compound("flags.ugrace", 1)
        elif dec == "//":
            compound("flags.ugrace", 2)
        elif dec == "///":
            compound("flags.ugrace", 3)
        elif dec == "////":
            compound("flags.ugrace", 4)


_symbol_list = {
    "+": "scripts.stopped",
    "open": "scripts.open",
    "snap": "scripts.snap",
    "wedge": "scripts.wedge",
    "thumb": "scripts.thumb",
    "shortphrase": "scripts.shortphrase",
    "mediumphrase": "scripts.mediumphrase",
    "longphrase": "scripts.longphrase",
    "trill": "scripts.trill",
    "trillh": "scripts.trill",
    "roll": "scripts.roll",
    "irishroll": "scripts.roll",
    "marcato": "scripts.umarcato",
    "dmarcato": "scripts.dmarcato",
    "umarcato": "scripts.umarcato",
    "turn": "scripts.turn",
    "uppermordent": "scripts.prall",
    "pralltriller": "scripts.prall",
    "mordent": "scripts.mordent",
    "lowermordent": "scripts.mordent",
    "downbow": "scripts.downbow",
    "upbow": "scripts.upbow",
    "fermata": "scripts.ufermata",
    "invertedfermata": "scripts.dfermata",
    "breath": ",",
    "coda": "scripts.coda",
    "segno": "scripts.segno",
}


def _stacked_decoration(decoration, width, abselem, y_pos, positioning, min_top, min_bottom, accent_above):
    def increment_placement(placement, height):
        if placement == 'above':
            y_pos.above += height
        else:
            y_pos.below -= height

    def get_placement(placement):
        if placement == 'above':
            y = y_pos.above
            if y < min_top:
                y = min_top
        else:
            y = y_pos.below
            if y > min_bottom:
                y = min_bottom
        return y

    def text_decoration(text, placement, anchor):
        y = get_placement(placement)
        text_fudge = 2
        text_height = 5
        # TODO-PER: Get the height of the current font and use that for the thickness.
        abselem.add_fixed_x(RelativeElement(text, width / 2, 0, y + text_fudge, Obj(type="decoration", klass='ornament', thickness=3, anchor=anchor)))
        increment_placement(placement, text_height)

    def symbol_decoration(symbol, placement):
        delta_x = width / 2
        if glyphs.get_symbol_align(symbol) != "center":
            delta_x -= (glyphs.get_symbol_width(symbol) / 2)
        height = glyphs.symbol_height_in_pitches(symbol) + 1  # adding a little padding so nothing touches.
        y = get_placement(placement)
        y = y + height / 2 if placement == 'above' else y - height / 2  # Center the element vertically.
        abselem.add_fixed_x(RelativeElement(symbol, delta_x, glyphs.get_symbol_width(symbol), y, Obj(klass='ornament', thickness=glyphs.symbol_height_in_pitches(symbol), position=placement)))
        increment_placement(placement, height)

    has_one = False
    for dec in decoration:
        if dec in ("0", "1", "2", "3", "4", "5", "D.C.", "D.S."):
            text_decoration(dec, positioning, 'middle')
            has_one = True
        elif dec == "D.C.alcoda":
            text_decoration("D.C. al coda", positioning, 'end')
            has_one = True
        elif dec == "D.C.alfine":
            text_decoration("D.C. al fine", positioning, 'end')
            has_one = True
        elif dec == "D.S.alcoda":
            text_decoration("D.S. al coda", positioning, 'end')
            has_one = True
        elif dec == "D.S.alfine":
            text_decoration("D.S. al fine", positioning, 'end')
            has_one = True
        elif dec == "fine":
            text_decoration("FINE", positioning, 'middle')
            has_one = True
        elif dec in ("+", "open", "snap", "wedge", "thumb", "shortphrase", "mediumphrase", "longphrase", "trill",
                     "trillh", "roll", "irishroll", "marcato", "dmarcato", "turn", "uppermordent", "pralltriller",
                     "mordent", "lowermordent", "downbow", "upbow", "fermata", "breath", "umarcato", "coda", "segno"):
            symbol_decoration(_symbol_list[dec], positioning)
            has_one = True
        elif dec == "invertedfermata":
            symbol_decoration(_symbol_list[dec], 'below')
            has_one = True
        elif dec == "mark":
            abselem.klass = "mark"
        elif dec == "accent":
            if accent_above:
                symbol_decoration("scripts.sforzato", positioning)
                has_one = True
    return has_one


def _left_decoration(decoration, abselem, roomtaken):
    for dec in decoration:
        if dec == "arpeggio":
            # The arpeggio symbol is the height of a note (that is, two Y units). This stacks as many as we need to go from the
            # top note to the bottom note. The arpeggio should also be a little taller than the stacked notes, so there is an extra
            # one drawn and it is offset by half of a note height (that is, one Y unit).
            j = abselem.abcelem.minpitch - 1
            while j <= abselem.abcelem.maxpitch:
                abselem.add_extra(RelativeElement(
                    "scripts.arpeggio",
                    -glyphs.get_symbol_width("scripts.arpeggio") * 2 - roomtaken,
                    0,
                    j + 2,
                    Obj(klass='ornament', thickness=glyphs.symbol_height_in_pitches("scripts.arpeggio"))))
                j += 2


def _first_note(els):
    for e in els:
        if e.abcelem.pitches:
            return e
    return None


def _last_note(els):
    # The end point doesn't need to be a note - we end at the end of the line
    return els[-1] if els else None


class Decoration:
    def __init__(self):
        self.startDiminuendoX = None
        self.startCrescendoX = None
        self.startGlissandoX = None
        self.dynamicPositioning = None
        self.minTop = 12  # TODO-PER: this is assuming a 5-line staff. Pass that info in.
        self.minBottom = 0

    def end_line(self, voice):
        if self.startDiminuendoX:
            voice.add_other(CrescendoElem(self.startDiminuendoX, _last_note(voice.children), ">", self.dynamicPositioning))
            self.startDiminuendoX = None
        if self.startCrescendoX:
            voice.add_other(CrescendoElem(self.startCrescendoX, _last_note(voice.children), "<", self.dynamicPositioning))
            self.startCrescendoX = None

    def dynamic_decoration(self, voice, decoration, abselem, positioning):
        diminuendo = None
        crescendo = None
        glissando = None
        for dec in decoration:
            if dec == "diminuendo(":
                self.startDiminuendoX = abselem
                self.dynamicPositioning = positioning
                diminuendo = None
            elif dec == "diminuendo)":
                if not self.startDiminuendoX:
                    self.startDiminuendoX = _first_note(voice.children)
                diminuendo = Obj(start=self.startDiminuendoX, stop=abselem)
                self.startDiminuendoX = None
            elif dec == "crescendo(":
                self.startCrescendoX = abselem
                self.dynamicPositioning = positioning
                crescendo = None
            elif dec == "crescendo)":
                if not self.startCrescendoX:
                    self.startCrescendoX = _first_note(voice.children)
                crescendo = Obj(start=self.startCrescendoX, stop=abselem)
                self.startCrescendoX = None
            elif dec in ('~(', "glissando("):
                self.startGlissandoX = abselem
                glissando = None
            elif dec in ('~)', "glissando)"):
                glissando = Obj(start=self.startGlissandoX, stop=abselem)
                self.startGlissandoX = None
        if diminuendo:
            voice.add_other(CrescendoElem(diminuendo.start, diminuendo.stop, ">", positioning))
        if crescendo:
            voice.add_other(CrescendoElem(crescendo.start, crescendo.stop, "<", positioning))
        if glissando:
            voice.add_other(GlissandoElem(glissando.start, glissando.stop))

    def create_decoration(self, voice, decoration, pitch, width, abselem, roomtaken, d, min_pitch, positioning, has_vocals, accent_above):
        if not positioning:
            positioning = Obj(ornamentPosition='above', volumePosition='above' if has_vocals else 'below', dynamicPosition='above' if has_vocals else 'below')
        # These decorations don't affect the placement of other decorations
        _volume_decoration(voice, decoration, abselem, positioning.volumePosition)
        self.dynamic_decoration(voice, decoration, abselem, positioning.dynamicPosition)
        _compound_decoration(decoration, pitch, width, abselem, d)

        # treat staccato, accent, and tenuto first (may need to shift other markers)
        y_pos = _close_decoration(voice, decoration, pitch, width, abselem, roomtaken, d, min_pitch, accent_above)
        # yPos is an object containing 'above' and 'below'. That is the placement of the next symbol on either side.

        y_pos.above = js_max(y_pos.above, self.minTop)
        y_pos.below = js_min(y_pos.below, min_pitch)
        _stacked_decoration(decoration, width, abselem, y_pos, positioning.ornamentPosition, self.minTop, min_pitch, accent_above)
        _left_decoration(decoration, abselem, roomtaken)
