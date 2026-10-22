"""Creation of clefs, key signatures, time signatures and note heads.

Ports of ``create-clef.js``, ``create-key-signature.js``, ``create-time-signature.js``,
``create-note-head.js`` and ``translate-chord.js``.
"""

import re

from ...jsutil import Obj, at, js_str
from . import glyphs
from .elements import AbsoluteElement, RelativeElement


def _clef_offsets(clef):
    return {"clefs.G": -5, "clefs.C": -4, "clefs.F": -4, "clefs.perc": -2}.get(clef, 0)


def create_clef(elem, tune_number):
    clef = None
    octave = 0
    elem.el_type = "clef"
    abselem = AbsoluteElement(elem, 0, 10, 'staff-extra clef', tune_number)
    abselem.isClef = True
    t = elem.type
    table = {
        "treble": ("clefs.G", 0), "tenor": ("clefs.C", 0), "alto": ("clefs.C", 0), "bass": ("clefs.F", 0),
        'treble+8': ("clefs.G", 1), 'tenor+8': ("clefs.C", 1), 'bass+8': ("clefs.F", 1), 'alto+8': ("clefs.C", 1),
        'treble-8': ("clefs.G", -1), 'tenor-8': ("clefs.C", -1), 'bass-8': ("clefs.F", -1), 'alto-8': ("clefs.C", -1),
        'perc': ("clefs.perc", 0),
    }
    if t == 'none':
        return None
    if t in table:
        clef, octave = table[t]
    else:
        abselem.add_fixed(RelativeElement("clef=" + js_str(t), 0, 0, None, Obj(type="debug")))
    dx = 5
    if clef:
        height = glyphs.symbol_height_in_pitches(clef)
        ofs = _clef_offsets(clef)
        clef_pos = elem.clefPos
        abselem.add_right(RelativeElement(clef, dx, glyphs.get_symbol_width(clef), clef_pos,
                                          Obj(top=_add(_add(height, clef_pos), ofs), bottom=_add(clef_pos, ofs))))

        if octave != 0:
            scale = 2 / 3
            adjustspacing = (glyphs.get_symbol_width(clef) - glyphs.get_symbol_width("8") * scale) / 2
            pitch = _add(abselem.top, 3) if octave > 0 else _add(abselem.bottom, -1)
            top = _add(abselem.top, 3) if octave > 0 else _add(abselem.bottom, -3)
            bottom = _add(top, -2)
            if elem.type == "bass-8":
                # The placement for bass octave is a little different. It should hug the clef.
                pitch = 3
                adjustspacing = 0
            abselem.add_right(RelativeElement("8", dx + adjustspacing, glyphs.get_symbol_width("8") * scale, pitch,
                                              Obj(scalex=scale, scaley=scale, top=top, bottom=bottom)))
    return abselem


def _add(a, b):
    if a is None or b is None:
        return float('nan')
    return a + b


def create_key_signature(elem, tune_number):
    elem.el_type = "keySignature"
    if not elem.accidentals or len(elem.accidentals) == 0:
        return None
    abselem = AbsoluteElement(elem, 0, 10, 'staff-extra key-signature', tune_number)
    abselem.isKeySig = True
    dx = 0
    for acc in elem.accidentals:
        fudge = 0
        a = acc.acc
        if a == "sharp":
            symbol = "accidentals.sharp"
            fudge = -3
        elif a == "natural":
            symbol = "accidentals.nat"
        elif a == "flat":
            symbol = "accidentals.flat"
            fudge = -1.2
        elif a == "quartersharp":
            symbol = "accidentals.halfsharp"
            fudge = -2.5
        elif a == "quarterflat":
            symbol = "accidentals.halfflat"
            fudge = -1.2
        else:
            symbol = "accidentals.flat"
        h = glyphs.symbol_height_in_pitches(symbol)
        abselem.add_right(RelativeElement(symbol, dx, glyphs.get_symbol_width(symbol), acc.verticalPos,
                                          Obj(thickness=h, top=_add(acc.verticalPos, h + fudge), bottom=_add(acc.verticalPos, fudge))))
        dx += glyphs.get_symbol_width(symbol) + 2
    return abselem


def create_time_signature(elem, tune_number):
    elem.el_type = "timeSignature"
    abselem = AbsoluteElement(elem, 0, 10, 'staff-extra time-signature', tune_number)
    t = elem.type
    if t == "specified":
        x = 0
        for i in range(len(elem.value)):
            v = elem.value[i]
            if i != 0:
                abselem.add_right(RelativeElement('+', x + 1, glyphs.get_symbol_width("+"), 6, Obj(thickness=glyphs.symbol_height_in_pitches("+"))))
                x += glyphs.get_symbol_width("+") + 2
            if v.den:
                num_width = 0
                for ch in v.num:
                    num_width += glyphs.get_symbol_width(ch)
                den_width = 0
                for i2 in range(len(v.num)):
                    den_width += glyphs.get_symbol_width(at(v.den, i2))
                max_width = max(num_width, den_width)
                abselem.add_right(RelativeElement(v.num, x + (max_width - num_width) / 2, num_width, 8, Obj(thickness=glyphs.symbol_height_in_pitches(at(v.num, 0)))))
                abselem.add_right(RelativeElement(v.den, x + (max_width - den_width) / 2, den_width, 4, Obj(thickness=glyphs.symbol_height_in_pitches(at(v.den, 0)))))
                x += max_width
            else:
                this_width = 0
                for ch in v.num:
                    this_width += glyphs.get_symbol_width(ch)
                abselem.add_right(RelativeElement(v.num, x, this_width, 6, Obj(thickness=glyphs.symbol_height_in_pitches(at(v.num, 0)))))
                x += this_width
    else:
        names = {
            "common_time": "timesig.common", "cut_time": "timesig.cut",
            "tempus_imperfectum": "timesig.imperfectum", "tempus_imperfectum_prolatio": "timesig.imperfectum2",
            "tempus_perfectum": "timesig.perfectum", "tempus_perfectum_prolatio": "timesig.perfectum2",
        }
        if t in names:
            n = names[t]
            abselem.add_right(RelativeElement(n, 0, glyphs.get_symbol_width(n), 6, Obj(thickness=glyphs.symbol_height_in_pitches(n))))
    return abselem


_acc_symbols = {
    "quartersharp": "accidentals.halfsharp",
    "dblsharp": "accidentals.dblsharp",
    "sharp": "accidentals.sharp",
    "quarterflat": "accidentals.halfflat",
    "flat": "accidentals.flat",
    "dblflat": "accidentals.dblflat",
    "natural": "accidentals.nat",
}


def create_note_head(abselem, c, pitchelem, options=None):
    if not options:
        options = {}
    o = options
    d = o.get('dir') if o.get('dir') is not None else None
    headx = o.get('headx') if o.get('headx') is not None else 0
    extrax = o.get('extrax') if o.get('extrax') is not None else 0
    flag = o.get('flag') if o.get('flag') is not None else None
    dot = o.get('dot') if o.get('dot') is not None else 0
    dotshiftx = o.get('dotshiftx') if o.get('dotshiftx') is not None else 0
    scale = o.get('scale') if o.get('scale') is not None else 1
    accidental_slot = o.get('accidentalSlot') if o.get('accidentalSlot') is not None else []
    should_extend_stem = o.get('shouldExtendStem') if o.get('shouldExtendStem') is not None else False
    print_accidentals = o.get('printAccidentals') if o.get('printAccidentals') is not None else True
    chord_pos = o.get('chordPos')

    # TODO scale the dot as well
    pitch = pitchelem.verticalPos
    notehead = None
    accidentalshiftx = 0
    new_dot_shift_x = 0
    extra_left = 0
    if c is None:
        abselem.add_fixed(RelativeElement("pitch is undefined", 0, 0, 0, Obj(type="debug")))
    elif c == "":
        notehead = RelativeElement(None, 0, 0, pitch, Obj(chordPos=chord_pos))
    else:
        shiftheadx = headx
        if pitchelem.printer_shift:
            adjust = 1 if pitchelem.printer_shift == "same" else 0
            shiftheadx = (-glyphs.get_symbol_width(c) * scale + adjust) if d == "down" else (glyphs.get_symbol_width(c) * scale - adjust)
        opts = Obj(scalex=scale, scaley=scale, thickness=glyphs.symbol_height_in_pitches(c) * scale, name=pitchelem.name, chordPos=chord_pos)
        notehead = RelativeElement(c, shiftheadx, glyphs.get_symbol_width(c) * scale, pitch, opts)
        notehead.stemDir = d
        if flag:
            pos = _add(pitch, (-7 if d == "down" else 7) * scale)
            # if this is a regular note, (not grace or tempo indicator) then the stem will have been stretched to the middle line if it is far from the center.
            if should_extend_stem:
                if d == "down" and pos > 6:
                    pos = 6
                if d == "up" and pos < 6:
                    pos = 6
            xdelta = headx if d == "down" else headx + notehead.w - 0.6
            abselem.add_right(RelativeElement(flag, xdelta, glyphs.get_symbol_width(flag) * scale, pos, Obj(scalex=scale, scaley=scale, chordPos=chord_pos)))
        new_dot_shift_x = notehead.w + dotshiftx - 2 + 5 * dot
        while dot > 0:
            dotadjusty = 1 - abs(pitch) % 2  # PER: take abs value of the pitch. And the shift still happens on ledger lines.
            abselem.add_right(RelativeElement("dots.dot", notehead.w + dotshiftx - 2 + 5 * dot, glyphs.get_symbol_width("dots.dot"), pitch + dotadjusty, Obj(chordPos=chord_pos)))
            dot -= 1
    if notehead:
        notehead.highestVert = pitchelem.highestVert

    if print_accidentals and pitchelem.accidental:
        symb = _acc_symbols.get(pitchelem.accidental)
        # if a note is at least a sixth away, it can share a slot with another accidental
        acc_slot_found = False
        acc_place = extrax
        for slot in accidental_slot:
            if pitch - slot[0] >= 6:
                slot[0] = pitch
                acc_place = slot[1]
                acc_slot_found = True
                break
        if acc_slot_found is False:
            acc_place -= (glyphs.get_symbol_width(symb) * scale + 2)
            accidental_slot.append([pitch, acc_place])
            accidentalshiftx = (glyphs.get_symbol_width(symb) * scale + 2)
        h = glyphs.symbol_height_in_pitches(symb)
        abselem.add_extra(RelativeElement(symb, acc_place, glyphs.get_symbol_width(symb), pitch, Obj(scalex=scale, scaley=scale, top=pitch + h / 2, bottom=pitch - h / 2, chordPos=chord_pos)))
        extra_left = glyphs.get_symbol_width(symb) / 2  # TODO-PER: We need a little extra width if there is an accidental, but I'm not sure why it isn't the full width of the accidental.

    return Obj(notehead=notehead, accidentalshiftx=accidentalshiftx, dotshiftx=new_dot_shift_x, extraLeft=extra_left)


def _german_note(note):
    return {"B#": "H#", "B♯": "H♯", "B": "H", "Bb": "B", "B♭": "B"}.get(note, note)


_chord_re = re.compile(r"^([ABCDEFG][♯♭]?)?([^/]+)?(/([ABCDEFG][#b♯♭]?))?", re.S)


def translate_chord(chord_string, jazzchords, german_alphabet):
    lines = chord_string.split("\n")
    for i in range(len(lines)):
        chord = lines[i]
        # If the chord isn't in a recognizable format then just skip it.
        reg = _chord_re.match(chord)
        if not reg:
            continue
        base_chord = reg.group(1) or ""
        modifier = reg.group(2) or ""
        bass_note = reg.group(4) or ""
        if german_alphabet:
            base_chord = _german_note(base_chord)
            bass_note = _german_note(bass_note)
        # This puts markers in the pieces of the chord that are read by the svg creator.
        # After the main part of the chord (the letter, a sharp or flat, and "m") a marker is added. Before a slash a marker is added.
        marker = "\x03" if jazzchords else ""
        bass = "/" + bass_note if bass_note else ""
        lines[i] = marker.join([base_chord, modifier, bass])
    return "\n".join(lines)
