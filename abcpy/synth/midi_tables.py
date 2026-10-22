"""Small MIDI helper tables and conversions.

Ports of ``instrument-index-to-name.js``, ``pitch-to-note-name.js``,
``note-to-midi.js``, ``cents-to-factor.js`` and ``pitches-to-perc.js``.
"""

import math
import re

from ..jsutil import parse_int, js_floor

instrument_index_to_name = [
    "acoustic_grand_piano",
    "bright_acoustic_piano",
    "electric_grand_piano",
    "honkytonk_piano",
    "electric_piano_1",
    "electric_piano_2",
    "harpsichord",
    "clavinet",
    "celesta",
    "glockenspiel",
    "music_box",
    "vibraphone",
    "marimba",
    "xylophone",
    "tubular_bells",
    "dulcimer",
    "drawbar_organ",
    "percussive_organ",
    "rock_organ",
    "church_organ",
    "reed_organ",
    "accordion",
    "harmonica",
    "tango_accordion",
    "acoustic_guitar_nylon",
    "acoustic_guitar_steel",
    "electric_guitar_jazz",
    "electric_guitar_clean",
    "electric_guitar_muted",
    "overdriven_guitar",
    "distortion_guitar",
    "guitar_harmonics",
    "acoustic_bass",
    "electric_bass_finger",
    "electric_bass_pick",
    "fretless_bass",
    "slap_bass_1",
    "slap_bass_2",
    "synth_bass_1",
    "synth_bass_2",
    "violin",
    "viola",
    "cello",
    "contrabass",
    "tremolo_strings",
    "pizzicato_strings",
    "orchestral_harp",
    "timpani",
    "string_ensemble_1",
    "string_ensemble_2",
    "synth_strings_1",
    "synth_strings_2",
    "choir_aahs",
    "voice_oohs",
    "synth_choir",
    "orchestra_hit",
    "trumpet",
    "trombone",
    "tuba",
    "muted_trumpet",
    "french_horn",
    "brass_section",
    "synth_brass_1",
    "synth_brass_2",
    "soprano_sax",
    "alto_sax",
    "tenor_sax",
    "baritone_sax",
    "oboe",
    "english_horn",
    "bassoon",
    "clarinet",
    "piccolo",
    "flute",
    "recorder",
    "pan_flute",
    "blown_bottle",
    "shakuhachi",
    "whistle",
    "ocarina",
    "lead_1_square",
    "lead_2_sawtooth",
    "lead_3_calliope",
    "lead_4_chiff",
    "lead_5_charang",
    "lead_6_voice",
    "lead_7_fifths",
    "lead_8_bass_lead",
    "pad_1_new_age",
    "pad_2_warm",
    "pad_3_polysynth",
    "pad_4_choir",
    "pad_5_bowed",
    "pad_6_metallic",
    "pad_7_halo",
    "pad_8_sweep",
    "fx_1_rain",
    "fx_2_soundtrack",
    "fx_3_crystal",
    "fx_4_atmosphere",
    "fx_5_brightness",
    "fx_6_goblins",
    "fx_7_echoes",
    "fx_8_scifi",
    "sitar",
    "banjo",
    "shamisen",
    "koto",
    "kalimba",
    "bagpipe",
    "fiddle",
    "shanai",
    "tinkle_bell",
    "agogo",
    "steel_drums",
    "woodblock",
    "taiko_drum",
    "melodic_tom",
    "synth_drum",
    "reverse_cymbal",
    "guitar_fret_noise",
    "breath_noise",
    "seashore",
    "bird_tweet",
    "telephone_ring",
    "helicopter",
    "applause",
    "gunshot",
    "percussion",
]

pitch_to_note_name = {
    21: 'A0',
    22: 'Bb0',
    23: 'B0',
    24: 'C1',
    25: 'Db1',
    26: 'D1',
    27: 'Eb1',
    28: 'E1',
    29: 'F1',
    30: 'Gb1',
    31: 'G1',
    32: 'Ab1',
    33: 'A1',
    34: 'Bb1',
    35: 'B1',
    36: 'C2',
    37: 'Db2',
    38: 'D2',
    39: 'Eb2',
    40: 'E2',
    41: 'F2',
    42: 'Gb2',
    43: 'G2',
    44: 'Ab2',
    45: 'A2',
    46: 'Bb2',
    47: 'B2',
    48: 'C3',
    49: 'Db3',
    50: 'D3',
    51: 'Eb3',
    52: 'E3',
    53: 'F3',
    54: 'Gb3',
    55: 'G3',
    56: 'Ab3',
    57: 'A3',
    58: 'Bb3',
    59: 'B3',
    60: 'C4',
    61: 'Db4',
    62: 'D4',
    63: 'Eb4',
    64: 'E4',
    65: 'F4',
    66: 'Gb4',
    67: 'G4',
    68: 'Ab4',
    69: 'A4',
    70: 'Bb4',
    71: 'B4',
    72: 'C5',
    73: 'Db5',
    74: 'D5',
    75: 'Eb5',
    76: 'E5',
    77: 'F5',
    78: 'Gb5',
    79: 'G5',
    80: 'Ab5',
    81: 'A5',
    82: 'Bb5',
    83: 'B5',
    84: 'C6',
    85: 'Db6',
    86: 'D6',
    87: 'Eb6',
    88: 'E6',
    89: 'F6',
    90: 'Gb6',
    91: 'G6',
    92: 'Ab6',
    93: 'A6',
    94: 'Bb6',
    95: 'B6',
    96: 'C7',
    97: 'Db7',
    98: 'D7',
    99: 'Eb7',
    100: 'E7',
    101: 'F7',
    102: 'Gb7',
    103: 'G7',
    104: 'Ab7',
    105: 'A7',
    106: 'Bb7',
    107: 'B7',
    108: 'C8',
    109: 'Db8',
    110: 'D8',
    111: 'Eb8',
    112: 'E8',
    113: 'F8',
    114: 'Gb8',
    115: 'G8',
    116: 'Ab8',
    117: 'A8',
    118: 'Bb8',
    119: 'B8',
    120: 'C9',
    121: 'Db9',
}


def cents_to_factor(cents):
    """Two to the power of cents divided by 1200."""
    return math.pow(2, cents / 1200)


_accidentals = {"__": -2, "_": -1, "_/": -0.5, "=": 0, "": 0, "^/": 0.5, "^": 1, "^^": 2}
_notes_in_order = ['C', '-', 'D', '-', 'E', 'F', '-', 'G', '-', 'A', '-', 'B', 'c', '-', 'd', '-', 'e', 'f', '-', 'g', '-', 'a', '-', 'b']
_note_re = re.compile(r"([_^/]*)([ABCDEFGabcdefg])(,*)('*)")


def note_to_midi(note):
    """Convert an abc note name like ``^c'`` to a MIDI pitch number."""
    reg = _note_re.search(note)
    if reg:
        acc = _accidentals.get(reg.group(1))
        if acc is None:
            return float('nan')
        pitch = _notes_in_order.index(reg.group(2))
        octave = len(reg.group(4)) - len(reg.group(3))
        return 48 + pitch + acc + octave * 12
    return 0


def midi_to_note(midi):
    """Convert a MIDI pitch number to an abc note name."""
    midi = parse_int(midi, 10)
    octave = js_floor(midi / 12)
    pitch = midi % 12
    name = _notes_in_order[pitch]
    if name == '-':
        name = '^' + _notes_in_order[pitch - 1]

    if octave > 4:
        name = name.lower()
        octave -= 5
        while octave > 0:
            name += "'"
            octave -= 1
    else:
        while octave < 4:
            name += ','
            octave += 1
    return name


_perc_letters = ["C", "D", "E", "F", "G", "A", "B", "c", "d", "e", "f", "g", "a", "b", "c'", "d'", "e'"]
_pitch_map = {}
for _i, _n in enumerate(_perc_letters):
    _pitch_map["f%d" % _i] = "_" + _n
    _pitch_map["n%d" % _i] = "=" + _n
    _pitch_map["s%d" % _i] = "^" + _n
    _pitch_map["x%d" % _i] = _n


def pitches_to_perc(pitch_obj):
    """Return the abc note name (with accidental) used as a key in ``%%percmap``."""
    from ..jsutil import js_str
    pitch = (pitch_obj.accidental[0] if pitch_obj.accidental else 'x') + js_str(pitch_obj.verticalPos)
    return _pitch_map.get(pitch)
