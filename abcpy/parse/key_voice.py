"""Parsing of K: (key/clef) and V: (voice) fields (port of ``abc_parse_key_voice.js``)."""

import re

from ..jsutil import Obj, at, assign, parse_float, js_keys, js_str
from . import transpose

clef_lines = {
    'treble': {'clef': 'treble', 'pitch': 4, 'mid': 0},
    'treble+8': {'clef': 'treble+8', 'pitch': 4, 'mid': 0},
    'treble-8': {'clef': 'treble-8', 'pitch': 4, 'mid': 0},
    'treble^8': {'clef': 'treble+8', 'pitch': 4, 'mid': 0},
    'treble_8': {'clef': 'treble-8', 'pitch': 4, 'mid': 0},
    'treble1': {'clef': 'treble', 'pitch': 2, 'mid': 2},
    'treble2': {'clef': 'treble', 'pitch': 4, 'mid': 0},
    'treble3': {'clef': 'treble', 'pitch': 6, 'mid': -2},
    'treble4': {'clef': 'treble', 'pitch': 8, 'mid': -4},
    'treble5': {'clef': 'treble', 'pitch': 10, 'mid': -6},
    'perc': {'clef': 'perc', 'pitch': 6, 'mid': 0},
    'none': {'clef': 'none', 'mid': 0},
    'bass': {'clef': 'bass', 'pitch': 8, 'mid': -12},
    'bass+8': {'clef': 'bass+8', 'pitch': 8, 'mid': -12},
    'bass-8': {'clef': 'bass-8', 'pitch': 8, 'mid': -12},
    'bass^8': {'clef': 'bass+8', 'pitch': 8, 'mid': -12},
    'bass_8': {'clef': 'bass-8', 'pitch': 8, 'mid': -12},
    'bass+16': {'clef': 'bass', 'pitch': 8, 'mid': -12},
    'bass-16': {'clef': 'bass', 'pitch': 8, 'mid': -12},
    'bass^16': {'clef': 'bass', 'pitch': 8, 'mid': -12},
    'bass_16': {'clef': 'bass', 'pitch': 8, 'mid': -12},
    'bass1': {'clef': 'bass', 'pitch': 2, 'mid': -6},
    'bass2': {'clef': 'bass', 'pitch': 4, 'mid': -8},
    'bass3': {'clef': 'bass', 'pitch': 6, 'mid': -10},
    'bass4': {'clef': 'bass', 'pitch': 8, 'mid': -12},
    'bass5': {'clef': 'bass', 'pitch': 10, 'mid': -14},
    'tenor': {'clef': 'alto', 'pitch': 8, 'mid': -8},
    'tenor1': {'clef': 'alto', 'pitch': 2, 'mid': -2},
    'tenor2': {'clef': 'alto', 'pitch': 4, 'mid': -4},
    'tenor3': {'clef': 'alto', 'pitch': 6, 'mid': -6},
    'tenor4': {'clef': 'alto', 'pitch': 8, 'mid': -8},
    'tenor5': {'clef': 'alto', 'pitch': 10, 'mid': -10},
    'alto': {'clef': 'alto', 'pitch': 6, 'mid': -6},
    'alto1': {'clef': 'alto', 'pitch': 2, 'mid': -2},
    'alto2': {'clef': 'alto', 'pitch': 4, 'mid': -4},
    'alto3': {'clef': 'alto', 'pitch': 6, 'mid': -6},
    'alto4': {'clef': 'alto', 'pitch': 8, 'mid': -8},
    'alto5': {'clef': 'alto', 'pitch': 10, 'mid': -10},
    'alto+8': {'clef': 'alto+8', 'pitch': 6, 'mid': -6},
    'alto-8': {'clef': 'alto-8', 'pitch': 6, 'mid': -6},
    'alto^8': {'clef': 'alto+8', 'pitch': 6, 'mid': -6},
    'alto_8': {'clef': 'alto-8', 'pitch': 6, 'mid': -6},
}

pitches = {'A': 5, 'B': 6, 'C': 0, 'D': 1, 'E': 2, 'F': 3, 'G': 4, 'a': 12, 'b': 13, 'c': 7, 'd': 8, 'e': 9, 'f': 10, 'g': 11}

_voice_clef_tokens = set([
    'treble', 'bass', 'tenor', 'alto', 'perc', 'none',
    "treble'", "bass'", "tenor'", "alto'", "none'",
    "treble''", "bass''", "tenor''", "alto''", "none''",
    'treble,', 'bass,', 'tenor,', 'alto,', 'none,',
    'treble,,', 'bass,,', 'tenor,,', 'alto,,', 'none,,',
    'treble+8', 'treble-8', 'treble^8', 'treble_8', 'treble1', 'treble2', 'treble3', 'treble4', 'treble5',
    'bass+8', 'bass-8', 'bass^8', 'bass_8', 'bass+16', 'bass-16', 'bass^16', 'bass_16',
    'bass1', 'bass2', 'bass3', 'bass4', 'bass5',
    'tenor1', 'tenor2', 'tenor3', 'tenor4', 'tenor5',
    'alto1', 'alto2', 'alto3', 'alto4', 'alto5',
    'alto+8', 'alto-8', 'alto^8', 'alto_8',
])


def calc_middle(clef, oct):
    value = clef_lines.get(clef)
    mid = value['mid'] if value else 0
    return mid + oct


def fix_clef(clef):
    value = clef_lines.get(clef.type)
    if value:
        clef.clefPos = value.get('pitch')
        if 'pitch' not in value:
            # JS assigns undefined, which disappears when serialized
            del clef.clefPos
        clef.type = value['clef']


def deep_copy_key(key):
    ret = Obj(accidentals=[], root=key.root, acc=key.acc, mode=key.mode)
    for k in key.accidentals:
        ret.accidentals.append(assign(k))
    if key.explicitAccidentals is not None:
        ret.explicitAccidentals = []
        for k in key.explicitAccidentals:
            ret.explicitAccidentals.append(assign(k))
    return ret


def add_pos_to_key(clef, key):
    # Shift the key signature from the treble positions to whatever position is needed for the clef.
    # This may put the key signature unnaturally high or low, so if it does, then shift it.
    mid = clef.verticalPos
    for acc in key.accidentals:
        pitch = pitches.get(acc.note)
        acc.verticalPos = pitch - mid if pitch is not None else float('nan')
    if key.impliedNaturals:
        for acc in key.impliedNaturals:
            pitch = pitches.get(acc.note)
            acc.verticalPos = pitch - mid if pitch is not None else float('nan')

    def low_adjust(acc):
        acc.verticalPos -= 7
        if acc.verticalPos >= 11 or (acc.verticalPos == 10 and acc.acc == 'flat'):
            acc.verticalPos -= 7
        if acc.note == 'A' and acc.acc == 'sharp':
            acc.verticalPos -= 7
        if (acc.note == 'G' or acc.note == 'F') and acc.acc == 'flat':
            acc.verticalPos -= 7

    def mid_adjust(acc):
        acc.verticalPos -= 7
        if mid == -8 and (acc.note == 'f' or acc.note == 'g') and acc.acc == 'sharp':
            acc.verticalPos -= 7

    if mid < -10:
        for acc in key.accidentals:
            low_adjust(acc)
        if key.impliedNaturals:
            for acc in key.impliedNaturals:
                low_adjust(acc)
    elif mid < -4:
        for acc in key.accidentals:
            mid_adjust(acc)
        if key.impliedNaturals:
            for acc in key.impliedNaturals:
                mid_adjust(acc)
    elif mid >= 7:
        for acc in key.accidentals:
            acc.verticalPos += 7
        if key.impliedNaturals:
            for acc in key.impliedNaturals:
                acc.verticalPos += 7


def fix_key(clef, key):
    fixed_key = assign(key)
    add_pos_to_key(clef, fixed_key)
    return fixed_key


def parse_middle(s):
    i = 0
    p = at(s, i)
    i += 1
    if p == '^' or p == '_':
        p = at(s, i)
        i += 1
    mid = pitches.get(p)
    if mid is None:
        mid = 6  # If a legal middle note wasn't received, just ignore it.
    while i < len(s):
        if s[i] == ',':
            mid -= 7
        elif s[i] == "'":
            mid += 7
        else:
            break
        i += 1
    return Obj(mid=mid - 6, str=s[i:])  # We get the note in the middle of the staff. We want the note that appears as the first ledger line below the staff.


def normalize_accidentals(accs):
    for a in accs:
        if a.note == 'b':
            a.note = 'B'
        elif a.note == 'a':
            a.note = 'A'
        elif a.note == 'F':
            a.note = 'f'
        elif a.note == 'E':
            a.note = 'e'
        elif a.note == 'D':
            a.note = 'd'
        elif a.note == 'C':
            a.note = 'c'
        elif a.note == 'G' and a.acc == 'sharp':
            a.note = 'g'
        elif a.note == 'g' and a.acc == 'flat':
            a.note = 'G'


class ParseKeyVoice:
    def __init__(self, directive):
        self.directive = directive
        self.tokenizer = None
        self.warn = None
        self.multiline_vars = None
        self.tune = None
        self.tune_builder = None

    def initialize(self, tokenizer, warn, multiline_vars, tune, tune_builder):
        self.tokenizer = tokenizer
        self.warn = warn
        self.multiline_vars = multiline_vars
        self.tune = tune
        self.tune_builder = tune_builder

    fix_clef = staticmethod(fix_clef)
    deep_copy_key = staticmethod(deep_copy_key)
    add_pos_to_key = staticmethod(add_pos_to_key)
    fix_key = staticmethod(fix_key)

    def standard_key(self, key_name, root, acc, local_transpose):
        return transpose.key_signature(self.multiline_vars, key_name, root, acc, local_transpose)

    def _set_voice_key(self):
        mv = self.multiline_vars
        if mv.currentVoice:
            mv.currentVoice.key = deep_copy_key(mv.key)

    def parse_key(self, s, is_inline):  # (and clef)
        # returns:
        #		{ foundClef: true, foundKey: true }
        # Side effects:
        #		calls warn() when there is a syntax error
        #		sets these members of multilineVars: clef, key, style
        mv = self.multiline_vars
        warn = self.warn
        tokenizer = self.tokenizer
        if len(s) == 0:
            # an empty K: field is the same as K:none
            s = 'none'
        tokens = tokenizer.tokenize(s, 0, len(s))
        ret = Obj()

        # Be sure that a key was passed in
        if len(tokens) == 0:
            warn("Must pass in key signature.", s, 0)
            return ret

        # first the key
        t0 = tokens[0].token
        if t0 == 'HP':
            self.directive.add_directive("bagpipes")
            mv.key = Obj(root="HP", accidentals=[], acc="", mode="")
            ret.foundKey = True
            tokens.pop(0)
            if not is_inline:
                mv.globalKey = deep_copy_key(mv.key)
            self._set_voice_key()
        elif t0 == 'Hp':
            self.directive.add_directive("bagpipes")
            mv.key = Obj(root="Hp", accidentals=[Obj(acc='natural', note='g'), Obj(acc='sharp', note='f'), Obj(acc='sharp', note='c')], acc="", mode="")
            ret.foundKey = True
            tokens.pop(0)
            if not is_inline:
                mv.globalKey = deep_copy_key(mv.key)
            self._set_voice_key()
        elif t0 == 'none':
            # we got the none key - that's the same as C to us
            mv.key = Obj(root="none", accidentals=[], acc="", mode="")
            ret.foundKey = True
            tokens.pop(0)
            if not is_inline:
                mv.globalKey = deep_copy_key(mv.key)
            self._set_voice_key()
        else:
            ret_pitch = tokenizer.get_key_pitch(tokens[0].token)
            if ret_pitch.len > 0:
                ret.foundKey = True
                acc = ""
                mode = ""
                # The accidental and mode might be attached to the pitch, so we might want to just remove the first character.
                if len(tokens[0].token) > 1:
                    tokens[0].token = tokens[0].token[1:]
                else:
                    tokens.pop(0)
                key = ret_pitch.token
                # We got a pitch to start with, so we might also have an accidental and a mode
                if len(tokens) > 0:
                    ret_acc = tokenizer.get_sharp_flat(tokens[0].token)
                    if ret_acc.len > 0:
                        if len(tokens[0].token) > 1:
                            tokens[0].token = tokens[0].token[1:]
                        else:
                            tokens.pop(0)
                        key += ret_acc.token
                        acc = ret_acc.token
                    if len(tokens) > 0:
                        ret_mode = tokenizer.get_mode(tokens[0].token)
                        if ret_mode.len > 0:
                            tokens.pop(0)
                            key += ret_mode.token
                            mode = ret_mode.token
                    # Be sure that the key specified is in the list: not all keys are physically possible, like Cbmin.
                    if self.standard_key(key, ret_pitch.token, acc, 0) is None:
                        warn("Unsupported key signature: " + key, s, 0)
                        return ret
                # We need to do a deep copy because we are going to modify it
                old_key = deep_copy_key(mv.key)
                # HACK! To get the local transpose to work, the transposition is done for each line. This caused the global transposition variable to be factored in twice, so subtract one of them here.
                key_compensate = -mv.globalTranspose if (not is_inline and mv.globalTranspose) else 0
                saved_orig_key = None
                if is_inline:
                    saved_orig_key = mv.globalTransposeOrigKeySig
                mv.key = deep_copy_key(self.standard_key(key, ret_pitch.token, acc, key_compensate))
                if is_inline:
                    mv.globalTransposeOrigKeySig = saved_orig_key
                mv.key.mode = mode
                if old_key and mv.keywarn is not False:
                    # Add natural in all places that the old key had an accidental.
                    for k in range(len(mv.key.accidentals)):
                        for kk in range(len(old_key.accidentals)):
                            if old_key.accidentals[kk].note and mv.key.accidentals[k].note.lower() == old_key.accidentals[kk].note.lower():
                                old_key.accidentals[kk].note = None
                    for kk in range(len(old_key.accidentals)):
                        if old_key.accidentals[kk].note:
                            if mv.key.impliedNaturals is None:
                                mv.key.impliedNaturals = []
                            mv.key.impliedNaturals.append(Obj(acc='natural', note=old_key.accidentals[kk].note))
                if not is_inline:
                    mv.globalKey = deep_copy_key(mv.key)
                self._set_voice_key()

        # There are two special cases of deprecated syntax. Ignore them if they occur
        if len(tokens) == 0:
            return ret
        if tokens[0].token == 'exp':
            tokens.pop(0)
        if len(tokens) == 0:
            return ret
        if tokens[0].token == 'oct':
            tokens.pop(0)

        # now see if there are extra accidentals
        if len(tokens) == 0:
            return ret
        accs = tokenizer.get_key_accidentals2(tokens)
        if accs.warn:
            warn(accs.warn, s, 0)
        # If we have extra accidentals, first replace ones that are of the same pitch before adding them to the end.
        if accs.accs:
            if not ret.foundKey:  # if there are only extra accidentals, make sure this is set.
                ret.foundKey = True
                mv.key = Obj(root="none", acc="", mode="", accidentals=[])
            normalize_accidentals(accs.accs)
            for i in range(len(accs.accs)):
                found = False
                j = 0
                while j < len(mv.key.accidentals) and not found:
                    if mv.key.accidentals[j].note == accs.accs[i].note:
                        found = True
                        if mv.key.accidentals[j].acc != accs.accs[i].acc:
                            # If the accidental is different, then replace it. If it is the same, then the declaration was redundant, so just ignore it.
                            mv.key.accidentals[j].acc = accs.accs[i].acc
                            if mv.key.explicitAccidentals is None:
                                mv.key.explicitAccidentals = []
                            mv.key.explicitAccidentals.append(accs.accs[i])
                    j += 1
                if not found:
                    if mv.key.explicitAccidentals is None:
                        mv.key.explicitAccidentals = []
                    mv.key.explicitAccidentals.append(accs.accs[i])
                    mv.key.accidentals.append(accs.accs[i])
                    if mv.key.impliedNaturals:
                        kkk = 0
                        while kkk < len(mv.key.impliedNaturals):
                            if mv.key.impliedNaturals[kkk].note == accs.accs[i].note:
                                mv.key.impliedNaturals.pop(kkk)
                            kkk += 1
            if not is_inline:
                mv.globalKey = deep_copy_key(mv.key)
            self._set_voice_key()

        # Now see if any optional parameters are present. They have the form "key=value", except that "clef=" is optional
        while len(tokens) > 0:
            t0 = tokens[0].token
            if t0 in ("m", "middle"):
                tokens.pop(0)
                if len(tokens) == 0:
                    warn("Expected = after middle", s, 0)
                    return ret
                token = tokens.pop(0)
                if token.token != "=":
                    warn("Expected = after middle", s, token.start)
                    continue
                if len(tokens) == 0:
                    warn("Expected parameter after middle=", s, 0)
                    return ret
                pitch = tokenizer.get_pitch_from_tokens(tokens)
                if pitch.warn:
                    warn(pitch.warn, s, 0)
                if pitch.position:
                    mv.clef.verticalPos = pitch.position - 6  # we get the position from the middle line, but want to offset it to the first ledger line.
            elif t0 in ("transpose", "stafflines", "staffscale", "octave"):
                name = t0
                tokens.pop(0)
                if len(tokens) == 0:
                    warn("Expected = after " + name, s, 0)
                    return ret
                token = tokens.pop(0)
                if token.token != "=":
                    warn("Expected = after " + name, s, token.start)
                    continue
                if len(tokens) == 0:
                    warn("Expected parameter after " + name + "=", s, 0)
                    return ret
                if tokens[0].type != 'number':
                    warn("Expected number after " + name, s, tokens[0].start)
                    continue
                if name == "transpose":
                    mv.clef.transpose = tokens[0].intt
                elif name == "stafflines":
                    mv.clef.stafflines = tokens[0].intt
                elif name == "staffscale":
                    mv.clef.staffscale = tokens[0].floatt
                else:
                    mv.octave = tokens[0].intt
                tokens.pop(0)
            elif t0 == "style":
                tokens.pop(0)
                if len(tokens) == 0:
                    warn("Expected = after style", s, 0)
                    return ret
                token = tokens.pop(0)
                if token.token != "=":
                    warn("Expected = after style", s, token.start)
                    continue
                if len(tokens) == 0:
                    warn("Expected parameter after style=", s, 0)
                    return ret
                if tokens[0].token in ("normal", "harmonic", "rhythm", "x", "triangle"):
                    mv.style = tokens[0].token
                    tokens.pop(0)
                else:
                    warn("error parsing style element: " + js_str(tokens[0].token), s, tokens[0].start)
            elif t0 in ("clef", "treble", "bass", "alto", "tenor", "perc", "none"):
                if t0 == "clef":
                    tokens.pop(0)
                    if len(tokens) == 0:
                        warn("Expected = after clef", s, 0)
                        return ret
                    token = tokens.pop(0)
                    if token.token != "=":
                        warn("Expected = after clef", s, token.start)
                        continue
                    if len(tokens) == 0:
                        warn("Expected parameter after clef=", s, 0)
                        return ret
                    # yes, we want to fall through. That allows "clef=" to be optional.
                # clef is [clef=] [⟨clef type⟩] [⟨line number⟩] [+8|-8]
                clef = tokens.pop(0)
                ct = clef.token
                if ct in ('treble', 'tenor', 'alto', 'bass', 'perc', 'none'):
                    pass
                elif ct == 'C' or ct == 'c':
                    clef.token = 'alto'
                elif ct == 'F' or ct == 'f':
                    clef.token = 'bass'
                elif ct == 'G' or ct == 'g':
                    clef.token = 'treble'
                else:
                    warn("Expected clef name. Found " + js_str(clef.token), s, clef.start)
                if len(tokens) > 0 and tokens[0].type == 'number':
                    clef.token += tokens[0].token
                    tokens.pop(0)
                if len(tokens) > 1 and tokens[0].token in ('-', '+', '^', '_') and tokens[1].token == '8':
                    clef.token += tokens[0].token + tokens[1].token
                    tokens.pop(0)
                    tokens.pop(0)
                mv.clef = Obj(type=clef.token, verticalPos=calc_middle(clef.token, 0))
                if mv.currentVoice and mv.currentVoice.transpose is not None:
                    mv.clef.transpose = mv.currentVoice.transpose
                ret.foundClef = True
            else:
                warn("Unknown parameter: " + js_str(tokens[0].token), s, tokens[0].start)
                tokens.pop(0)
        return ret

    def _set_current_voice(self, vid):
        mv = self.multiline_vars
        current_voice = mv.voices.get(vid)
        if mv.currentVoice:
            if mv.currentVoice.index == current_voice.index and mv.currentVoice.staffNum == current_voice.staffNum:
                return None  # there was no change so don't reset it.
        mv.currentVoice = current_voice
        if current_voice.key:
            mv.key = deep_copy_key(current_voice.key)
        elif mv.globalKey:
            mv.key = deep_copy_key(mv.globalKey)
        return self.tune_builder.set_current_voice(current_voice.staffNum, current_voice.index, vid)

    def parse_voice(self, line, i, e):
        # First truncate the string to the first non-space character after V: through either the
        # end of the line or a % character. Then remove trailing spaces, too.
        mv = self.multiline_vars
        warn = self.warn
        tokenizer = self.tokenizer
        ret = tokenizer.get_meat(line, i, e)
        st = Obj(start=ret.start)
        end = ret.end
        # The first thing on the line is the ID. It can be any non-space string and terminates at the first space.
        vid = tokenizer.get_token(line, st.start, end)
        if len(vid) == 0:
            warn("Expected a voice id", line, st.start)
            return None
        is_new = False
        if mv.voices.get(vid) is None:
            mv.voices[vid] = Obj()
            is_new = True
            if mv.score_is_present:
                warn("Can't have an unknown V: id when the %score directive is present", line, st.start)
        st.start += len(vid)
        st.start += tokenizer.eat_white_space(line, st.start)

        staff_info = Obj(startStaff=is_new)

        def check_attr(attr, name):
            if attr.warn is not None:
                warn("Expected value for " + name + " in voice: " + attr.warn, line, st.start)
                return False
            if attr.err is not None:
                warn("Expected value for " + name + " in voice: " + attr.err, line, st.start)
                return False
            if len(attr.token) == 0 and at(line, st.start) != '"':
                warn("Expected value for " + name + " in voice", line, st.start)
                return False
            return True

        def add_next_token_to_staff_info(name):
            attr = tokenizer.get_voice_token(line, st.start, end)
            if check_attr(attr, name):
                staff_info[name] = attr.token
            st.start += attr.len

        def add_next_token_to_voice_info(vid_, name, typ):
            attr = tokenizer.get_voice_token(line, st.start, end)
            if check_attr(attr, name):
                if typ == 'number':
                    attr.token = parse_float(attr.token)
                mv.voices[vid_][name] = attr.token
            st.start += attr.len

        def get_next_token(name, typ):
            attr = tokenizer.get_voice_token(line, st.start, end)
            if check_attr(attr, name):
                if typ == 'number':
                    attr.token = parse_float(attr.token)
                # NOTE: abcjs returns here without advancing past the token.
                return attr.token
            st.start += attr.len
            return None

        def add_next_note_token_to_voice_info(vid_, name):
            note_to_transposition = {"_B": 2, "_E": 9, "_b": -10, "_e": -3}
            attr = tokenizer.get_voice_token(line, st.start, end)
            if attr.warn is not None:
                warn("Expected one of (_B, _E, _b, _e) for " + name + " in voice: " + attr.warn, line, st.start)
            elif len(attr.token or "") == 0 and at(line, st.start) != '"':
                warn("Expected one of (_B, _E, _b, _e) for " + name + " in voice", line, st.start)
            else:
                t = note_to_transposition.get(attr.token)
                if not t:
                    warn("Expected one of (_B, _E, _b, _e) for " + name + " in voice", line, st.start)
                else:
                    mv.voices[vid_][name] = t
            st.start += attr.len

        # Then the following items can occur in any order:
        while st.start < end:
            token = tokenizer.get_voice_token(line, st.start, end)
            st.start += token.len

            if token.warn:
                warn("Error parsing voice: " + token.warn, line, st.start)
            else:
                attr = None
                tt = token.token
                if tt in ('clef', 'cl'):
                    add_next_token_to_staff_info('clef')
                    oct = 0
                    if staff_info.clef is not None:
                        staff_info.clef = re.sub(r"[',]", "", staff_info.clef)
                        if '+16' in staff_info.clef:
                            oct += 14
                            staff_info.clef = staff_info.clef.replace('+16', '', 1)
                        staff_info.verticalPos = calc_middle(staff_info.clef, oct)
                elif tt in _voice_clef_tokens:
                    staff_info.clef = re.sub(r"[',]", "", tt)
                    staff_info.verticalPos = calc_middle(staff_info.clef, 0)
                    mv.voices[vid].clef = tt
                elif tt in ('staves', 'stave', 'stv'):
                    add_next_token_to_staff_info('staves')
                elif tt in ('brace', 'brc'):
                    add_next_token_to_staff_info('brace')
                elif tt in ('bracket', 'brk'):
                    add_next_token_to_staff_info('bracket')
                elif tt in ('name', 'nm'):
                    add_next_token_to_staff_info('name')
                elif tt in ('subname', 'sname', 'snm'):
                    add_next_token_to_staff_info('subname')
                elif tt == 'merge':
                    staff_info.startStaff = False
                elif tt in ('stem', 'stems'):
                    attr = tokenizer.get_voice_token(line, st.start, end)
                    if attr.warn is not None:
                        warn("Expected value for stems in voice: " + attr.warn, line, st.start)
                    elif attr.err is not None:
                        warn("Expected value for stems in voice: " + attr.err, line, st.start)
                    elif attr.token == 'up' or attr.token == 'down':
                        mv.voices[vid].stem = attr.token
                    else:
                        warn("Expected up or down for voice stem", line, st.start)
                    st.start += attr.len
                elif tt in ('up', 'down'):
                    mv.voices[vid].stem = tt
                elif tt in ('middle', 'm'):
                    add_next_token_to_staff_info('verticalPos')
                    staff_info.verticalPos = parse_middle(staff_info.verticalPos).mid
                elif tt in ('gchords', 'gch'):
                    mv.voices[vid].suppressChords = True
                    # gchords can stand on its own, or it could be gchords=0.
                    attr = tokenizer.get_voice_token(line, st.start, end)
                    if attr.token == "0":
                        st.start = st.start + attr.len
                elif tt in ('space', 'spc'):
                    add_next_token_to_staff_info('spacing')
                elif tt == 'scale':
                    add_next_token_to_voice_info(vid, 'scale', 'number')
                elif tt == 'score':
                    add_next_note_token_to_voice_info(vid, 'scoreTranspose')
                elif tt == 'transpose':
                    add_next_token_to_voice_info(vid, 'transpose', 'number')
                elif tt == 'stafflines':
                    add_next_token_to_voice_info(vid, 'stafflines', 'number')
                elif tt == 'staffscale':
                    add_next_token_to_voice_info(vid, 'staffscale', 'number')
                elif tt == 'octave':
                    add_next_token_to_voice_info(vid, 'octave', 'number')
                elif tt == 'volume':
                    add_next_token_to_voice_info(vid, 'volume', 'number')
                elif tt == 'cue':
                    cue = get_next_token('cue', 'string')
                    if cue == 'on':
                        mv.voices[vid].scale = 0.6
                    else:
                        mv.voices[vid].scale = 1
                elif tt == "style":
                    attr = tokenizer.get_voice_token(line, st.start, end)
                    if attr.warn is not None:
                        warn("Expected value for style in voice: " + attr.warn, line, st.start)
                    elif attr.err is not None:
                        warn("Expected value for style in voice: " + attr.err, line, st.start)
                    elif attr.token in ('normal', 'harmonic', 'rhythm', 'x', 'triangle'):
                        mv.voices[vid].style = attr.token
                    else:
                        warn("Expected one of [normal, harmonic, rhythm, x, triangle] for voice style", line, st.start)
                    st.start += attr.len
            st.start += tokenizer.eat_white_space(line, st.start)

        # now we've filled up staffInfo, figure out what to do with this voice
        if staff_info.startStaff or len(mv.staves) == 0:
            mv.staves.append(Obj(index=len(mv.staves), meter=mv.origMeter))
            if not mv.score_is_present:
                mv.staves[-1].numVoices = 0
        if mv.voices[vid].staffNum is None:
            # store where to write this for quick access later.
            mv.voices[vid].staffNum = len(mv.staves) - 1
            vi = 0
            for v in mv.voices:
                if mv.voices[v].staffNum == mv.voices[vid].staffNum:
                    vi += 1
            mv.voices[vid].index = vi - 1
        s = mv.staves[mv.voices[vid].staffNum]
        if not mv.score_is_present:
            s.numVoices = (s.numVoices if s.numVoices is not None else float('nan')) + 1
        if staff_info.clef:
            s.clef = Obj(type=staff_info.clef, verticalPos=staff_info.verticalPos)
        if staff_info.spacing:
            s.spacing_below_offset = staff_info.spacing
        if staff_info.verticalPos:
            s.verticalPos = staff_info.verticalPos

        if staff_info.name:
            if s.name:
                s.name.append(staff_info.name)
            else:
                s.name = [staff_info.name]
        if staff_info.subname:
            if s.subname:
                s.subname.append(staff_info.subname)
            else:
                s.subname = [staff_info.subname]

        return self._set_current_voice(vid)
