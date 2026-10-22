"""Transposition of chord symbols (port of ``transpose-chord.js``)."""

import re

sharp_chords = ['C', 'C♯', 'D', "D♯", 'E', 'F', "F♯", 'G', 'G♯', 'A', 'A♯', 'B']
flat_chords = ['C', 'D♭', 'D', 'E♭', 'E', 'F', 'G♭', 'G', 'A♭', 'A', 'B♭', 'B']
sharp_chords_free = ['C', 'C#', 'D', "D#", 'E', 'F', "F#", 'G', 'G#', 'A', 'A#', 'B']
flat_chords_free = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']

_chord_re = re.compile(r"^([A-G][b#♭♯]?)([^/]+)?/?([A-G][b#♭♯]?)?(.+)?", re.S)


def _find(name):
    for table in (sharp_chords, flat_chords, sharp_chords_free, flat_chords_free):
        if name in table:
            return table.index(name)
    return -1


def transpose_chord_name(chord, steps, prefer_flats, free_gchord):
    if not steps or steps % 12 == 0:  # The chords are the same if it is an exact octave change.
        return chord

    while steps < 0:
        steps += 12
    if steps > 11:
        steps = steps % 12

    # (chord name w/accidental) (a bunch of stuff) (/) (bass note) (anything else)
    match = _chord_re.match(chord)
    if not match:
        return chord  # We don't recognize the format of the chord, so skip it.
    name, extra1, bass, extra2 = match.group(1), match.group(2), match.group(3), match.group(4)
    index = _find(name)
    if index < 0:
        return chord

    index = (index + steps) % 12

    if prefer_flats:
        chord = flat_chords_free[index] if free_gchord else flat_chords[index]
    else:
        chord = sharp_chords_free[index] if free_gchord else sharp_chords[index]

    is_dim = bool(extra1) and ('dim' in extra1 or '°' in extra1)
    # We never want A#dim or D#dim
    if is_dim and chord == 'A#':
        chord = 'Bb'
    if is_dim and chord == 'D#':
        chord = 'Eb'
    if is_dim and chord == 'A♯':
        chord = 'B♭'
    if is_dim and chord == 'D♯':
        chord = 'E♭'

    if extra1:
        chord += extra1

    if bass:
        index = _find(bass)
        chord += '/'
        if index >= 0:
            index = (index + steps) % 12
            if prefer_flats:
                chord += flat_chords_free[index] if free_gchord else flat_chords[index]
            else:
                chord += sharp_chords_free[index] if free_gchord else sharp_chords[index]
        else:
            chord += bass  # Don't know what to do so do nothing

    if extra2:
        chord += extra2

    return chord
