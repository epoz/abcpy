"""Transpose the text of an abc string (port of ``str/output.js``, abcjs's ``strTranspose``).

Unlike the ``visualTranspose`` parse option, this rewrites the abc source: the
key signatures, notes, grace notes and chord symbols are changed and the new
abc string is returned.
"""

import re

from ..jsutil import Obj, parse_int, is_nan
from ..const.key_accidentals import key_accidentals
from ..const.relative_major import relative_major, transpose_key, relative_mode, is_legal_mode
from ..parse.transpose_chord import transpose_chord_name

letters = "CDEFGAB"
octaves = [",,,,", ",,,", ",,", ",", "", "'", "''", "'''", "''''"]


def _letter_index(ch):
    if not ch:
        return -1
    return letters.find(ch) if len(ch) == 1 else -1


def str_transpose(abc, abc_tune, steps):
    """Transpose ``abc`` by ``steps`` half steps.

    ``abc_tune`` is the list of parsed tunes for ``abc`` (the result of
    :func:`abcpy.parse_only`).  Returns the transposed abc string.
    """
    if abc_tune == "TEST":  # Backdoor way to get entry points for unit tests
        return Obj(keyAccidentals=key_accidentals, relativeMajor=relative_major, transposeKey=transpose_key,
                   relativeMode=relative_mode, transposeChordName=transpose_chord_name)
    steps = parse_int(steps, 10)
    if is_nan(steps):
        steps = 0
    changes = []
    if not isinstance(abc_tune, list):
        abc_tune = [abc_tune]
    for t in abc_tune:
        changes = changes + _transpose_one_tune(abc, t, steps)

    # Reverse sort so that we are replacing strings from the end to the beginning so that the indexes aren't invalidated as we go.
    # (Because voices can be written in different ways we can't count on the notes being encountered in the order they appear in the string.)
    changes.sort(key=lambda c: -c.start)
    output = list(abc)
    for ch in changes:
        output[ch.start:ch.end] = [ch.note]
    return ''.join(output)


def _transpose_one_tune(abc, abc_tune, steps):
    changes = []

    # Don't transpose bagpipe music - that is a special case and is always a particular key
    key = abc_tune.get_key_signature()
    if key.root == 'Hp' or key.root == "HP":
        return changes

    changes = changes + _change_all_key_sigs(abc, steps)

    for line in abc_tune.lines:
        staves = line.staff
        if staves:
            for staff in staves:
                if staff.clef.type != "perc":
                    changes = changes + _transpose_voices(abc, staff.voices, staff.key, steps)
    return changes


_key_re = re.compile(r"^( *)([A-G])([#b]?)( ?)(\w*)")


def _change_all_key_sigs(abc, steps):
    changes = []
    arr = abc.split("K:")
    # now each line except the first one will start with whatever is right after "K:"
    count = len(arr[0])
    for segment in arr[1:]:
        match = _key_re.match(segment)
        if match:
            start = count + 2 + len(match.group(1))  # move past the 'K:' and optional white space
            mode = match.group(5) if is_legal_mode(match.group(5)) else ''
            key = match.group(2) + match.group(3) + match.group(4) + mode  # key name, accidental, optional space, and mode
            destination_key = _new_key(Obj(root=match.group(2), acc=match.group(3), mode=mode), steps)
            dest = destination_key.root + destination_key.acc + match.group(4) + destination_key.mode
            changes.append(Obj(start=start, end=start + len(key), note=dest))
        count += len(segment) + 2
    return changes


def _transpose_voices(abc, voices, key, steps):
    changes = []
    destination_key = _new_key(key, steps)
    for voice in voices:
        changes = changes + _transpose_voice(abc, voice, key.root, _create_key_accidentals(key), destination_key, steps)
    return changes


def _create_key_accidentals(key):
    ret = {}
    for acc in key.accidentals:
        if acc.acc == 'flat':
            ret[acc.note.upper()] = '_'
        elif acc.acc == 'sharp':
            ret[acc.note.upper()] = '^'
    return ret


def _set_letter_distance(destination_key, key_root, steps):
    letter_distance = _letter_index(destination_key.root) - _letter_index(key_root)
    if key_root == "none":
        letter_distance = _letter_index(destination_key.root)
    if letter_distance == 0:
        # This could either be a half step (like Eb => E) or almost an octave (like E => Eb)
        if steps > 2:  # If it is a large leap, then we are going up an octave
            letter_distance += 7
        elif steps == -12:  # If it is a large leap, then we are going down an octave
            letter_distance -= 7
    elif steps > 0 and letter_distance < 0:
        letter_distance += 7
    elif steps < 0 and letter_distance > 0:
        letter_distance -= 7

    if steps > 12:
        letter_distance += 7
    elif steps < -12:
        letter_distance -= 7

    return letter_distance


def _transpose_voice(abc, voice, key_root, key_accs, destination_key, steps):
    changes = []
    letter_distance = _set_letter_distance(destination_key, key_root, steps)

    measure_accidentals = {}
    transposed_measure_accidentals = {}
    for el in voice:
        if el.chord:
            for ch in el.chord:
                if ch.position == 'default':
                    prefers_flats = bool(destination_key.accidentals) and destination_key.accidentals[0].acc == 'flat'
                    new_chord = transpose_chord_name(ch.name, steps, prefers_flats, True)
                    new_chord = new_chord.replace("♭", "b").replace("♯", "#")
                    if new_chord != ch.name:  # If we didn't recognize the chord the input is returned unchanged and there is nothing to replace
                        changes.append(_replace_chord(abc, el.startChar, el.endChar, new_chord))
        if el.el_type == 'note' and el.pitches:
            pitch_array = _find_notes(abc, el.startChar, el.endChar)
            for p in pitch_array:
                note = _parse_note(p.note, key_root, key_accs, measure_accidentals)
                if note.acc:
                    measure_accidentals[note.name.upper()] = note.acc
                new_pitch = _transpose_pitch(note, destination_key, letter_distance, transposed_measure_accidentals)
                if new_pitch.acc:
                    transposed_measure_accidentals[new_pitch.upper] = new_pitch.acc
                changes.append(Obj(note=new_pitch.acc + new_pitch.name, start=p.index, end=p.index + len(p.note)))
            if el.gracenotes:
                for g in range(len(el.gracenotes)):
                    grace = _parse_note(el.gracenotes[g].name, key_root, key_accs, measure_accidentals)
                    if grace.acc:
                        measure_accidentals[grace.name.upper()] = grace.acc
                    new_grace = _transpose_pitch(grace, destination_key, letter_distance, measure_accidentals)
                    if new_grace.acc:
                        transposed_measure_accidentals[new_grace.upper] = new_grace.acc
                    changes.append(_replace_grace(abc, el.startChar, el.endChar, new_grace.acc + new_grace.name, g))
        elif el.el_type == "bar":
            measure_accidentals = {}
            transposed_measure_accidentals = {}
        elif el.el_type == "keySignature":
            key_root = el.root
            key_accs = _create_key_accidentals(el)
            destination_key = _new_key(el, steps)
            letter_distance = _set_letter_distance(destination_key, key_root, steps)
    return changes


def _new_key(key, steps):
    if key.root == "none":
        return Obj(root=transpose_key("C", steps), mode="", acc="", accidentals=[])
    major = relative_major(key.root + key.acc + key.mode)
    new_major = transpose_key(major, steps)
    new_mode = relative_mode(new_major, key.mode)
    acc = key_accidentals(new_major)
    return Obj(root=new_mode[0], mode=key.mode, acc=new_mode[1] if len(new_mode) > 1 else '', accidentals=acc)


def _transpose_pitch(note, key, letter_distance, measure_accidentals):
    # Depending on what the current note and new note are, the octave might have changed
    # The letterDistance is how far the change is to see if we passed "C" when transposing.
    pitch = note.pitch
    orig_dist_from_c = _letter_index(note.name)
    root = _letter_index(key.root)
    index = (root + pitch) % 7
    # if the note crosses "c" then the octave changes, so that is true of "B" when going up one step, "A" and "B" when going up two steps, etc., and reverse when going down.
    new_dist_from_c = orig_dist_from_c + letter_distance
    oct = note.oct
    while new_dist_from_c > 6:
        oct += 1
        new_dist_from_c -= 7
    while new_dist_from_c < 0:
        oct -= 1
        new_dist_from_c += 7

    name = letters[index]

    acc = ''
    adj = note.adj
    # the amount of adjustment depends on the key - if there is a sharp in the key sig, then -1 is a natural, if there isn't, then -1 is a flat.
    key_acc = '='
    for a in (key.accidentals or []):
        if a.note.lower() == name.lower():
            adj = adj + (-1 if a.acc == 'flat' else 1)
            key_acc = '_' if a.acc == 'flat' else '^'
            break
    if adj == -2:
        acc = "__"
    elif adj == -1:
        acc = "_"
    elif adj == 0:
        acc = "="
    elif adj == 1:
        acc = "^"
    elif adj == 2:
        acc = "^^"
    elif adj == -3:
        # This requires a triple flat, so bump down the pitch and try again
        new_note = Obj()
        new_note.pitch = note.pitch - 1
        new_note.oct = note.oct
        li = _letter_index(note.name) - 1
        new_note.name = letters[li] if li >= 0 else None
        if not new_note.name:
            new_note.name = "B"
            new_note.oct -= 1
        if new_note.name == "B" or new_note.name == "E":
            new_note.adj = note.adj + 1
        else:
            new_note.adj = note.adj + 2
        return _transpose_pitch(new_note, key, letter_distance + 1, measure_accidentals)
    elif adj == 3:
        # This requires a triple sharp, so bump up the pitch and try again
        new_note = Obj()
        new_note.pitch = note.pitch + 1
        new_note.oct = note.oct
        li = _letter_index(note.name) + 1
        new_note.name = letters[li] if 0 <= li < len(letters) else None
        if not new_note.name:
            new_note.name = "C"
            new_note.oct += 1
        if new_note.name == "C" or new_note.name == "F":
            new_note.adj = note.adj - 1
        else:
            new_note.adj = note.adj - 2
        return _transpose_pitch(new_note, key, letter_distance + 1, measure_accidentals)
    if (measure_accidentals.get(name) == acc or (not measure_accidentals.get(name) and acc == key_acc)) and not note.courtesy:
        acc = ""

    if oct == 0:
        name = name + ",,,"
    elif oct == 1:
        name = name + ",,"
    elif oct == 2:
        name = name + ","
    elif oct == 4:
        name = name.lower()
    elif oct == 5:
        name = name.lower() + "'"
    elif oct == 6:
        name = name.lower() + "''"
    elif oct == 7:
        name = name.lower() + "'''"
    elif oct == 8:
        name = name.lower() + "''''"
    if oct > 4:
        name = name.lower()

    return Obj(acc=acc, name=name, upper=name.upper())


_reg_pitch = re.compile(r"([_^=]*)([A-Ga-g])([,']*)")
_reg_optional_note = r"([_^=]*[A-Ga-g][,']*)?(\d*\/*\d*)?([\>\<\-\)]*)?"


def _parse_note(note, key_root, key_accs, measure_accidentals):
    # This the relationship of the note to the tonic and an octave. So what is returned is a distance in steps from the tonic and the amount of adjustment from
    # a normal scale. That is - in the key of D an F# is two steps from the tonic and no adjustment. A G# is three steps from the tonic and one half-step higher.
    root = 0 if key_root == "none" else _letter_index(key_root)
    reg = _reg_pitch.search(note)
    name = reg.group(2).upper()
    pos = _letter_index(name) - root
    if pos < 0:
        pos += 7
    oct = octaves.index(reg.group(3)) if reg.group(3) in octaves else -1
    if name == reg.group(2):  # See if it is a capital letter and subtract an octave if so.
        oct -= 1
    current_acc = measure_accidentals.get(name) or key_accs.get(name) or "="  # use the key accidentals if they exist, but override with the measure accidentals, and if neither of them exist, use a natural.
    return Obj(acc=reg.group(1), name=name, pitch=pos, oct=oct,
               adj=_calc_adjustment(reg.group(1), key_accs.get(name), measure_accidentals.get(name)),
               courtesy=reg.group(1) == current_acc)


def _find_notes(abc, start, end):
    note = abc[start:end]

    # Since the regex will also find "c", "d", and "a" in `!coda!`, we need to filter them
    ignore_blocks = []
    for m in re.finditer(r'("[^"]+")+', note):
        ignore_blocks.append(Obj(start=m.end() - len(m.group(0)), end=m.end()))
    for m in re.finditer(r"(![^!]+!)+", note):
        ignore_blocks.append(Obj(start=m.end() - len(m.group(0)), end=m.end()))

    ret = []
    for m in _reg_pitch.finditer(note):
        if len(m.group(0)) == 0:
            continue
        last_index = m.end()
        found = False
        for b in ignore_blocks:
            if b.start <= last_index <= b.end:
                found = True
        if not found:
            ret.append(Obj(note=m.group(0), index=start + last_index - len(m.group(0))))
    return ret


_reg_grace = None


def _replace_grace(abc, start, end, new_grace, index):
    global _reg_grace
    note = abc[start:end]
    # I don't know how to capture more than one note, so I'm separating them. There is a limit of the number of notes in a chord depending on the repeats I have here, but it is unlikely to happen in real music.
    if _reg_grace is None:
        pre_note = r"(\/*)"
        _reg_grace = re.compile(r"([^\{]*)" + r"\{" + (pre_note + _reg_optional_note) * 8 + r"\}")
    match = _reg_grace.search(note)
    if match:
        groups = [match.group(0)] + list(match.groups())

        def grp(n):
            return groups[n] if n < len(groups) else None

        # This will match all notes inside a grace symbol
        # Get the number of chars used by the previous graces
        count = 1 + len(grp(1))  # one character for the open brace, and whatever comes before the brace
        i = 0
        while i < index:  # index is the iteration through the chord. This function gets called for each one.
            for k in (2, 3, 4, 5):
                if grp(i * 3 + k):
                    count += len(grp(i * 3 + k))
            i += 1
        if grp(index * 3 + 2):
            count += len(grp(i * 3 + 2) or "")
        start += count
        end_len = len(grp(index * 3 + 3) or "")
        end_len += len(grp(index * 3 + 4) or "")
        end_len += len(grp(index * 3 + 5) or "")
        end = start + end_len
    return Obj(start=start, end=end, note=new_grace)


def _replace_chord(abc, start, end, new_chord):
    # Isolate the chord and just replace that
    match = re.search(r'([^"]+)?(".+")+', abc[start:end])
    if match.group(1):
        start += len(match.group(1))
    end = start + len(match.group(2))
    # leave the quote in, so skip one more
    return Obj(start=start + 1, end=end - 1, note=new_chord)


def _calc_adjustment(this_accidental, key_accidental, measure_accidental):
    if not this_accidental and measure_accidental:
        # There was no accidental on this note, but there was earlier in the measure, so we'll use that
        this_accidental = measure_accidental
    if not this_accidental:
        return 0  # there is no deviation from the key.

    if key_accidental is None:
        return {'__': -2, '_': -1, '=': 0, '^': 1, '^^': 2}.get(this_accidental, 0)
    if key_accidental == '_':
        return {'__': -1, '_': 0, '=': 1, '^': 2, '^^': 3}.get(this_accidental, 0)
    if key_accidental == '^':
        return {'__': -3, '_': -2, '=': -1, '^': 0, '^^': 1}.get(this_accidental, 0)
    return 0  # this should never happen
