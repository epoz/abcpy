"""Create a standard MIDI file from a tune.

Port of ``abc_midi_renderer.js``, ``midi/abc_midi_create.js`` and
``get-midi-file.js``.  The MIDI data is built the same way as abcjs does it
(as a ``data:audio/midi,`` URI with percent-encoded bytes) so that the output
is byte-for-byte identical; :func:`get_midi_file` can return it as ``bytes``.
"""

import math
import re

from ..jsutil import Obj, js_round, js_str, js_sort, to_int32, number, obj_copy
from .midi_tables import cents_to_factor

HALF_STEP = 4096  # For the pitch wheel - (i.e. the distance from C to C#)
BASE_DURATION = 480 * 4  # nice and divisible, equals 1 whole note


def _js_hex(n):
    """``Number.prototype.toString(16)`` for the values used here."""
    if isinstance(n, float):
        if n != n:
            return "NaN"
        if math.isinf(n):
            return "Infinity" if n > 0 else "-Infinity"
        if n == int(n):
            n = int(n)
        else:
            sign = "-" if n < 0 else ""
            ip = int(abs(n))
            frac = abs(n) - ip
            digits = ""
            for _ in range(20):
                frac *= 16
                d = int(frac)
                digits += "0123456789abcdef"[d]
                frac -= d
                if frac == 0:
                    break
            return sign + format(ip, "x") + "." + digits
    if n < 0:
        return "-" + format(-n, "x")
    return format(n, "x")


def _encode_hex(s):
    # s is assumed to be of even length
    ret = ""
    for i in range(0, len(s), 2):
        ret += "%" + s[i:i + 2]
    return ret


def _to_hex(n, padding):
    s = _js_hex(n)
    s = s.split(".")[0]
    while len(s) < padding:
        s = "0" + s
    if len(s) > padding:
        s = s[0:padding]
    return _encode_hex(s)


def _to_7bit_hex(n):
    # this takes a number and shifts all digits from the 7th one to the left.
    n = js_round(n)
    lower = int(math.fmod(n, 128))
    higher = n - lower
    return _to_hex(higher * 2 + lower, 4)


def _to_duration_hex(n):
    res = 0
    a = []

    # cut up into 7 bit chunks;
    n = to_int32(js_round(n))
    while n != 0:
        a.append(n & 0x7F)
        n = n >> 7

    # join the 7 bit chunks together, all but last chunk get leading 1
    for i in range(len(a) - 1, -1, -1):
        res = to_int32(res << 8)
        bits = a[i]
        if i != 0:
            bits = bits | 0x80
        res = to_int32(res | bits)

    padding = len(_js_hex(res))
    padding += padding % 2
    return _to_hex(res, padding)


def _utf16_units(s):
    data = s.encode("utf-16-le")
    return [data[i] | (data[i + 1] << 8) for i in range(0, len(data), 2)]


def _encode_string(s, cmd_type):
    # If there are multi-byte chars, we don't know how long the string will be until we create it.
    name_array = ""
    for code in _utf16_units(s):
        name_array += _to_hex(code, 2)
    return "%00%FF" + cmd_type + _to_hex(len(name_array) // 3, 2) + name_array  # Each byte is represented by three chars "%XX", so divide by 3 to get the length.


def _key_signature(key):
    # 00 FF 5902 03 00 - key signature
    if not key or key.accidentals is None:
        return ""
    h = "%00%FF%59%02"
    sharp_count = 0
    flat_count = 256
    for a in key.accidentals:
        if a.acc == "sharp":
            sharp_count += 1
        elif a.acc == "flat":
            flat_count -= 1
    sig = _to_hex(flat_count, 2) if flat_count != 256 else _to_hex(sharp_count, 2)
    mode = "%01" if key.mode == "m" else "%00"
    return h + sig + mode


def _time_signature(time):
    # 00 FF 58 04 04 02 30 08 - time signature
    h = "%00%FF%58%04" + _to_hex(time.num, 2)
    dens = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4, 32: 5}
    den = dens.get(time.den)
    if not den:
        return ""  # the denominator is not supported, so just don't include this.
    h += _to_hex(den, 2)

    clocks = {"2/4": 24, "3/4": 24, "4/4": 24, "5/4": 24, "6/4": 72, "2/2": 48, "3/2": 48, "4/2": 48,
              "3/8": 36, "6/8": 36, "9/8": 36, "12/8": 36}.get(js_str(time.num) + "/" + js_str(time.den))
    if not clocks:
        return ""  # time sig is not supported.
    h += _to_hex(clocks, 2)
    return h + "%08"


class Midi:
    """Accumulates the MIDI tracks as a percent-encoded string."""

    def __init__(self):
        self.trackstrings = ""
        self.trackcount = 0
        self.noteOnAndChannel = "%90"
        self.noteOffAndChannel = "%80"
        self.instrument = None
        self.channel = None
        self.track = ""
        self.trackName = ""
        self.trackInstrument = ""
        self.silencelength = 0
        self.noteWarped = {}

    def set_tempo(self, qpm):
        if self.trackcount == 0:
            self.start_track()
            self.track += "%00%FF%51%03" + _to_hex(js_round(60000000 / qpm), 6)
            self.end_track()

    def set_global_info(self, qpm, name, key, time):
        if self.trackcount == 0:
            self.start_track()
            divisions = js_round(60000000 / qpm) if qpm else float('nan')
            # Add the tempo
            self.track += "%00%FF%51%03" + _to_hex(divisions, 6)

            if key:
                self.track += _key_signature(key)
            if time:
                self.track += _time_signature(time)
            if name:
                self.track += _encode_string(name, "%01")
            self.end_track()

    def start_track(self):
        self.noteWarped = {}
        self.track = ""
        self.trackName = ""
        self.trackInstrument = ""
        self.silencelength = 0
        self.trackcount += 1
        if self.instrument:
            self.set_instrument(self.instrument)

    def end_track(self):
        self.track = self.trackName + self.trackInstrument + self.track
        tracklength = _to_hex(len(self.track) / 3 + 4, 8)
        self.track = "MTrk" + tracklength + self.track + '%00%FF%2F%00'  # track header ... track end
        self.trackstrings += self.track

    def set_text(self, typ, text):
        if typ == 'name':
            self.trackName = _encode_string(text, "%03")

    def set_instrument(self, num):
        self.trackInstrument = "%00%C0" + _to_hex(num, 2)
        self.instrument = num

    def set_channel(self, num, pan=None):
        self.channel = num
        cc_prefix = "%00%B" + _js_hex(self.channel)
        # Reset midi, in case it was set previously.
        self.track += cc_prefix + "%79%00"  # Reset All Controllers
        self.track += cc_prefix + "%40%00"  # Damper pedal
        self.track += cc_prefix + "%5B%30"  # Effect 1 Depth (reverb)
        # Translate pan as -1 to 1 to 0 to 127
        if not pan:
            pan = 0
        pan = js_round((pan + 1) * 64)
        self.track += cc_prefix + "%0A" + _to_hex(pan, 2)  # Pan
        self.track += cc_prefix + "%07%64"  # Channel Volume

        self.noteOnAndChannel = "%9" + _js_hex(self.channel)
        self.noteOffAndChannel = "%8" + _js_hex(self.channel)

    def start_note(self, pitch, loudness, cents=None):
        self.track += _to_duration_hex(self.silencelength)  # only need to shift by amount of silence (if there is any)
        self.silencelength = 0
        if cents:
            # the pitch is altered so send a midi pitch wheel event
            self.track += "%e" + _js_hex(self.channel)
            bend = js_round(cents_to_factor(cents) * HALF_STEP)
            self.track += _to_7bit_hex(0x2000 + bend)
            self.track += _to_duration_hex(0)  # this all happens at once so there is a zero length here
            self.noteWarped[pitch] = True
        self.track += self.noteOnAndChannel
        self.track += "%" + _js_hex(pitch) + _to_hex(loudness, 2)  # note

    def end_note(self, pitch):
        self.track += _to_duration_hex(self.silencelength)  # only need to shift by amount of silence (if there is any)
        self.silencelength = 0
        if self.noteWarped.get(pitch):
            # the pitch was altered so alter it back.
            self.track += "%e" + _js_hex(self.channel)
            self.track += _to_7bit_hex(0x2000)
            self.track += _to_duration_hex(0)
            self.noteWarped[pitch] = False
        self.track += self.noteOffAndChannel
        self.track += "%" + _js_hex(pitch) + "%00"  # end note

    def add_rest(self, length):
        self.silencelength += length
        if self.silencelength < 0:
            self.silencelength = 0

    def get_data(self):
        return ("data:audio/midi," +
                "MThd%00%00%00%06%00%01" + _to_hex(self.trackcount, 4) + "%01%e0" +  # header
                self.trackstrings)


def _add_notes(midi, note_placement, base_duration):
    times = js_sort([float(t) for t in note_placement.keys()], lambda a, b: a - b)
    last_time = 0
    for t in times:
        events = note_placement[t]
        if t > last_time:
            distance = (t - last_time) * base_duration
            midi.add_rest(distance)
            last_time = t
        for event in events:
            if event.volume:
                midi.start_note(event.pitch, event.volume, event.cents)
            else:
                midi.end_note(event.pitch)


def midi_create(abc_tune, options=None):
    """Return the MIDI file for a parsed tune as a ``data:audio/midi,...`` string."""
    options = obj_copy(options) if options is not None else Obj()
    commands = abc_tune.set_up_audio(options)
    midi = Midi()
    title = abc_tune.metaText.get('title') if abc_tune.metaText else None
    if isinstance(title, list):
        title = None if not title else "".join(t.text if isinstance(t, dict) else str(t) for t in title)
    if title and len(title) > 128:
        title = title[0:124] + '...'
    key = abc_tune.get_key_signature()
    time = abc_tune.get_meter_fraction()

    # Fix for */8 meter tempos
    tempo = commands.tempo if commands.tempo is not None else float('nan')

    beats_per_second = tempo / 60

    # Fix tempo for compound meters
    if time.den == 8 and time.num != 5 and time.num != 7:
        # Compute the tempo based on the actual milliseconds per measure, scaled by the number of eight notes and halved to get tempo in bpm.
        ms_per_measure = abc_tune.milliseconds_per_measure()
        tempo = (60000 / (ms_per_measure / time.num)) / 2
        beats_per_second = tempo / 60

    midi.set_global_info(tempo, title, key, time)

    for i in range(len(commands.tracks)):
        midi.start_track()
        note_placement = {}
        for event in commands.tracks[i]:
            cmd = event.cmd
            if cmd == 'text':
                midi.set_text(event.type, event.text)
            elif cmd == 'program':
                pan = 0
                if options.pan and len(options.pan) > i:
                    pan = options.pan[i]
                if event.instrument == 128:
                    # If we're using the percussion voice, change to Channel 10
                    midi.set_channel(9, pan)
                    midi.set_instrument(0)
                else:
                    midi.set_channel(event.channel, pan)
                    midi.set_instrument(event.instrument)
            elif cmd == 'note':
                gap_length_in_beats = event.gap * beats_per_second
                start = event.start
                # The staccato and legato are indicated by event.gap.
                # event.gap is in seconds but the durations are in whole notes.
                end = start + event.duration - gap_length_in_beats
                note_placement.setdefault(float(start), []).append(Obj(pitch=event.pitch, volume=event.volume, cents=event.cents))
                note_placement.setdefault(float(end), []).append(Obj(pitch=event.pitch, volume=0))
        _add_notes(midi, note_placement, BASE_DURATION)
        midi.end_track()

    return midi.get_data()


def _data_to_bytes(download_midi):
    decoded = download_midi.replace("data:audio/midi,", "", 1)
    decoded = decoded.replace("MThd", "%4d%54%68%64")
    decoded = decoded.replace("MTrk", "%4d%54%72%6b")
    out = bytearray()
    for i in range(len(decoded) // 3):
        p = i * 3 + 1
        try:
            out.append(int(decoded[p:p + 2], 16) & 0xFF)
        except ValueError:
            out.append(0)
    return bytes(out)


def _generate_midi_download_link(tune, midi_params, midi, index):
    div_classes = ['abcjs-download-midi', 'abcjs-midi-' + js_str(index)]
    if midi_params.downloadClass:
        div_classes.append(midi_params.downloadClass)
    html = '<div class="' + ' '.join(div_classes) + '">'
    if midi_params.preTextDownload:
        html += midi_params.preTextDownload
    title = tune.metaText.get('title') if tune.metaText and tune.metaText.get('title') else 'Untitled'
    if callable(midi_params.downloadLabel):
        label = midi_params.downloadLabel(tune, index)
    elif midi_params.downloadLabel:
        label = midi_params.downloadLabel.replace("%T", title, 1)
    else:
        label = "Download MIDI for \"" + title + "\""
    title = re.sub(r"\W", "_", title.lower().replace("'", "")).replace("__", "_")
    filename = midi_params.fileName if midi_params.fileName else title + '.midi'
    html += '<a download="' + filename + '" href="' + midi + '">' + label + '</a>'
    if midi_params.postTextDownload:
        html += midi_params.postTextDownload
    return html + "</div>"


def get_midi_file(source, options=None):
    """Create MIDI for ``source`` (an abc string or a parsed :class:`~abcpy.data.tune.Tune`).

    ``options['midiOutputType']`` selects the result: ``"binary"`` (the default
    in abcpy) returns ``bytes``; ``"encoded"`` returns the ``data:audio/midi``
    URI; ``"link"`` returns an HTML download link like abcjs does.  When
    ``source`` is a string, a list with one result per tune is returned.
    """
    params = obj_copy(options) if options else Obj()
    params.generateInline = False
    output_type = params.midiOutputType or "binary"

    def callback(div, tune, index, abc=None):
        download_midi = midi_create(tune, params)
        if output_type == "encoded":
            return download_midi
        if output_type == "binary":
            return _data_to_bytes(download_midi)
        return _generate_midi_download_link(tune, params, download_midi, index)

    if isinstance(source, str):
        from ..api.tunebook import render_engine, number_of_tunes
        return render_engine(callback, ["*"] * number_of_tunes(source), source, params)
    return callback(None, source, 0)


def write_midi_file(source, path, options=None, tune_index=0):
    """Write the MIDI for one tune of ``source`` to ``path``."""
    opts = dict(options or {})
    opts['midiOutputType'] = 'binary'
    data = get_midi_file(source, opts)
    if isinstance(data, list):
        data = data[tune_index]
    with open(path, "wb") as f:
        f.write(data)
    return path
