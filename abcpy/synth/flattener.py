"""Turn a linear series of events into a series of MIDI commands (port of ``abc_midi_flattener.js``).

The input is the output of :func:`abcpy.synth.sequencer.sequence`.  This pass
changes the logical definitions of the grace notes, decorations, ties,
triplets, rests, transpositions, keys, and accidentals into actual note
durations.  It also extracts guitar chords to a separate voice and resolves
their rhythm.

The result is ``{'tempo', 'instrument', 'tracks', 'totalDuration'}`` where each
track is a list of ``{'cmd': 'program'|'note'|'text', ...}`` events.
"""

import math

from ..jsutil import Obj, at, js_round, js_str, parse_int, number, is_nan, js_sort, js_keys, truthy, obj_copy, js_floor
from .chord_track import ChordTrack
from .midi_tables import pitches_to_perc

DRUM_INSTRUMENT = 128

# The gaps per beat. The first two are in seconds, the third is in fraction of a duration.
NORMAL_BREAK_BETWEEN_NOTES = 0  # for articulation (matches muse score value)
SLURRED_BREAK_BETWEEN_NOTES = -0.001  # make the slurred notes actually overlap
STACCATO_BREAK_BETWEEN_NOTES = 0.4  # some people say staccato is half duration, some say 3/4 so this splits it

_scale = [0, 2, 4, 5, 7, 9, 11]


def _time_to_real_time(time):
    return time / 1000000


def _extract_octave(pitch):
    return js_floor(pitch / 7)


def _extract_note(pitch):
    pitch = math.fmod(pitch, 7)
    if pitch < 0:
        pitch += 7
    return int(pitch) if pitch == int(pitch) else pitch


def _get_beat_fraction(meter):
    d = parse_int(meter.den, 10)
    if d == 2:
        return 0.5
    if d == 4:
        return 0.25
    if d == 8:
        if math.fmod(number(meter.num), 3) == 0:
            return 0.375
        return 0.125
    if d == 16:
        return 0.125
    return 0.25


def _calc_beat(measure_start, beat_length, curr_time):
    distance_from_start = curr_time - measure_start
    return distance_from_start / beat_length


def _adjust_for_micro_tone(description):
    # if the pitch is not a whole number then make it a whole number and add a tuning factor
    pitch = js_str(description.pitch)
    if ".75" in pitch:
        description.pitch = js_round(description.pitch)
        description.cents = -50
    elif ".25" in pitch:
        description.pitch = js_round(description.pitch)
        description.cents = 50
    return description


class _Flattener:
    def __init__(self, voices, options, percmap, midi_options):
        self.barAccidentals = {}
        self.accidentals = [0, 0, 0, 0, 0, 0, 0]
        self.transpose = 0
        self.bagpipes = False
        self.tracks = []
        self.startingTempo = options.qpm
        self.startingMeter = None
        self.tempoChangeFactor = 1
        self.instrument = None
        self.currentInstrument = None
        self.currentTrack = None
        self.lastNoteDurationPosition = -1
        self.currentTrackName = None
        self.lastEventTime = 0
        self.percmap = percmap
        self.meter = Obj(num=4, den=4)
        self.lastBarTime = 0
        self.doBeatAccents = True
        self.stressBeat1 = 105
        self.stressBeatDown = 95
        self.stressBeatUp = 85
        self.volumesPerNotePitch = []
        self.beatFraction = 0.25
        self.nextVolume = None
        self.nextVolumeDelta = None
        self.slurCount = 0
        # For the drum/metronome track.
        self.drumTrack = []
        self.drumTrackFinished = False
        self.drumDefinition = Obj()
        self.drumBars = 1
        self.pickupLength = 0
        if len(voices) > 0 and len(voices[0]) > 0:
            self.pickupLength = voices[0][0].pickupLength

        # For resolving chords.
        if options.bassprog is not None and not midi_options.get('bassprog'):
            midi_options['bassprog'] = [options.bassprog]
        if options.bassvol is not None and not midi_options.get('bassvol'):
            midi_options['bassvol'] = [options.bassvol]
        if options.chordprog is not None and not midi_options.get('chordprog'):
            midi_options['chordprog'] = [options.chordprog]
        if options.chordvol is not None and not midi_options.get('chordvol'):
            midi_options['chordvol'] = [options.chordvol]
        if options.gchord is not None and not midi_options.get('gchord'):
            midi_options['gchord'] = [options.gchord]
        self.chordTrack = ChordTrack(len(voices), options.chordsOff, midi_options, self.meter)

    def duration_rounded(self, duration):
        return js_round(duration * self.tempoChangeFactor * 1000000) / 1000000

    def run(self, voices, options):
        chord_track = self.chordTrack
        # First adjust the input to resolve ties, set the starting time for each note, etc. That will make the rest of the logic easier
        _pre_process(voices, options)

        for i in range(len(voices)):
            self.transpose = 0
            chord_track.set_transpose(self.transpose)
            self.lastNoteDurationPosition = -1
            voice = voices[i]
            self.currentTrack = [Obj(cmd='program', channel=i, instrument=self.instrument)]
            self.currentTrackName = None
            self.lastBarTime = 0
            chord_track.set_last_bar_time(0)
            voice_off = False
            if options.voicesOff is True:
                voice_off = True
            elif options.voicesOff and len(options.voicesOff) and i in options.voicesOff:
                voice_off = True
            for element in voice:
                t = element.el_type
                if t == "name":
                    self.currentTrackName = Obj(cmd='text', type="name", text=element.trackName)
                elif t == "note":
                    self.write_note(element, voice_off)
                elif t == "key":
                    self.accidentals = _set_key_signature(element)
                elif t == "meter":
                    if not self.startingMeter:
                        self.startingMeter = element
                    self.meter = element
                    chord_track.set_meter(self.meter)
                    self.beatFraction = _get_beat_fraction(self.meter)
                    self.align_drum_to_meter()
                elif t == "tempo":
                    if not self.startingTempo:
                        self.startingTempo = element.qpm
                    else:
                        self.tempoChangeFactor = self.startingTempo / element.qpm if element.qpm else 1
                    chord_track.set_tempo_change_factor(self.tempoChangeFactor)
                elif t == "transpose":
                    self.transpose = element.transpose
                    chord_track.set_transpose(self.transpose)
                elif t == "bar":
                    chord_track.bar_end(element)

                    self.barAccidentals = {}
                    if i == 0:  # Only write the drum part on the first voice so that it is not duplicated.
                        self.write_drum(len(voices) + 1)
                    chord_track.set_rhythm_head(False)  # decide whether there are rhythm heads each measure.
                    self.lastBarTime = _time_to_real_time(element.time)
                    chord_track.set_last_bar_time(self.lastBarTime)
                elif t == "bagpipes":
                    self.bagpipes = True
                elif t == "instrument":
                    if self.instrument is None:
                        self.instrument = element.program
                    self.currentInstrument = element.program
                    if len(self.currentTrack) > 0 and self.currentTrack[-1].cmd == 'program':
                        self.currentTrack[-1].instrument = element.program
                    else:
                        ii = len(self.currentTrack) - 1
                        while ii >= 0 and self.currentTrack[ii].cmd != 'program':
                            ii -= 1
                        if ii < 0 or self.currentTrack[ii].instrument != element.program:
                            self.currentTrack.append(Obj(cmd='program', channel=0, instrument=element.program))
                elif t == "channel":
                    self.set_channel(element.channel)
                elif t == "drum":
                    self.drumDefinition = self.normalize_drum_definition(element.params)
                    self.align_drum_to_meter()
                elif t == "gchordOn":
                    chord_track.g_chord_on(element)
                elif t == "beat":
                    self.stressBeat1 = element.beats[0]
                    self.stressBeatDown = element.beats[1]
                    self.stressBeatUp = element.beats[2]
                    if not element.volumesPerNotePitch:
                        self.volumesPerNotePitch = []
                    else:
                        self.volumesPerNotePitch = element.volumesPerNotePitch
                    # TODO-PER: also use the last parameter - which changes which beats are strong.
                elif t == "vol":
                    self.nextVolume = element.volume
                elif t == "volinc":
                    self.nextVolumeDelta = element.volume
                elif t == "beataccents":
                    self.doBeatAccents = element.value
                elif t in ("gchord", "bassprog", "chordprog", "bassvol", "chordvol", "gchordbars"):
                    chord_track.param_change(element)
                # else: unknown el_type (this should never happen)
            if self.currentTrack[0].instrument is None:
                self.currentTrack[0].instrument = self.instrument if self.instrument else 0
            if self.currentTrackName:
                self.currentTrack.insert(0, self.currentTrackName)
            self.tracks.append(self.currentTrack)
            chord_track.finish()
            if len(self.drumTrack) > 0:  # Don't do drums on more than one track, so turn off drum after we create it.
                self.drumTrackFinished = True
        # See if any notes are octaves played at the same time. If so, raise the pitch of the higher one.
        if options.detuneOctave:
            _find_octaves(self.tracks, parse_int(options.detuneOctave, 10))

        chord_track.add_track(self.tracks)
        if len(self.drumTrack) > 0:
            self.tracks.append(self.drumTrack)

        return Obj(tempo=self.startingTempo, instrument=self.instrument, tracks=self.tracks, totalDuration=self.lastEventTime)

    def set_channel(self, channel):
        for i in range(len(self.currentTrack) - 1, -1, -1):
            if self.currentTrack[i].cmd == "program":
                self.currentTrack[i].channel = channel
                return

    def process_volume(self, beat, voice_off, pitch_index_of_note=None):
        if voice_off:
            return 0
        pitch_stress_beat1 = self.stressBeat1
        pitch_stress_beat_down = self.stressBeatDown
        pitch_stress_beat_up = self.stressBeatUp
        if pitch_index_of_note is not None and len(self.volumesPerNotePitch) >= pitch_index_of_note + 1:
            pitch_stress_beat1 = self.volumesPerNotePitch[pitch_index_of_note][0]
            pitch_stress_beat_down = self.volumesPerNotePitch[pitch_index_of_note][1]
            pitch_stress_beat_up = self.volumesPerNotePitch[pitch_index_of_note][2]
        if self.nextVolume is not None:
            volume = self.nextVolume
            self.nextVolume = None
        elif not self.doBeatAccents:
            volume = pitch_stress_beat_down
        elif self.pickupLength is not None and self.pickupLength > beat:
            volume = pitch_stress_beat_up
        else:
            bar_beat = _calc_beat(self.lastBarTime, _get_beat_fraction(self.meter), beat)
            if bar_beat == 0:
                volume = pitch_stress_beat1
            elif parse_int(js_str(bar_beat), 10) == bar_beat:
                volume = pitch_stress_beat_down
            else:
                volume = pitch_stress_beat_up
        if self.nextVolumeDelta:
            volume += self.nextVolumeDelta
            self.nextVolumeDelta = None
        if volume < 0:
            volume = 0
        if volume > 127:
            volume = 127
        return 0 if voice_off else volume

    def do_modified_notes(self, note_modification, p):
        start = p.start
        running_duration = p.duration
        shortest_note = self.duration_rounded(1.0 / 32)
        ct = self.currentTrack
        ci = self.currentInstrument

        def push(pitch, st, dur, decoration=True):
            ev = Obj(cmd='note', pitch=pitch, volume=p.volume, start=st, duration=dur, gap=0, instrument=ci)
            if decoration:
                ev.style = 'decoration'
            ct.append(ev)

        if note_modification == "trill":
            note = 2
            while running_duration > 0:
                push(p.pitch + note, start, shortest_note)
                note = 0 if note == 2 else 2
                running_duration -= shortest_note
                start += shortest_note
        elif note_modification == "trillh":
            note = 1
            while running_duration > 0:
                push(p.pitch + note, start, shortest_note)
                note = 0 if note == 1 else 1
                running_duration -= shortest_note
                start += shortest_note
        elif note_modification == "pralltriller":
            push(p.pitch, start, shortest_note)
            running_duration -= shortest_note
            start += shortest_note
            push(p.pitch + 2, start, shortest_note)
            running_duration -= shortest_note
            start += shortest_note
            push(p.pitch, start, running_duration, False)
        elif note_modification in ("mordent", "lowermordent"):
            push(p.pitch, start, shortest_note)
            running_duration -= shortest_note
            start += shortest_note
            push(p.pitch - 2, start, shortest_note)
            running_duration -= shortest_note
            start += shortest_note
            push(p.pitch, start, running_duration, False)
        elif note_modification == "turn":
            shortest_note = p.duration / 4
            push(p.pitch + 2, start, shortest_note)
            push(p.pitch, start + shortest_note, shortest_note)
            push(p.pitch - 1, start + shortest_note * 2, shortest_note)
            push(p.pitch, start + shortest_note * 3, shortest_note)
        elif note_modification == "roll":
            while running_duration > 0:
                push(p.pitch, start, shortest_note)
                running_duration -= shortest_note * 2
                start += shortest_note * 2

    def write_note(self, elem, voice_off):
        # Create a series of note events to append to the current track.
        velocity = self.process_volume(_time_to_real_time(elem.time), voice_off)
        self.chordTrack.process_chord(elem)

        # if there are grace notes, then also play them.
        # I'm not sure there is an exact rule for the length of the notes. My rule, unless I find
        # a better one is: the grace notes cannot take more than 1/2 of the main note's value.
        if elem.gracenotes and elem.pitches and len(elem.pitches) > 0 and elem.pitches[0]:
            graces = self.process_grace_notes(elem.gracenotes, elem.pitches[0].duration)
            if elem.elem:
                elem.elem.midiGraceNotePitches = self.write_grace_notes(graces, _time_to_real_time(elem.time), velocity * 2 / 3, self.currentInstrument)  # make the graces a little quieter.

        # The beat fraction is the note that gets a beat (.25 is a quarter note)
        # The tempo is in minutes and we want to get to milliseconds.
        # If the element is inside a repeat, there may be more than one value.
        if elem.elem:
            rt = _time_to_real_time(elem.time)
            ms = rt / self.beatFraction / self.startingTempo * 60 * 1000 if self.startingTempo else float('nan')
            ee = elem.elem
            if ee.currentTrackMilliseconds is None:
                ee.currentTrackMilliseconds = ms
                ee.currentTrackWholeNotes = rt
            else:
                if not isinstance(ee.currentTrackMilliseconds, list):
                    if ee.currentTrackMilliseconds != ms:
                        ee.currentTrackMilliseconds = [ee.currentTrackMilliseconds, ms]
                        ee.currentTrackWholeNotes = [ee.currentTrackWholeNotes, rt]
                else:
                    # There can be duplicates if there are multiple voices
                    if ms not in ee.currentTrackMilliseconds:
                        ee.currentTrackMilliseconds.append(ms)
                        ee.currentTrackWholeNotes.append(rt)
        if elem.pitches:
            this_break_between_notes = ''
            ret = _find_note_modifications(elem, velocity)
            if ret.thisBreakBetweenNotes:
                this_break_between_notes = ret.thisBreakBetweenNotes
            if ret.velocity:
                velocity = ret.velocity

            # TODO-PER: Can also make a different sound on style=x and style=harmonic
            e_pitches = elem.pitches
            if elem.style == "rhythm":
                e_pitches = self.chordTrack.set_rhythm_head(True, elem)

            if elem.elem:
                elem.elem.midiPitches = []
            for i in range(len(e_pitches)):
                # here we can set the volume for each note in a chord, if specified
                pitch_velocity = velocity
                if not ret.velocity and isinstance(elem.decoration, list) and len(elem.decoration) > i:
                    pitch_velocity = self.process_volume(_time_to_real_time(elem.time), voice_off, i)
                note = e_pitches[i]
                if not note:
                    continue
                if note.startSlur:
                    self.slurCount += len(note.startSlur)
                if note.endSlur:
                    self.slurCount -= len(note.endSlur)
                actual_pitch = note.actualPitch if note.actualPitch else self.adjust_pitch(note)
                if self.currentInstrument == DRUM_INSTRUMENT and self.percmap:
                    name = pitches_to_perc(note)
                    if name and self.percmap.get(name):
                        actual_pitch = self.percmap[name].sound
                p = Obj(cmd='note', pitch=actual_pitch, volume=pitch_velocity, start=_time_to_real_time(elem.time),
                        duration=self.duration_rounded(note.duration), instrument=self.currentInstrument,
                        startChar=elem.elem.startChar if elem.elem else None, endChar=elem.elem.endChar if elem.elem else None)
                p = _adjust_for_micro_tone(p)
                if elem.gracenotes:
                    p.duration = p.duration / 2
                    p.start = p.start + p.duration
                if elem.elem:
                    elem.elem.midiPitches.append(p)
                if ret.noteModification:
                    self.do_modified_notes(ret.noteModification, p)
                else:
                    if self.slurCount > 0:
                        p.endType = 'tenuto'
                    elif this_break_between_notes:
                        p.endType = this_break_between_notes

                    if p.endType == "tenuto":
                        p.gap = SLURRED_BREAK_BETWEEN_NOTES
                    elif p.endType == "staccato":
                        d = p.duration * STACCATO_BREAK_BETWEEN_NOTES
                        p.gap = self.startingTempo / 60 * d
                    else:
                        p.gap = NORMAL_BREAK_BETWEEN_NOTES
                    self.currentTrack.append(p)
            self.lastNoteDurationPosition = len(self.currentTrack) - 1
        real_dur = _get_real_duration(elem)
        if real_dur is None:
            real_dur = float('nan')
        self.lastEventTime = _js_max(self.lastEventTime, _time_to_real_time(elem.time) + self.duration_rounded(real_dur))

    def adjust_pitch(self, note):
        if note.midipitch is not None:
            return note.midipitch  # The pitch might already be known, for instance if there is a drummap.
        pitch = note.pitch
        if note.accidental:
            acc_values = {"sharp": 1, "flat": -1, "natural": 0, "dblsharp": 2, "dblflat": -2, "quartersharp": 0.25, "quarterflat": -0.25}
            if note.accidental in acc_values:
                # change that pitch (not other octaves) for the rest of the bar
                self.barAccidentals[pitch] = acc_values[note.accidental]

        actual_pitch = _extract_octave(pitch) * 12 + _scale[_extract_note(pitch)] + 60

        if self.barAccidentals.get(pitch) is not None:
            # An accidental is always taken at face value and supersedes the key signature.
            actual_pitch += self.barAccidentals[pitch]
        else:  # use normal accidentals
            actual_pitch += self.accidentals[_extract_note(pitch)]
        actual_pitch += self.transpose
        return actual_pitch

    def process_grace_notes(self, graces, companion_duration):
        # Grace notes take up half of the note value. So if there are many of them they are all real short.
        grace_duration = 0
        ret = []
        for grace in graces:
            grace_duration += grace.duration
        multiplier = companion_duration / 2 / grace_duration if grace_duration else (float('nan') if is_nan(companion_duration) or companion_duration == 0 else float('inf'))

        for grace in graces:
            actual_pitch = self.adjust_pitch(grace)
            if self.currentInstrument == DRUM_INSTRUMENT and self.percmap:
                name = pitches_to_perc(grace)
                if name and self.percmap.get(name):
                    actual_pitch = self.percmap[name].sound
            pitch = Obj(pitch=actual_pitch, duration=grace.duration * multiplier)
            pitch = _adjust_for_micro_tone(pitch)
            ret.append(pitch)
        return ret

    def write_grace_notes(self, graces, start, velocity, current_instrument):
        midi_grace = []
        velocity = js_round(velocity)
        for gp in graces:
            self.currentTrack.append(Obj(cmd='note', pitch=gp.pitch, volume=velocity, start=start, duration=gp.duration, gap=0, instrument=current_instrument, style='grace'))
            midi_grace.append(Obj(pitch=gp.pitch, durationInMeasures=gp.duration, volume=velocity, instrument=current_instrument))
            start += gp.duration
        return midi_grace

    def normalize_drum_definition(self, params):
        # Be very strict with the drum definition. If anything is not perfect,
        # just turn the drums off.
        if len(params.pattern) == 0 or params.on is False:
            return Obj(on=False)

        s = params.pattern[0]
        events = []
        event = ""
        total_play = 0
        for ch in s:
            if ch == 'd':
                total_play += 1
            if ch == 'd' or ch == 'z':
                if len(event) != 0:
                    events.append(event)
                    event = ch
                else:
                    event = event + ch
            else:
                if len(event) == 0:
                    # there was an error: the string should have started with d or z
                    return Obj(on=False)
                event = event + ch

        if len(event) != 0:
            events.append(event)

        # Now the events array should have one item per event.
        # There should be two more params for each event: the volume and the pitch.
        if len(params.pattern) != total_play * 2 + 1:
            return Obj(on=False)

        ret = Obj(on=True, bars=params.bars, pattern=[])
        beat_length = _get_beat_fraction(self.meter)
        play_count = 0
        for event in events:
            length = 1
            div = False
            num = 0  # (abcjs builds this by string concatenation, so "23" becomes "023" -> 23 and so on)
            for ch in event[1:]:
                if ch == "/":
                    if num != 0:
                        length *= number(num)
                    num = 0
                    div = True
                elif ch in "123456789":
                    num = js_str(number(num) * 10) + ch if not isinstance(num, str) else js_str(number(num) * 10) + ch
                else:
                    return Obj(on=False)
            if div:
                if num == 0:
                    num = 2  # a slash by itself is interpreted as "/2"
                length /= number(num)
            elif num:
                length *= number(num)
            if event[0] == 'd':
                ret.pattern.append(Obj(len=length * beat_length, pitch=at(params.pattern, 1 + play_count), velocity=at(params.pattern, 1 + play_count + total_play)))
                play_count += 1
            else:
                ret.pattern.append(Obj(len=length * beat_length, pitch=None))
        self.drumBars = params.bars if params.bars else 1
        return ret

    def align_drum_to_meter(self):
        if not self.drumDefinition or not self.drumDefinition.pattern:
            return
        ret = self.drumDefinition
        # Now normalize the pattern to cover the correct number of measures. The note lengths passed are relative to each other and need to be scaled to fit a measure.
        total_time = 0
        measures_per_beat = number(self.meter.num) / number(self.meter.den)
        for p in ret.pattern:
            total_time += p.len
        factor = total_time / self.drumBars / measures_per_beat
        for p in ret.pattern:
            p.len = p.len / factor
        self.drumDefinition = ret

    def write_drum(self, channel):
        if len(self.drumTrack) == 0 and not self.drumDefinition.on:
            return

        measure_len = number(self.meter.num) / number(self.meter.den)
        if len(self.drumTrack) == 0:
            if self.lastEventTime < measure_len:
                return  # This is true if there are pickup notes. The drum doesn't start until the first full measure.
            self.drumTrack.append(Obj(cmd='program', channel=channel, instrument=DRUM_INSTRUMENT))

        if not self.drumDefinition.on:
            # this is the case where there has been a drum track, but it was specifically turned off.
            return
        start = self.lastBarTime
        for d in self.drumDefinition.pattern:
            length = self.duration_rounded(d.len)
            if d.pitch:
                self.drumTrack.append(Obj(cmd='note', pitch=d.pitch, volume=d.velocity, start=start, duration=length, gap=0, instrument=DRUM_INSTRUMENT))
            start += length


def _js_max(a, b):
    if is_nan(a) or is_nan(b):
        return float('nan')
    return max(a, b)


def _find_note_modifications(elem, velocity):
    ret = Obj()
    if elem.decoration:
        for d in elem.decoration:
            if d == 'staccato':
                ret.thisBreakBetweenNotes = 'staccato'
            elif d == 'tenuto':
                ret.thisBreakBetweenNotes = 'tenuto'
            elif d == 'accent':
                ret.velocity = min(127, velocity * 1.5)
            elif d == 'trill':
                ret.noteModification = "trill"
            elif d == 'lowermordent':
                ret.noteModification = "lowermordent"
            elif d == 'uppermordent':
                ret.noteModification = "pralltriller"
            elif d == 'mordent':
                ret.noteModification = "mordent"
            elif d == 'turn':
                ret.noteModification = "turn"
            elif d == 'roll':
                ret.noteModification = "roll"
            elif d == 'pralltriller':
                ret.noteModification = "pralltriller"
            elif d == 'trillh':
                ret.noteModification = "trillh"
    return ret


def _get_real_duration(elem):
    if elem.pitches and len(elem.pitches) > 0 and elem.pitches[0]:
        return elem.pitches[0].duration
    if elem.elem:
        return elem.elem.duration
    return elem.duration


def _set_key_signature(elem):
    accidentals = [0, 0, 0, 0, 0, 0, 0]
    if not elem.accidentals:
        return accidentals
    for acc in elem.accidentals:
        d = {"flat": -1, "quarterflat": -0.25, "sharp": 1, "quartersharp": 0.25}.get(acc.acc, 0)
        lowercase = acc.note.lower()
        note = _extract_note(ord(lowercase[0]) - ord('c'))
        accidentals[note] += d
    return accidentals


def _pre_process(voices, options):
    for voice in voices:
        ties = {}
        starting_tempo = options.qpm
        time_counter = 0
        tempo_multiplier = 1
        for j in range(len(voice)):
            element = voice[j]

            if element.el_type == 'tempo':
                if not starting_tempo:
                    starting_tempo = element.qpm
                else:
                    tempo_multiplier = starting_tempo / element.qpm if element.qpm else 1
                continue

            # For convenience, put the current time in each event so that it doesn't have to be calculated in the complicated stuff that follows.
            element.time = time_counter
            this_duration = element.duration if truthy(element.duration) else 0
            time_counter += js_round(this_duration * tempo_multiplier * 1000000)  # To compensate for JS rounding problems, do all intermediate calcs on integers.

            # If there are pitches then put the duration in the pitch object and if there are ties then change the duration of the first note in the tie.
            if element.pitches:
                for k in range(len(element.pitches)):
                    pitch = element.pitches[k]
                    if pitch:
                        pitch.duration = element.duration
                        if pitch.startTie:
                            if ties.get(pitch.pitch) is None:  # We might have three notes tied together - if so just add this duration.
                                ties[pitch.pitch] = Obj(el=j, pitch=k)
                            else:
                                tp = voice[ties[pitch.pitch].el].pitches[ties[pitch.pitch].pitch]
                                tp.duration += pitch.duration
                                element.pitches[k] = None
                        elif pitch.endTie:
                            tie = ties.get(pitch.pitch)
                            if tie:
                                dur = pitch.duration
                                tp = voice[tie.el].pitches[tie.pitch]
                                tp.pop('startTie', None)
                                tp.duration += dur
                                element.pitches[k] = None
                                del ties[pitch.pitch]
                            else:
                                pitch.pop('endTie', None)
                element.pop('duration', None)
        for key in js_keys(ties):
            item = ties[key]
            voice[item.el].pitches[item.pitch].pop('startTie', None)


def _find_octaves(tracks, detune_cents):
    timing = {}
    for i in range(len(tracks)):
        for j in range(len(tracks[i])):
            note = tracks[i][j]
            if note.cmd == "note":
                timing.setdefault(note.start, []).append(Obj(track=i, event=j, pitch=note.pitch))
    for key in timing:
        arr = timing[key]
        if len(arr) > 1:
            arr = js_sort(list(arr), lambda a, b: a.pitch - b.pitch)
            top_event = arr[-1]
            top_note = math.fmod(top_event.pitch, 12)
            found = False
            for j in range(len(arr) - 1):
                if math.fmod(arr[j].pitch, 12) == top_note:
                    found = True
                    break
            if found:
                event = tracks[top_event.track][top_event.event]
                if not event.cents:
                    event.cents = 0
                event.cents += detune_cents


def flatten(voices, options=None, percmap=None, midi_options=None):
    """Turn the sequenced voices into MIDI-like tracks."""
    options = options if isinstance(options, Obj) else (obj_copy(options) if options else Obj())
    if midi_options is None:
        midi_options = Obj()
    f = _Flattener(voices, options, percmap, midi_options)
    return f.run(voices, options)
