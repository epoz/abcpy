"""Accidentals of each standard key signature (port of ``const/key-accidentals.js``)."""

from ..jsutil import Obj
from .relative_major import relative_major

key1sharp = {'acc': 'sharp', 'note': 'f'}
key2sharp = {'acc': 'sharp', 'note': 'c'}
key3sharp = {'acc': 'sharp', 'note': 'g'}
key4sharp = {'acc': 'sharp', 'note': 'd'}
key5sharp = {'acc': 'sharp', 'note': 'A'}
key6sharp = {'acc': 'sharp', 'note': 'e'}
key7sharp = {'acc': 'sharp', 'note': 'B'}
key1flat = {'acc': 'flat', 'note': 'B'}
key2flat = {'acc': 'flat', 'note': 'e'}
key3flat = {'acc': 'flat', 'note': 'A'}
key4flat = {'acc': 'flat', 'note': 'd'}
key5flat = {'acc': 'flat', 'note': 'G'}
key6flat = {'acc': 'flat', 'note': 'c'}
key7flat = {'acc': 'flat', 'note': 'F'}

keys = {
    'C#': [key1sharp, key2sharp, key3sharp, key4sharp, key5sharp, key6sharp, key7sharp],
    'F#': [key1sharp, key2sharp, key3sharp, key4sharp, key5sharp, key6sharp],
    'B': [key1sharp, key2sharp, key3sharp, key4sharp, key5sharp],
    'E': [key1sharp, key2sharp, key3sharp, key4sharp],
    'A': [key1sharp, key2sharp, key3sharp],
    'D': [key1sharp, key2sharp],
    'G': [key1sharp],
    'C': [],
    'F': [key1flat],
    'Bb': [key1flat, key2flat],
    'Eb': [key1flat, key2flat, key3flat],
    'Cm': [key1flat, key2flat, key3flat],
    'Ab': [key1flat, key2flat, key3flat, key4flat],
    'Db': [key1flat, key2flat, key3flat, key4flat, key5flat],
    'Gb': [key1flat, key2flat, key3flat, key4flat, key5flat, key6flat],
    'Cb': [key1flat, key2flat, key3flat, key4flat, key5flat, key6flat, key7flat],

    # The following are not in the 2.0 spec, but seem normal enough.
    'A#': [key1flat, key2flat],
    'B#': [],
    'D#': [key1flat, key2flat, key3flat],
    'E#': [key1flat],
    'G#': [key1flat, key2flat, key3flat, key4flat],
    'none': [],
}


def key_accidentals(key):
    """Return a fresh list of accidentals for the key, or None if it isn't recognized."""
    new_key = keys.get(relative_major(key))
    if new_key is None:  # If we don't recognize the key then there is no change
        return None
    return [Obj(a) for a in new_key]
