"""Creates the accompaniment ("boom-chick") track from the chord symbols (port of ``chord-track.js``).

The algorithm for chords is:
- The chords are done in a separate track.
- If there are notes before the first chord, then put that much silence to start the track.
- The pattern of chord expression depends on the meter, and how many chords are in a measure.
- If a chord root is not A-G, then ignore it as if the chord wasn't there at all.
- If a chord modification isn't in our supported list, change it to a major triad.
- There is a standard pattern of boom-chick for each time sig, or it can be overridden.
- For any unrecognized meter, play the full chord on each beat.
- If there is any note in the melody that has a rhythm head, then assume the melody controls the rhythm,
  so there is no chord added for that entire measure.
"""

import math

from ..jsutil import Obj, assign, at, js_round, number, parse_int, js_str, js_floor


def _time_to_real_time(time):
    return time / 1000000


def _duration_rounded(duration, tempo_change_factor):
    return js_round(duration * tempo_change_factor * 1000000) / 1000000


break_synonyms = ['break', '(break)', 'no chord', 'n.c.', 'tacet']

basses = {'A': 33, 'B': 35, 'C': 36, 'D': 38, 'E': 40, 'F': 41, 'G': 43}

chord_intervals = {
    # unusual chords
    "-addb2": [0, 1, 3, 7],
    "maddb2": [0, 1, 3, 7],
    "addb2": [0, 1, 4, 7],
    "susb2": [0, 1, 7],
    "-add2": [0, 2, 3, 7],
    "madd2": [0, 2, 3, 7],
    "add2": [0, 2, 4, 7],
    "sus2": [0, 2, 7],
    "-7sus2": [0, 2, 7, 10],
    "7sus2": [0, 2, 7, 10],
    "m7sus2": [0, 2, 7, 10],
    "min7sus2": [0, 2, 7, 10],
    "7sus2/9": [0, 2, 7, 10, 14],
    "add#2": [0, 3, 4, 7],
    "-add4": [0, 3, 5, 7],
    "madd4": [0, 3, 5, 7],
    # diminished chords
    "dim": [0, 3, 6],
    "m(b5)": [0, 3, 6],
    "°": [0, 3, 6],
    "˚": [0, 3, 6],
    "-add#4": [0, 3, 6, 7],
    "madd#4": [0, 3, 6, 7],
    "dim7": [0, 3, 6, 9],
    "°7": [0, 3, 6, 9],
    "˚7": [0, 3, 6, 9],
    "-7(b5)": [0, 3, 6, 10],
    "-7b5": [0, 3, 6, 10],
    "m7(b5)": [0, 3, 6, 10],
    "m7b5": [0, 3, 6, 10],
    "ø": [0, 3, 6, 10],
    "ø7": [0, 3, 6, 10],
    # minor chords
    "-": [0, 3, 7],
    "m": [0, 3, 7],
    "-(b6)": [0, 3, 7, 8],
    "-b6": [0, 3, 7, 8],
    "m(b6)": [0, 3, 7, 8],
    "mb6": [0, 3, 7, 8],
    "-6": [0, 3, 7, 9],
    "m6": [0, 3, 7, 9],
    "-6(9)": [0, 3, 7, 9, 14],
    "-6/9": [0, 3, 7, 9, 14],
    "-69": [0, 3, 7, 9, 14],
    "m6(9)": [0, 3, 7, 9, 14],
    "m6/9": [0, 3, 7, 9, 14],
    "m69": [0, 3, 7, 9, 14],
    "-7": [0, 3, 7, 10],
    "m7": [0, 3, 7, 10],
    "-7(b9)": [0, 3, 7, 10, 13],
    "-7b9": [0, 3, 7, 10, 13],
    "-7(9)": [0, 3, 7, 10, 14],
    "-7/9": [0, 3, 7, 10, 14],
    "-9": [0, 3, 7, 10, 14],
    "m7(9)": [0, 3, 7, 10, 14],
    "m7/9": [0, 3, 7, 10, 14],
    "m9": [0, 3, 7, 10, 14],
    "-7(9,11)": [0, 3, 7, 10, 14, 17],
    "-7/9/11": [0, 3, 7, 10, 14, 17],
    "m7(9,11)": [0, 3, 7, 10, 14, 17],
    "m7/9/11": [0, 3, 7, 10, 14, 17],
    "-13": [0, 3, 7, 10, 14, 17, 21],
    "-7(9,11,13)": [0, 3, 7, 10, 14, 17, 21],
    "-7/9/11/13": [0, 3, 7, 10, 14, 17, 21],
    "m13": [0, 3, 7, 10, 14, 17, 21],
    "m7(9,11,13)": [0, 3, 7, 10, 14, 17, 21],
    "m7/9/11/13": [0, 3, 7, 10, 14, 17, 21],
    "-7(9,13)": [0, 3, 7, 10, 14, 21],
    "-7/9/13": [0, 3, 7, 10, 14, 21],
    "m7(9,13)": [0, 3, 7, 10, 14, 21],
    "m7/9/13": [0, 3, 7, 10, 14, 21],
    "-7(11)": [0, 3, 7, 10, 17],
    "-7/11": [0, 3, 7, 10, 17],
    "m7(11)": [0, 3, 7, 10, 17],
    "m7/11": [0, 3, 7, 10, 17],
    "-7(11,13)": [0, 3, 7, 10, 17, 21],
    "-7/11/13": [0, 3, 7, 10, 17, 21],
    "m7(11,13)": [0, 3, 7, 10, 17, 21],
    "m7/11/13": [0, 3, 7, 10, 17, 21],
    "-(maj7)": [0, 3, 7, 11],
    "-7M": [0, 3, 7, 11],
    "-maj7": [0, 3, 7, 11],
    "-∆7": [0, 3, 7, 11],
    "m(maj7)": [0, 3, 7, 11],
    "mM7": [0, 3, 7, 11],
    "min(maj7)": [0, 3, 7, 11],
    "-9+7": [0, 3, 7, 11, 13],
    "-(maj9)": [0, 3, 7, 11, 14],
    "-7M(9)": [0, 3, 7, 11, 14],
    "-maj9": [0, 3, 7, 11, 14],
    "-∆9": [0, 3, 7, 11, 14],
    "m(maj9)": [0, 3, 7, 11, 14],
    "mM9": [0, 3, 7, 11, 14],
    "min(maj9)": [0, 3, 7, 11, 14],
    "-11": [0, 3, 7, 11, 14, 17],
    "m11": [0, 3, 7, 11, 14, 17],
    "-addb9": [0, 3, 7, 13],
    "maddb9": [0, 3, 7, 13],
    "-add9": [0, 3, 7, 14],
    "madd9": [0, 3, 7, 14],
    "-add11": [0, 3, 7, 17],
    "madd11": [0, 3, 7, 17],
    "-add#11": [0, 3, 7, 18],
    "madd#11": [0, 3, 7, 18],
    # altered minor chords
    "-#5": [0, 3, 8],
    "-(#5)": [0, 3, 8],
    "m#5": [0, 3, 8],
    "m(#5)": [0, 3, 8],
    "-7#5": [0, 3, 8, 10],
    "-7(#5)": [0, 3, 8, 10],
    "dim7(b13)": [0, 3, 9, 20],
    "°7(b13)": [0, 3, 9, 20],
    "˚7(b13)": [0, 3, 9, 20],
    # altered major chords
    "add4": [0, 4, 5, 7],
    "maj(b5)": [0, 4, 6],
    "majb5": [0, 4, 6],
    "add#4": [0, 4, 6, 7],
    "7(b5)": [0, 4, 6, 10],
    "7b5": [0, 4, 6, 10],
    "7(b5,b9)": [0, 4, 6, 10, 13],
    "7(b9,b5)": [0, 4, 6, 10, 13],
    "7b5(b9)": [0, 4, 6, 10, 13],
    "7b9,b5": [0, 4, 6, 10, 13],
    "7b9b5": [0, 4, 6, 10, 13],
    "7(b5,b9,b13)": [0, 4, 6, 10, 13, 20],
    "7/b5/b9/b13": [0, 4, 6, 10, 13, 20],
    "7b5/b9/b13": [0, 4, 6, 10, 13, 20],
    "7(b5,b9,13)": [0, 4, 6, 10, 13, 21],
    "7/b5/b9/13": [0, 4, 6, 10, 13, 21],
    "7b5/b9/13": [0, 4, 6, 10, 13, 21],
    "7(9,b5)": [0, 4, 6, 10, 14],
    "7(b5,9)": [0, 4, 6, 10, 14],
    "7b5(9)": [0, 4, 6, 10, 14],
    "9b5": [0, 4, 6, 10, 14],
    "13(b5)": [0, 4, 6, 10, 14, 21],
    "13b5": [0, 4, 6, 10, 14, 21],
    "7(b5,9,13)": [0, 4, 6, 10, 14, 21],
    "7/b5/9/13": [0, 4, 6, 10, 14, 21],
    "7b5/9/13": [0, 4, 6, 10, 14, 21],
    "7#9b5": [0, 4, 6, 10, 15],
    "7(#9,b5)": [0, 4, 6, 10, 15],
    "7(b5,#9)": [0, 4, 6, 10, 15],
    "7b5(#9)": [0, 4, 6, 10, 15],
    "7(b5,#9,b13)": [0, 4, 6, 10, 15, 20],
    "7/b5/#9/b13": [0, 4, 6, 10, 15, 20],
    "7b5/#9/b13": [0, 4, 6, 10, 15, 20],
    "7(b5,#9,13)": [0, 4, 6, 10, 15, 21],
    "7/b5/#9/13": [0, 4, 6, 10, 15, 21],
    "7b5/#9/13": [0, 4, 6, 10, 15, 21],
    "7(b5,b13)": [0, 4, 6, 10, 20],
    "7/b5/b13": [0, 4, 6, 10, 20],
    "7b5/b13": [0, 4, 6, 10, 20],
    "7(b5,13)": [0, 4, 6, 10, 21],
    "7/b5/13": [0, 4, 6, 10, 21],
    "7b5(13)": [0, 4, 6, 10, 21],
    "7b5/13": [0, 4, 6, 10, 21],
    "7M(b5)": [0, 4, 6, 11],
    "maj7(b5)": [0, 4, 6, 11],
    "maj7b5": [0, 4, 6, 11],
    "7M(b5,9)": [0, 4, 6, 11, 14],
    "maj7(b5,9)": [0, 4, 6, 11, 14],
    "maj7b5/9": [0, 4, 6, 11, 14],
    "7M(b5,9,13)": [0, 4, 6, 11, 14, 21],
    "maj7(b5,9,13)": [0, 4, 6, 11, 14, 21],
    "maj7b5/9/13": [0, 4, 6, 11, 14, 21],
    "7M(b5,13)": [0, 4, 6, 11, 21],
    "maj7(b5,13)": [0, 4, 6, 11, 21],
    "maj7b5/13": [0, 4, 6, 11, 21],
    # major chords
    "M": [0, 4, 7],
    "Δ": [0, 4, 7],
    "∆": [0, 4, 7],
    "6": [0, 4, 7, 9],
    "6(9)": [0, 4, 7, 9, 14],
    "6/9": [0, 4, 7, 9, 14],
    "69": [0, 4, 7, 9, 14],
    "6add9": [0, 4, 7, 9, 14],
    "6(9,11)": [0, 4, 7, 9, 14, 17],
    "6/9/11": [0, 4, 7, 9, 14, 17],
    "6911": [0, 4, 7, 9, 14, 17],
    "6(9,#11)": [0, 4, 7, 9, 14, 18],
    "6/9/#11": [0, 4, 7, 9, 14, 18],
    "69#11": [0, 4, 7, 9, 14, 18],
    "6(11)": [0, 4, 7, 9, 17],
    "6/11": [0, 4, 7, 9, 17],
    "611": [0, 4, 7, 9, 17],
    "6#11": [0, 4, 7, 9, 18],
    "6(#11)": [0, 4, 7, 9, 18],
    "6/#11": [0, 4, 7, 9, 18],
    "7": [0, 4, 7, 10],
    "7(b9)": [0, 4, 7, 10, 13],
    "7b9": [0, 4, 7, 10, 13],
    "7(9)": [0, 4, 7, 10, 14],
    "7/9": [0, 4, 7, 10, 14],
    "9": [0, 4, 7, 10, 14],
    "7(9,11)": [0, 4, 7, 10, 14, 17],
    "7/9/11": [0, 4, 7, 10, 14, 17],
    "7(9,11,13)": [0, 4, 7, 10, 14, 17, 21],
    "7/9/11/13": [0, 4, 7, 10, 14, 17, 21],
    "7#11": [0, 4, 7, 10, 14, 18],
    "7(#11)": [0, 4, 7, 10, 14, 18],
    "9#11": [0, 4, 7, 10, 14, 18],
    "9(#11)": [0, 4, 7, 10, 14, 18],
    "(13)": [0, 4, 7, 10, 14, 21],
    "13": [0, 4, 7, 10, 14, 21],
    "7(9,13)": [0, 4, 7, 10, 14, 21],
    "7/9/13": [0, 4, 7, 10, 14, 21],
    "9/13": [0, 4, 7, 10, 14, 21],
    "7#9": [0, 4, 7, 10, 15],
    "7(#9)": [0, 4, 7, 10, 15],
    "7(#9,b13)": [0, 4, 7, 10, 15, 20],
    "7(11)": [0, 4, 7, 10, 17],
    "7/11": [0, 4, 7, 10, 17],
    "7(11,13)": [0, 4, 7, 10, 17, 21],
    "7/11/13": [0, 4, 7, 10, 17, 21],
    "13#11": [0, 4, 7, 10, 18, 21],
    "13(#11)": [0, 4, 7, 10, 18, 21],
    "7(b13)": [0, 4, 7, 10, 20],
    "7b13": [0, 4, 7, 10, 20],
    "7(13)": [0, 4, 7, 10, 21],
    "7/13": [0, 4, 7, 10, 21],
    "7M": [0, 4, 7, 11],
    "maj7": [0, 4, 7, 11],
    "Δ7": [0, 4, 7, 11],
    "∆7": [0, 4, 7, 11],
    "7M(9)": [0, 4, 7, 11, 14],
    "7M/9": [0, 4, 7, 11, 14],
    "maj7(9)": [0, 4, 7, 11, 14],
    "maj7/9": [0, 4, 7, 11, 14],
    "maj9": [0, 4, 7, 11, 14],
    "Δ9": [0, 4, 7, 11, 14],
    "∆9": [0, 4, 7, 11, 14],
    "7M(9,11)": [0, 4, 7, 11, 14, 17],
    "7M/9/11": [0, 4, 7, 11, 14, 17],
    "maj11": [0, 4, 7, 11, 14, 17],
    "maj7(9,11)": [0, 4, 7, 11, 14, 17],
    "maj7/9/11": [0, 4, 7, 11, 14, 17],
    "Δ11": [0, 4, 7, 11, 14, 17],
    "∆11": [0, 4, 7, 11, 14, 17],
    "7M(9,11,13)": [0, 4, 7, 11, 14, 17, 21],
    "7M/9/11/13": [0, 4, 7, 11, 14, 17, 21],
    "maj13": [0, 4, 7, 11, 14, 17, 21],
    "maj7(9,11,13)": [0, 4, 7, 11, 14, 17, 21],
    "maj7/9/11/13": [0, 4, 7, 11, 14, 17, 21],
    "Δ11(13)": [0, 4, 7, 11, 14, 17, 21],
    "Δ13": [0, 4, 7, 11, 14, 17, 21],
    "∆11(13)": [0, 4, 7, 11, 14, 17, 21],
    "7M(9,#11)": [0, 4, 7, 11, 14, 18],
    "7M/9/#11": [0, 4, 7, 11, 14, 18],
    "maj7(9,#11)": [0, 4, 7, 11, 14, 18],
    "maj7/9/#11": [0, 4, 7, 11, 14, 18],
    "maj9#11": [0, 4, 7, 11, 14, 18],
    "maj9(#11)": [0, 4, 7, 11, 14, 18],
    "maj9/#11": [0, 4, 7, 11, 14, 18],
    "Δ9(#11)": [0, 4, 7, 11, 14, 18],
    "7M(9,#11,13)": [0, 4, 7, 11, 14, 18, 21],
    "7M/9/#11/13": [0, 4, 7, 11, 14, 18, 21],
    "maj13#11": [0, 4, 7, 11, 14, 18, 21],
    "maj13(#11)": [0, 4, 7, 11, 14, 18, 21],
    "maj13/#11": [0, 4, 7, 11, 14, 18, 21],
    "Δ13(#11)": [0, 4, 7, 11, 14, 18, 21],
    "∆13(#11)": [0, 4, 7, 11, 14, 18, 21],
    "7M(9,13)": [0, 4, 7, 11, 14, 21],
    "7M/9/13": [0, 4, 7, 11, 14, 21],
    "maj7(9,13)": [0, 4, 7, 11, 14, 21],
    "maj7/9/13": [0, 4, 7, 11, 14, 21],
    "maj9(13)": [0, 4, 7, 11, 14, 21],
    "Δ9(13)": [0, 4, 7, 11, 14, 21],
    "∆9(13)": [0, 4, 7, 11, 14, 21],
    "7M(11)": [0, 4, 7, 11, 17],
    "7M/11": [0, 4, 7, 11, 17],
    "maj7(11)": [0, 4, 7, 11, 17],
    "maj7/11": [0, 4, 7, 11, 17],
    "Δ7(11)": [0, 4, 7, 11, 17],
    "∆7(11)": [0, 4, 7, 11, 17],
    "7M(#11)": [0, 4, 7, 11, 18],
    "7M/#11": [0, 4, 7, 11, 18],
    "maj7(#11)": [0, 4, 7, 11, 18],
    "maj7/#11": [0, 4, 7, 11, 18],
    "Δ7(#11)": [0, 4, 7, 11, 18],
    "∆7(#11)": [0, 4, 7, 11, 18],
    "7M(13)": [0, 4, 7, 11, 21],
    "7M/13": [0, 4, 7, 11, 21],
    "maj7(13)": [0, 4, 7, 11, 21],
    "maj7/13": [0, 4, 7, 11, 21],
    "Δ7(13)": [0, 4, 7, 11, 21],
    "∆7(13)": [0, 4, 7, 11, 21],
    "addb9": [0, 4, 7, 13],
    "add9": [0, 4, 7, 14],
    "add#9": [0, 4, 7, 15],
    "add11": [0, 4, 7, 17],
    "add#11": [0, 4, 7, 18],
    # augmented chords
    "+": [0, 4, 8],
    "aug": [0, 4, 8],
    "+7": [0, 4, 8, 10],
    "7#5": [0, 4, 8, 10],
    "7(#5)": [0, 4, 8, 10],
    "7+5": [0, 4, 8, 10],
    "aug7": [0, 4, 8, 10],
    "7(b9,#5)": [0, 4, 8, 10, 13],
    "7b9#5": [0, 4, 8, 10, 13],
    "9#5": [0, 4, 8, 10, 14],
    "9(#5)": [0, 4, 8, 10, 14],
    "9+5": [0, 4, 8, 10, 14],
    "13#5": [0, 4, 8, 10, 14, 21],
    "13(#5)": [0, 4, 8, 10, 14, 21],
    "7M(#5)": [0, 4, 8, 11],
    "maj7#5": [0, 4, 8, 11],
    "maj7(#5)": [0, 4, 8, 11],
    "7M(#5,9)": [0, 4, 8, 11, 14],
    "maj7#5/9": [0, 4, 8, 11, 14],
    "maj7(#5,9)": [0, 4, 8, 11, 14],
    "maj7#5#11": [0, 4, 8, 11, 18],
    "maj7(#5,#11)": [0, 4, 8, 11, 18],
    # sus4 chords
    "sus": [0, 5, 7],
    "sus4": [0, 5, 7],
    "-7sus4": [0, 5, 7, 10],
    "7sus": [0, 5, 7, 10],
    "7sus4": [0, 5, 7, 10],
    "m7sus4": [0, 5, 7, 10],
    "min7sus4": [0, 5, 7, 10],
    "7sus(b9)": [0, 5, 7, 10, 13],
    "7sus4(b9)": [0, 5, 7, 10, 13],
    "-9sus4": [0, 5, 7, 10, 14],
    "7sus4(9)": [0, 5, 7, 10, 14],
    "7sus4/9": [0, 5, 7, 10, 14],
    "9sus": [0, 5, 7, 10, 14],
    "9sus4": [0, 5, 7, 10, 14],
    "m9sus4": [0, 5, 7, 10, 14],
    "min9sus4": [0, 5, 7, 10, 14],
    "11sus4": [0, 5, 7, 10, 14, 17],
    "13sus4": [0, 5, 7, 10, 14, 21],
    "7sus(#9)": [0, 5, 7, 10, 15],
    "7sus4(#9)": [0, 5, 7, 10, 15],
    "7sus4(11)": [0, 5, 7, 10, 17],
    "7sus4(13)": [0, 5, 7, 10, 21],
    "7Msus": [0, 5, 7, 11],
    "7Msus4": [0, 5, 7, 11],
    "maj7sus": [0, 5, 7, 11],
    "maj7sus4": [0, 5, 7, 11],
    # power chords and unusual chords
    "#4": [0, 6],
    "b5": [0, 6],
    "sus#4": [0, 6, 7],
    "7Msus#4": [0, 6, 11],
    "maj7sus#4": [0, 6, 11],
    "5": [0, 7],
    "11": [0, 7, 10, 14, 17],
    "5(8)": [0, 7, 12],
    "5add8": [0, 7, 12],
    "5(9)": [0, 7, 14],
    "5add9": [0, 7, 14],
    "#5": [0, 8],
    "b6": [0, 8],
}

rhythm_patterns = {
    "2/2": ['boom', '', '', '', 'chick', '', '', ''],
    "3/2": ['boom', '', '', '', 'chick', '', '', '', 'chick', '', '', ''],
    "4/2": ['boom', '', '', '', 'chick', '', '', '', 'boom', '', '', '', 'chick', '', '', ''],

    "2/4": ['boom', '', 'chick', ''],
    "3/4": ['boom', '', 'chick', '', 'chick', ''],
    "4/4": ['boom', '', 'chick', '', 'boom', '', 'chick', ''],
    "5/4": ['boom', '', 'chick', '', 'chick', '', 'boom', '', 'chick', ''],
    "6/4": ['boom', '', 'chick', '', 'boom', '', 'chick', '', 'boom', '', 'chick', ''],

    "3/8": ['boom', '', 'chick'],
    "5/8": ['boom', 'chick', 'chick', 'boom', 'chick'],
    "6/8": ['boom', '', 'chick', 'boom', '', 'chick'],
    "7/8": ['boom', 'chick', 'chick', 'boom', 'chick', 'boom', 'chick'],
    "9/8": ['boom', '', 'chick', 'boom', '', 'chick', 'boom', '', 'chick'],
    "10/8": ['boom', 'chick', 'chick', 'boom', 'chick', 'chick', 'boom', 'chick', 'boom', 'chick'],
    "11/8": ['boom', 'chick', 'chick', 'boom', 'chick', 'chick', 'boom', 'chick', 'boom', 'chick', 'chick'],
    "12/8": ['boom', '', 'chick', 'boom', '', 'chick', 'boom', '', 'chick', 'boom', '', 'chick'],
}


class ChordTrack:
    def __init__(self, num_voices, chords_off, midi_options, meter):
        self.chordTrack = []
        self.chordTrackFinished = False
        self.chordChannel = num_voices  # first free channel for chords
        self.currentChords = []
        self.lastChord = None
        self.chordLastBar = None
        self.chordsOff = bool(chords_off)
        self.gChordTacet = self.chordsOff
        self.hasRhythmHead = False
        self.transpose = 0
        self.lastBarTime = 0
        self.meter = meter
        self.tempoChangeFactor = 1

        bassprog = midi_options.get('bassprog')
        chordprog = midi_options.get('chordprog')
        bassvol = midi_options.get('bassvol')
        chordvol = midi_options.get('chordvol')
        gchord = midi_options.get('gchord')
        # To allow for bass and chord instrument octave shifts
        self.bassInstrument = bassprog[0] if bassprog and len(bassprog) >= 1 else 0
        self.chordInstrument = chordprog[0] if chordprog and len(chordprog) >= 1 else 0

        # For octave shifted bass and chords
        self.bassOctaveShift = bassprog[1] if bassprog and len(bassprog) == 2 else 0
        self.chordOctaveShift = chordprog[1] if chordprog and len(chordprog) == 2 else 0

        self.boomVolume = bassvol[0] if bassvol and len(bassvol) == 1 else 64
        self.chickVolume = chordvol[0] if chordvol and len(chordvol) == 1 else 48

        # This allows for an initial %%MIDI gchord with no string
        if gchord and len(gchord) > 0:
            self.overridePattern = _parse_gchord(gchord[0])
        else:
            self.overridePattern = None

    def set_meter(self, meter):
        self.meter = meter

    def set_tempo_change_factor(self, tempo_change_factor):
        self.tempoChangeFactor = tempo_change_factor

    def set_last_bar_time(self, last_bar_time):
        self.lastBarTime = last_bar_time

    def set_transpose(self, transpose):
        self.transpose = transpose

    def set_rhythm_head(self, is_rhythm_head, elem=None):
        self.hasRhythmHead = is_rhythm_head
        e_pitches = []
        if is_rhythm_head:
            if self.lastChord and self.lastChord.chick:
                for c in self.lastChord.chick:
                    note2 = assign(elem.pitches[0])
                    note2.actualPitch = c
                    e_pitches.append(note2)
        return e_pitches

    def bar_end(self, element):
        if len(self.chordTrack) > 0 and not self.chordTrackFinished:
            self.resolve_chords(self.lastBarTime, _time_to_real_time(element.time))
            self.currentChords = []
        self.chordLastBar = self.lastChord

    def g_chord_on(self, element):
        if not self.chordsOff:
            self.gChordTacet = element.tacet

    def param_change(self, element):
        t = element.el_type
        if t == "gchord":
            # Skips gchord elements that don't have pattern strings
            if element.param and len(element.param) > 0:
                self.overridePattern = _parse_gchord(element.param)
            else:
                self.overridePattern = None
        elif t == "bassprog":
            self.bassInstrument = element.value
            self.bassOctaveShift = element.octaveShift if element.octaveShift is not None else 0
        elif t == "chordprog":
            self.chordInstrument = element.value
            self.chordOctaveShift = element.octaveShift if element.octaveShift is not None else 0
        elif t == "bassvol":
            self.boomVolume = element.param
        elif t == "chordvol":
            self.chickVolume = element.param

    def finish(self):
        if not self.chord_track_empty():  # Don't do chords on more than one track, so turn off chord detection after we create it.
            self.chordTrackFinished = True

    def add_track(self, tracks):
        if not self.chord_track_empty():
            tracks.append(self.chordTrack)

    def find_chord(self, elem):
        if self.gChordTacet:
            return 'break'

        # TODO-PER: Just using the first chord if there are more than one.
        if self.chordTrackFinished or not elem.chord or len(elem.chord) == 0:
            return None

        # Return the first annotation that is a regular chord: that is, it is in the default place or is a recognized "tacet" phrase.
        for ch in elem.chord:
            if ch.position == 'default':
                return ch.name
            if ch.name.lower() in break_synonyms:
                return 'break'
        return None

    def interpret_chord(self, name):
        # chords have the format:
        # [root][acc][modifier][/][bass][acc]
        # (The chord might be surrounded by parens. Just ignore them.)
        if len(name) == 0:
            return None
        if name == 'break':
            return Obj(chick=[])
        root = name[0:1]
        if root == '(':
            name = name[1:len(name) - 1]
            if len(name) == 0:
                return None
            root = name[0:1]
        bass = basses.get(root)
        if not bass:  # If the bass note isn't listed, then this was an unknown root. Only A-G are accepted.
            return None
        # Don't transpose the chords more than an octave.
        chord_transpose = self.transpose
        while chord_transpose < -8:
            chord_transpose += 12
        while chord_transpose > 8:
            chord_transpose -= 12
        bass += chord_transpose

        # If transposed below A or above G, bring it back in the normal backup range
        if bass < 33:
            bass += 12
        elif bass > 44:
            bass -= 12

        # Supporting octave shifted bass and chords
        unshifted_bass = bass

        bass += self.bassOctaveShift * 12

        bass2 = bass - 5  # The alternating bass is a 4th below
        remaining = name[1:]
        acc = remaining[0:1]
        if acc == 'b' or acc == '♭':
            unshifted_bass -= 1
            bass -= 1
            bass2 -= 1
            remaining = remaining[1:]
        elif acc == '#' or acc == '♯':
            unshifted_bass += 1
            bass += 1
            bass2 += 1
            remaining = remaining[1:]
        arr = remaining.split('/')
        chick = self.chord_notes(unshifted_bass, arr[0])
        # If the 5th is altered then the bass is altered. Normally the bass is 7 from the root, so adjust if it isn't.
        if len(chick) >= 3:
            fifth = chick[2] - chick[0]
            bass2 = bass2 + fifth - 7

        if len(arr) == 2:
            explicit_bass = basses.get(arr[1][0:1])
            if explicit_bass:
                bass_acc = arr[1][1:]
                bass_shift = {'#': 1, '♯': 1, 'b': -1, '♭': -1}.get(bass_acc) or 0
                bass = basses[arr[1][0:1]] + bass_shift + chord_transpose

                # Supporting octave shifted bass and chords
                bass += self.bassOctaveShift * 12

                bass2 = bass
        return Obj(boom=bass, boom2=bass2, chick=chick)

    def chord_notes(self, bass, modifier):
        # accept either chord spelling
        modifier = modifier.replace('♭', 'b').replace('♯', '#')

        intervals = chord_intervals.get(modifier)
        if not intervals:
            # If the chord isn't in our list, we can at least guess whether it is major or minor.
            if modifier[0:2].lower() == 'ma' or modifier[0:1] == 'M':
                intervals = chord_intervals['M']
            elif modifier[0:1] == 'm' or modifier[0:1] == '-':
                intervals = chord_intervals['m']
            else:
                intervals = chord_intervals['M']
        bass += 12  # the chord is an octave above the bass note.

        # For chick octave shift
        bass += (self.chordOctaveShift * 12)

        return [bass + i for i in intervals]

    def write_note(self, note, beat_length, volume, beat, note_length, instrument):
        # undefined means there is a stop time.
        if note is not None:
            self.chordTrack.append(Obj(cmd='note', pitch=note, volume=volume,
                                       start=self.lastBarTime + beat * _duration_rounded(beat_length, self.tempoChangeFactor),
                                       duration=_duration_rounded(note_length, self.tempoChangeFactor), gap=0, instrument=instrument))

    def chord_track_empty(self):
        for ev in self.chordTrack:
            if ev.cmd == 'note':
                return False
        return True

    def resolve_chords(self, start_time, end_time):
        # If there is a rhythm head anywhere in the measure then don't add a separate rhythm track
        if self.hasRhythmHead:
            return

        num = self.meter.num
        den = self.meter.den
        n_num = number(num)
        n_den = number(den)
        beat_length = 1 / n_den
        note_length = beat_length / 2
        this_measure_length = parse_int(num, 10) / parse_int(den, 10)
        portion_of_a_measure = this_measure_length - (end_time - start_time) / self.tempoChangeFactor
        if abs(portion_of_a_measure) < 0.00001:
            portion_of_a_measure = 0

        # there wasn't a new chord this measure, so use the last chord declared.
        # also the case where there is a chord declared in the measure, but not on its first beat.
        if len(self.currentChords) == 0 or self.currentChords[0].beat != 0:
            self.currentChords.insert(0, Obj(beat=0, chord=self.chordLastBar))

        current_chords_expanded = _expand_current_chords(self.currentChords, 8 * n_num / n_den, beat_length)
        this_pattern = self.overridePattern if self.overridePattern is not None else rhythm_patterns.get(js_str(num) + '/' + js_str(den))
        if portion_of_a_measure:
            this_pattern = []
            beats_present = ((end_time - start_time) / self.tempoChangeFactor) * 8
            p = 0
            while p < beats_present / 2:
                this_pattern.append("chick")
                this_pattern.append("")
                p += 2
        if this_pattern is None:
            this_pattern = []
            p = 0
            while p < (8 * n_num / n_den) / 2:
                this_pattern.append('chick')
                this_pattern.append("")
                p += 1
        first_boom = True
        # If the pattern is overridden, it might be longer than the length of a measure. If so, then ignore the rest of it
        min_length = min(len(this_pattern), len(current_chords_expanded))
        for p in range(min_length):
            prev = current_chords_expanded[p - 1] if p > 0 else None
            cur = current_chords_expanded[p]
            if p > 0 and prev and cur and prev.boom != cur.boom:
                first_boom = True
            typ = this_pattern[p]
            is_boom = 'boom' in typ
            # If we changed chords at a time when we're not expecting a bass note, then add an extra bass note in if the first thing in the pattern is a bass note.
            new_bass = (not is_boom and p != 0 and 'boom' in this_pattern[0] and
                        (not prev or prev.boom != (cur.boom if cur else None)))
            pitches = _resolve_pitch(cur, typ, first_boom, new_bass)
            if is_boom:
                first_boom = False
            for pitch in pitches:
                self.write_note(pitch,
                                0.125,
                                self.boomVolume if (is_boom or new_bass) else self.chickVolume,
                                p,
                                note_length,
                                self.bassInstrument if (is_boom or new_bass) else self.chordInstrument)
                if new_bass:
                    new_bass = False
                else:
                    is_boom = False  # only the first note in a chord is a bass note. This handles the case where bass and chord are played at the same time.

    def process_chord(self, elem):
        if self.chordTrackFinished:
            return
        chord = self.find_chord(elem)
        if chord:
            c = self.interpret_chord(chord)
            # If this isn't a recognized chord, just completely ignore it.
            if c:
                # If we ever have a chord in this voice, then we add the chord track.
                # However, if there are chords on more than one voice, then just use the first voice.
                if len(self.chordTrack) == 0:
                    self.chordTrack.append(Obj(cmd='program', channel=self.chordChannel, instrument=self.chordInstrument))

                self.lastChord = c
                bar_beat = _calc_beat(self.lastBarTime, _time_to_real_time(elem.time))
                self.currentChords.append(Obj(chord=self.lastChord, beat=bar_beat, start=_time_to_real_time(elem.time)))


def _resolve_pitch(current_chord, typ, first_boom, new_bass):
    ret = []
    if not current_chord:
        return ret
    if 'boom' in typ:
        ret.append(current_chord.boom if first_boom else current_chord.boom2)
    elif new_bass:
        ret.append(current_chord.boom)
    if 'chick' in typ:
        ret.extend(current_chord.chick)
    chick = current_chord.chick
    if typ == 'DO':
        ret.append(at(chick, 0))
    elif typ == 'MI':
        ret.append(at(chick, 1))
    elif typ == 'SOL':
        ret.append(_extract_note(current_chord, 2))
    elif typ == 'TI':
        ret.append(_extract_note(current_chord, 3))
    elif typ == 'TOP':
        ret.append(_extract_note(current_chord, 4))
    elif typ == 'do':
        ret.append(_plus12(at(chick, 0)))
    elif typ == 'mi':
        ret.append(_plus12(at(chick, 1)))
    elif typ == 'sol':
        ret.append(_plus12(_extract_note(current_chord, 2)))
    elif typ == 'ti':
        ret.append(_plus12(_extract_note(current_chord, 3)))
    elif typ == 'top':
        ret.append(_plus12(_extract_note(current_chord, 4)))
    return ret


def _plus12(n):
    return n + 12 if n is not None else float('nan')


def _extract_note(chord, index):
    # This creates an arpeggio note no matter how many notes are in the chord - if it runs out of notes it continues in the next octave
    if len(chord.chick) == 0:
        return float('nan')
    octave = js_floor(index / len(chord.chick))
    note = chord.chick[index % len(chord.chick)]
    return note + octave * 12


def _parse_gchord(gchord):
    # TODO-PER: The spec is more complicated than this but for now this will not try to do anything with error cases like the wrong number of beats.
    table = {'z': '', '2': '', 'c': 'chick', 'b': 'boom&chick', 'f': 'boom', 'G': 'DO', 'H': 'MI', 'I': 'SOL',
             'J': 'TI', 'K': 'TOP', 'g': 'do', 'h': 'mi', 'i': 'sol', 'j': 'ti', 'k': 'top'}
    return [table[ch] for ch in gchord if ch in table]


def _expand_current_chords(current_chords, num8th_notes, beat_length):
    # This returns an array that has a chord for each 1/8th note position in the current measure
    chords = []
    if len(current_chords) == 0:
        return chords

    current_chord = current_chords[0].chord
    for current in current_chords[1:]:
        while len(chords) < current.beat:
            chords.append(current_chord)
        current_chord = current.chord
    while len(chords) < num8th_notes:
        chords.append(current_chord)
    return chords


def _calc_beat(measure_start, curr_time):
    distance_from_start = curr_time - measure_start
    return distance_from_start * 8
