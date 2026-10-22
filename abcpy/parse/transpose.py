"""Automatic transposition of key signatures, chord symbols, and notes while parsing.

Port of abcjs ``abc_transpose.js``.
"""

import math
import re

from ..jsutil import Obj, at, substr, truthy, js_floor, js_ceil
from ..const.key_accidentals import key_accidentals
from . import all_notes
from .transpose_chord import transpose_chord_name

key_index = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5, 'F#': 6, 'Gb': 6,
    'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11,
}
new_key = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
new_key_minor = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'Bb', 'B']


def key_signature(mv, key_name, root, acc, local_transpose):
    if mv.clef.type == "perc" or mv.clef.type == "none":
        return Obj(accidentals=key_accidentals(key_name), root=root, acc=acc)
    if not local_transpose:
        local_transpose = 0
    mv.localTransposeVerticalMovement = 0
    mv.localTransposePreferFlats = False
    k = key_accidentals(key_name)
    if k is None:
        return mv.key  # If the key isn't in the list, it is non-standard. We won't attempt to transpose it.
    mv.localTranspose = (mv.globalTranspose if truthy(mv.globalTranspose) else 0) + local_transpose

    if not mv.localTranspose:
        return Obj(accidentals=k, root=root, acc=acc)
    mv.globalTransposeOrigKeySig = k
    if mv.localTranspose % 12 == 0:
        mv.localTransposeVerticalMovement = (mv.localTranspose / 12) * 7
        if mv.localTransposeVerticalMovement == int(mv.localTransposeVerticalMovement):
            mv.localTransposeVerticalMovement = int(mv.localTransposeVerticalMovement)
        return Obj(accidentals=k, root=root, acc=acc)

    base_key = at(key_name, 0)
    if at(key_name, 1) == 'b' or at(key_name, 1) == '#':
        base_key += key_name[1]
        key_name = substr(key_name, 2)
    else:
        key_name = substr(key_name, 1)
    this_key_index = key_index.get(base_key)
    recognized = this_key_index is not None
    if not recognized:
        # Either the key sig is "none" or we don't recognize it. Either way we don't change it, and we assume key of C for the purposes of this calculation.
        this_key_index = 0
        base_key = "C"
        key_name = ""
    index = this_key_index + mv.localTranspose
    while index < 0:
        index += 12
    if index > 11:
        index = index % 12
    new_key_name = new_key_minor[index] if at(key_name, 0) == 'm' else new_key[index]
    transposed_key = new_key_name + key_name
    new_key_sig = key_accidentals(transposed_key)
    if len(new_key_sig) == 0 or new_key_sig[0].acc == 'flat':  # key of C and all keys with flats should have chords with flats
        mv.localTransposePreferFlats = True
    distance = ord(transposed_key[0]) - ord(base_key[0])
    if mv.localTranspose > 0:
        if distance < 0:
            distance += 7
        elif distance == 0:
            # There's a funny thing that happens when the key changes only an accidental's distance, for instance, from Ab to A.
            if at(base_key, 1) == '#' or at(transposed_key, 1) == 'b':
                distance += 7
    elif mv.localTranspose < 0:
        if distance > 0:
            distance -= 7
        elif distance == 0:
            if at(base_key, 1) == 'b' or at(transposed_key, 1) == '#':
                distance -= 7

    if mv.localTranspose > 0:
        mv.localTransposeVerticalMovement = distance + js_floor(mv.localTranspose / 12) * 7
    else:
        mv.localTransposeVerticalMovement = distance + js_ceil(mv.localTranspose / 12) * 7
    if recognized:
        return Obj(accidentals=new_key_sig, root=new_key_name[0], acc=new_key_name[1] if len(new_key_name) > 1 else "")
    return Obj(accidentals=[], root=root, acc=acc)


def chord_name(mv, chord):
    return transpose_chord_name(chord, mv.localTranspose, mv.localTransposePreferFlats, mv.freegchord)


pitch_to_letter = ['c', 'd', 'e', 'f', 'g', 'a', 'b']

accidentals = {
    'dblflat': -2,
    'flat': -1,
    'natural': 0,
    'sharp': 1,
    'dblsharp': 2,
}
accidentals2 = {
    -2: "dblflat",
    -1: "flat",
    0: "natural",
    1: "sharp",
    2: "dblsharp",
}
accidentals3 = {
    -2: "__",
    -1: "_",
    0: "=",
    1: "^",
    2: "^^",
}


def _accidental_change(orig_pitch, new_pitch, accidental, orig_key_sig, new_key_sig):
    orig_pitch_letter = pitch_to_letter[(orig_pitch + 49) % 7]  # Make sure it is a positive pitch before normalizing.
    orig_accidental = 0
    for a in orig_key_sig:
        if a.note.lower() == orig_pitch_letter:
            orig_accidental = accidentals.get(a.acc)

    current_accidental = accidentals.get(accidental)
    if current_accidental is None or orig_accidental is None:
        delta = float('nan')
    else:
        delta = current_accidental - orig_accidental

    new_pitch_letter = pitch_to_letter[(new_pitch + 49) % 7]
    new_accidental = 0
    for a in new_key_sig.accidentals:
        if a.note.lower() == new_pitch_letter:
            new_accidental = accidentals.get(a.acc)
    calc_accidental = delta + new_accidental if new_accidental is not None else float('nan')
    if calc_accidental < -2:
        new_pitch -= 1
        calc_accidental += 1 if (new_pitch_letter == 'c' or new_pitch_letter == 'f') else 2
    if calc_accidental > 2:
        new_pitch += 1
        calc_accidental -= 1 if (new_pitch_letter == 'b' or new_pitch_letter == 'e') else 2
    return [new_pitch, calc_accidental]


def note(mv, el):
    # the "el" that is passed in has el.name, el.accidental, and el.pitch. "pitch" is the vertical position (0=middle C)
    # localTranspose is the number of half steps
    # localTransposeVerticalMovement is the vertical distance to move.
    if not mv.localTranspose or mv.clef.type == "perc":
        return
    orig_pitch = el.pitch
    if mv.localTransposeVerticalMovement:
        el.pitch = el.pitch + mv.localTransposeVerticalMovement
        if el.name:
            actual = el.name[1:] if el.accidental else el.name
            acc = el.name[0] if el.accidental else ''
            p = all_notes.pitch_index(actual)
            name = all_notes.note_name(p + mv.localTransposeVerticalMovement)
            el.name = acc + (name if name is not None else "undefined")

    if el.accidental:
        ret = _accidental_change(orig_pitch, el.pitch, el.accidental, mv.globalTransposeOrigKeySig, mv.targetKey)
        el.pitch = ret[0]
        acc_num = ret[1]
        if isinstance(acc_num, float) and acc_num == acc_num and acc_num == int(acc_num):
            acc_num = int(acc_num)  # the lookup tables are keyed by integers
        new_acc = accidentals2.get(acc_num)
        if new_acc is None:
            del el.accidental
        else:
            el.accidental = new_acc
        if el.name:
            prefix = accidentals3.get(acc_num)
            el.name = (prefix if prefix is not None else "undefined") + re.sub(r"[_^=]", "", el.name)
