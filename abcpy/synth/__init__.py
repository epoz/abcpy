"""Turning a parsed tune into MIDI events and standard MIDI files.

The web audio playback of abcjs is not ported; everything that produces
note events or MIDI data is.
"""

from .sequencer import sequence
from .flattener import flatten
from .midi import get_midi_file, write_midi_file, midi_create
from .midi_tables import (instrument_index_to_name, pitch_to_note_name, note_to_midi, midi_to_note,
                          cents_to_factor, pitches_to_perc)
