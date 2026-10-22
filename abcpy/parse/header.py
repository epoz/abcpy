"""Parses the header fields of an ABC tune (port of ``abc_parse_header.js``)."""

from ..jsutil import Obj, at, parse_int, number, js_set, strip, is_nan


class TempoError(Exception):
    pass


_tempo_string = {
    'larghissimo': 20,
    'adagissimo': 24,
    'sostenuto': 28,
    'grave': 32,
    'largo': 40,
    'lento': 50,
    'larghetto': 60,
    'adagio': 68,
    'adagietto': 74,
    'andante': 80,
    'andantino': 88,
    "marcia moderato": 84,
    "andante moderato": 100,
    'moderato': 112,
    'allegretto': 116,
    "allegro moderato": 120,
    'allegro': 126,
    'animato': 132,
    'agitato': 140,
    'veloce': 148,
    "mosso vivo": 156,
    'vivace': 164,
    'vivacissimo': 172,
    'allegrissimo': 176,
    'presto': 184,
    'prestissimo': 210,
}

meta_text_headers = {
    'A': 'author',
    'B': 'book',
    'C': 'composer',
    'D': 'discography',
    'F': 'url',
    'G': 'group',
    'I': 'instruction',
    'N': 'notes',
    'O': 'origin',
    'R': 'rhythm',
    'S': 'source',
    'W': 'unalignedWords',
    'Z': 'transcription',
}


class _Tokens(list):
    """A token list whose ``shift`` returns an empty token when exhausted (like JS ``undefined``)."""

    def shift(self):
        if len(self) == 0:
            return None
        return self.pop(0)


class ParseHeader:
    def __init__(self, tokenizer, warn, multiline_vars, tune, tune_builder, directive, key_voice):
        self.tokenizer = tokenizer
        self.warn = warn
        self.multiline_vars = multiline_vars
        self.tune = tune
        self.tune_builder = tune_builder
        self.directive = directive
        self.key_voice = key_voice
        self.reset(tokenizer, warn, multiline_vars, tune)

    def reset(self, tokenizer, warn, multiline_vars, tune):
        self.key_voice.initialize(tokenizer, warn, multiline_vars, tune, self.tune_builder)
        self.directive.initialize(tokenizer, warn, multiline_vars, tune, self.tune_builder)

    def set_title(self, title, orig_size):
        mv = self.multiline_vars
        if mv.hasMainTitle:
            self.tune_builder.add_subtitle(title, Obj(startChar=mv.iChar, endChar=mv.iChar + orig_size + 2))  # display secondary title
        else:
            self.tune_builder.add_meta_text("title", title, Obj(startChar=mv.iChar, endChar=mv.iChar + orig_size + 2))
            mv.hasMainTitle = True

    def _set_default_length_if_needed(self, value=0.125):
        mv = self.multiline_vars
        if mv.havent_set_length is True:
            mv.default_length = value
            mv.havent_set_length = False

    def set_meter(self, line):
        line = self.tokenizer.strip_comment(line)
        simple = {
            'C': 'common_time',
            'C|': 'cut_time',
            'o': 'tempus_perfectum',
            'c': 'tempus_imperfectum',
            'o.': 'tempus_perfectum_prolatio',
            'c.': 'tempus_imperfectum_prolatio',
        }
        if line in simple:
            self._set_default_length_if_needed()
            return Obj(type=simple[line])
        if len(line) == 0 or line.lower() == 'none':
            self._set_default_length_if_needed()
            return None
        tokens = _Tokens(self.tokenizer.tokenize(line, 0, len(line)))
        # the form is [open_paren] decimal [ plus|dot decimal ]... [close_paren] slash decimal [plus same_as_before]
        try:
            def parse_num():
                # handles this much: [open_paren] decimal [ plus|dot decimal ]... [close_paren]
                ret = Obj(value=0, num="")

                tok = tokens.shift()
                if tok is not None and tok.token == '(':
                    tok = tokens.shift()
                while True:
                    if tok is None or tok.type != 'number':
                        raise TempoError("Expected top number of meter")
                    ret.value += parse_int(tok.token)
                    ret.num += tok.token
                    if len(tokens) == 0 or tokens[0].token == '/':
                        return ret
                    tok = tokens.shift()
                    if tok.token == ')':
                        if len(tokens) == 0 or tokens[0].token == '/':
                            return ret
                        raise TempoError("Unexpected paren in meter")
                    if tok.token != '.' and tok.token != '+':
                        raise TempoError("Expected top number of meter")
                    ret.num += tok.token
                    if len(tokens) == 0:
                        raise TempoError("Expected top number of meter")
                    tok = tokens.shift()

            def parse_fraction():
                # handles this much: parseNum slash decimal
                ret = parse_num()
                if len(tokens) == 0:
                    return ret
                tok = tokens.shift()
                if tok.token != '/':
                    raise TempoError("Expected slash in meter")
                tok = tokens.shift()
                if tok is None or tok.type != 'number':
                    raise TempoError("Expected bottom number of meter")
                ret.den = tok.token
                ret.value = ret.value / parse_int(ret.den) if parse_int(ret.den) != 0 else (float('inf') if ret.value > 0 else float('nan'))
                return ret

            if len(tokens) == 0:
                raise TempoError("Expected meter definition in M: line")
            meter = Obj(type='specified', value=[])
            total_length = 0
            while True:
                ret = parse_fraction()
                total_length += ret.value
                mv_ = Obj(num=ret.num)
                if ret.den is not None:
                    mv_.den = ret.den
                meter.value.append(mv_)
                if len(tokens) == 0:
                    break

            self._set_default_length_if_needed(0.0625 if total_length < 0.75 else 0.125)
            return meter
        except TempoError as e:
            self.warn(str(e), line, 0)
        return None

    def calc_tempo(self, rel_tempo):
        mv = self.multiline_vars
        dur = 1 / 4
        if mv.meter and mv.meter.type == 'specified':
            dur = 1 / parse_int(mv.meter.value[0].den) if parse_int(mv.meter.value[0].den) else float('nan')
        elif mv.origMeter and mv.origMeter.type == 'specified':
            dur = 1 / parse_int(mv.origMeter.value[0].den) if parse_int(mv.origMeter.value[0].den) else float('nan')
        # abcjs loops with "i < relTempo.duration" (comparing a number with an array), which only
        # does anything when the array has a single element.
        duration = rel_tempo.duration
        if isinstance(duration, list):
            limit = number(duration)
            i = 0
            while not is_nan(limit) and i < limit:
                value = duration[i] if i < len(duration) else None
                js_set(duration, i, dur * value if value is not None else float('nan'))
                i += 1
                limit = number(duration)
        return rel_tempo

    def resolve_tempo(self):
        mv = self.multiline_vars
        if mv.tempo:  # If there's a tempo waiting to be resolved
            self.calc_tempo(mv.tempo)
            self.tune.metaText.tempo = mv.tempo
            del mv.tempo

    def add_user_definition(self, line, start, end):
        warn = self.warn
        mv = self.multiline_vars
        equals = line.find('=', start)
        if equals == -1:
            warn("Need an = in a macro definition", line, start)
            return

        before = strip(line[start:equals])
        after = strip(line[equals + 1:])

        if len(before) != 1:
            warn("Macro definitions can only be one character", line, start)
            return
        legal_chars = "HIJKLMNOPQRSTUVWXYhijklmnopqrstuvw~"
        if before not in legal_chars:
            warn("Macro definitions must be H-Y, h-w, or tilde", line, start)
            return
        if len(after) == 0:
            warn("Missing macro definition", line, start)
            return
        if mv.macros is None:
            mv.macros = Obj()
        mv.macros[before] = after

    def set_default_length(self, line, start, end):
        mv = self.multiline_vars
        length = line[start:end].replace(" ", "")
        len_arr = length.split('/')
        if len(len_arr) == 2:
            n = parse_int(len_arr[0])
            d = parse_int(len_arr[1])
            if not is_nan(d) and d > 0:
                mv.default_length = n / d  # a whole note is 1
                mv.havent_set_length = False
        elif len(len_arr) == 1 and len_arr[0] == '1':
            mv.default_length = 1
            mv.havent_set_length = False

    def set_tempo(self, line, start, end, i_char):
        # Q - tempo; can be used to specify the notes per minute, e.g. If
        # the meter denominator is a 4 note then Q:120 or Q:C=120
        # is 120 quarter notes per minute. Similarly  Q:C3=40 would be 40
        # dotted half notes per minute. An absolute tempo may also be
        # set, e.g. Q:1/8=120 is 120 eighth notes per minute,
        # irrespective of the meter's denominator.
        mv = self.multiline_vars
        try:
            tokens = _Tokens(self.tokenizer.tokenize(line, start, end))

            if len(tokens) == 0:
                raise TempoError("Missing parameter in Q: field")

            tempo = Obj(startChar=i_char + start - 2, endChar=i_char + end)
            delay_set = True
            token = tokens.shift()
            if token.type == 'quote':
                tempo.preString = token.token
                token = tokens.shift()
                if len(tokens) == 0:  # It's ok to just get a string for the tempo
                    # If the string is a well-known tempo, put in the bpm
                    bpm = _tempo_string.get(tempo.preString.lower())
                    if bpm:
                        tempo.bpm = bpm
                        tempo.suppressBpm = True
                    return Obj(type='immediate', tempo=tempo)
            if token.type == 'alpha' and token.token == 'C':  # either type 2 or type 3
                if len(tokens) == 0:
                    raise TempoError("Missing tempo after C in Q: field")
                token = tokens.shift()
                if token.type == 'punct' and token.token == '=':
                    # This is a type 2 format. The duration is an implied 1
                    if len(tokens) == 0:
                        raise TempoError("Missing tempo after = in Q: field")
                    token = tokens.shift()
                    if token.type != 'number':
                        raise TempoError("Expected number after = in Q: field")
                    tempo.duration = [1]
                    tempo.bpm = parse_int(token.token)
                elif token.type == 'number':
                    # This is a type 3 format.
                    tempo.duration = [parse_int(token.token)]
                    if len(tokens) == 0:
                        raise TempoError("Missing = after duration in Q: field")
                    token = tokens.shift()
                    if token.type != 'punct' or token.token != '=':
                        raise TempoError("Expected = after duration in Q: field")
                    if len(tokens) == 0:
                        raise TempoError("Missing tempo after = in Q: field")
                    token = tokens.shift()
                    if token.type != 'number':
                        raise TempoError("Expected number after = in Q: field")
                    tempo.bpm = parse_int(token.token)
                else:
                    raise TempoError("Expected number or equal after C in Q: field")
            elif token.type == 'number':  # either type 1 or type 4
                num = parse_int(token.token)
                if len(tokens) == 0 or tokens[0].type == 'quote':
                    # This is type 1
                    tempo.duration = [1]
                    tempo.bpm = num
                else:  # This is type 4
                    delay_set = False
                    token = tokens.shift()
                    if token.type != 'punct' and token.token != '/':
                        raise TempoError("Expected fraction in Q: field")
                    token = tokens.shift()
                    if token is None or token.type != 'number':
                        raise TempoError("Expected fraction in Q: field")
                    den = parse_int(token.token)
                    tempo.duration = [num / den if den else float('nan')]
                    # We got the first fraction, keep getting more as long as we find them.
                    while len(tokens) > 0 and tokens[0].token != '=' and tokens[0].type != 'quote':
                        token = tokens.shift()
                        if token.type != 'number':
                            raise TempoError("Expected fraction in Q: field")
                        num = parse_int(token.token)
                        token = tokens.shift()
                        if token is None or (token.type != 'punct' and token.token != '/'):
                            raise TempoError("Expected fraction in Q: field")
                        token = tokens.shift()
                        if token is None or token.type != 'number':
                            raise TempoError("Expected fraction in Q: field")
                        den = parse_int(token.token)
                        tempo.duration.append(num / den if den else float('nan'))
                    token = tokens.shift()
                    if token is None or (token.type != 'punct' and token.token != '='):
                        raise TempoError("Expected = in Q: field")
                    token = tokens.shift()
                    if token is None or token.type != 'number':
                        raise TempoError("Expected tempo in Q: field")
                    tempo.bpm = parse_int(token.token)
            else:
                raise TempoError("Unknown value in Q: field")
            if len(tokens) != 0:
                token = tokens.shift()
                if token.type == 'quote':
                    tempo.postString = token.token
                    token = tokens.shift()
                if len(tokens) != 0:
                    raise TempoError("Unexpected string at end of Q: field")
            if mv.printTempo is False:
                tempo.suppress = True
            return Obj(type='delaySet' if delay_set else 'immediate', tempo=tempo)
        except TempoError as msg:
            self.warn(str(msg), line, start)
            return Obj(type='none')

    def letter_to_inline_header(self, line, i, start_line):
        mv = self.multiline_vars
        tokenizer = self.tokenizer
        tune_builder = self.tune_builder
        warn = self.warn
        ws = tokenizer.eat_white_space(line, i)
        i += ws
        if len(line) >= i + 5 and at(line, i) == '[' and at(line, i + 2) == ':':
            e = line.find(']', i)
            start_char = mv.iChar + i
            end_char = mv.iChar + e + 1
            field = line[i:i + 3]

            def sub(a, b):
                # line.substring(a, b) where b may be -1
                from ..jsutil import substring
                return substring(line, a, b)

            if field == "[I:":
                err = self.directive.add_directive(sub(i + 3, e))
                if err:
                    warn(err, line, i)
                return [e - i + 1 + ws]
            if field == "[M:":
                meter = self.set_meter(sub(i + 3, e))
                if start_line and mv.currentVoice and meter:
                    mv.staves[mv.currentVoice.staffNum].meter = meter
                elif tune_builder.has_begin_music() and meter:
                    tune_builder.append_starting_element('meter', start_char, end_char, meter)
                else:
                    mv.meter = meter
                return [e - i + 1 + ws]
            if field == "[K:":
                result = self.key_voice.parse_key(sub(i + 3, e), True)
                if result.foundClef and tune_builder.has_begin_music():
                    tune_builder.append_starting_element('clef', start_char, end_char, mv.clef)
                if result.foundKey and tune_builder.has_begin_music():
                    tune_builder.append_starting_element('key', start_char, end_char, self.key_voice.fix_key(mv.clef, mv.key))
                return [e - i + 1 + ws]
            if field == "[P:":
                part = self.directive.parse_font_change_line(sub(i + 3, e))
                if start_line or len(self.tune.lines) <= self.tune.lineNum:
                    mv.partForNextLine = Obj(title=part, startChar=start_char, endChar=end_char)
                else:
                    tune_builder.append_element('part', start_char, end_char, Obj(title=part))
                return [e - i + 1 + ws]
            if field == "[L:":
                self.set_default_length(line, i + 3, e)
                return [e - i + 1 + ws]
            if field == "[Q:":
                if e > 0:
                    tempo = self.set_tempo(line, i + 3, e, mv.iChar)
                    if tempo.type == 'delaySet':
                        if tune_builder.has_begin_music():
                            tune_builder.append_element('tempo', start_char, end_char, self.calc_tempo(tempo.tempo))
                        else:
                            mv.tempoForNextLine = ['tempo', start_char, end_char, self.calc_tempo(tempo.tempo)]
                    elif tempo.type == 'immediate':
                        if not start_line and tune_builder.has_begin_music():
                            tune_builder.append_element('tempo', start_char, end_char, tempo.tempo)
                        else:
                            mv.tempoForNextLine = ['tempo', start_char, end_char, tempo.tempo]
                    return [e - i + 1 + ws, at(line, i + 1), sub(i + 3, e)]
            elif field == "[V:":
                if e > 0:
                    needs_new_line = self.key_voice.parse_voice(line, i + 3, e)
                    return [e - i + 1 + ws, at(line, i + 1), sub(i + 3, e), needs_new_line]
            elif field == "[r:":
                return [e - i + 1 + ws]
        return [0]

    def letter_to_body_header(self, line, i):
        mv = self.multiline_vars
        tune_builder = self.tune_builder
        warn = self.warn
        if len(line) >= i + 3:
            field = line[i:i + 2]
            if field == "I:":
                err = self.directive.add_directive(line[i + 2:])
                if err:
                    warn(err, line, i)
                return [len(line)]
            if field == "M:":
                meter = self.set_meter(line[i + 2:])
                if tune_builder.has_begin_music() and meter:
                    tune_builder.append_starting_element('meter', mv.iChar + i, mv.iChar + len(line), meter)
                return [len(line)]
            if field == "K:":
                result = self.key_voice.parse_key(line[i + 2:], tune_builder.has_begin_music())
                if result.foundClef and tune_builder.has_begin_music() and mv.keywarn is not False:
                    tune_builder.append_starting_element('clef', mv.iChar + i, mv.iChar + len(line), mv.clef)
                if result.foundKey and tune_builder.has_begin_music() and mv.keywarn is not False:
                    tune_builder.append_starting_element('key', mv.iChar + i, mv.iChar + len(line), self.key_voice.fix_key(mv.clef, mv.key))
                return [len(line)]
            if field == "P:":
                if tune_builder.has_begin_music():
                    tune_builder.append_element('part', mv.iChar + i, mv.iChar + len(line), Obj(title=line[i + 2:]))
                return [len(line)]
            if field == "L:":
                self.set_default_length(line, i + 2, len(line))
                return [len(line)]
            if field == "Q:":
                e = line.find('\x12', i + 2)
                if e == -1:
                    e = len(line)
                tempo = self.set_tempo(line, i + 2, e, mv.iChar)
                if tempo.type == 'delaySet':
                    tune_builder.append_element('tempo', mv.iChar + i, mv.iChar + len(line), self.calc_tempo(tempo.tempo))
                elif tempo.type == 'immediate':
                    tune_builder.append_element('tempo', mv.iChar + i, mv.iChar + len(line), tempo.tempo)
                return [e, at(line, i), strip(line[i + 2:])]
            if field == "V:":
                needs_new_line = self.key_voice.parse_voice(line, i + 2, len(line))
                return [len(line), at(line, i), strip(line[i + 2:]), needs_new_line]
        return [0]

    def parse_header(self, line):
        mv = self.multiline_vars
        tokenizer = self.tokenizer
        tune_builder = self.tune_builder
        directive = self.directive
        field = meta_text_headers.get(line[0])
        orig_size = len(line) - 2
        rest_of_line = tokenizer.translate_string(tokenizer.strip_comment(line[2:]))
        if field == 'unalignedWords' or field == 'notes':
            # These fields can be multi-line
            tune_builder.add_meta_text_array(field, directive.parse_font_change_line(rest_of_line), Obj(startChar=mv.iChar, endChar=mv.iChar + len(line)))
        elif field is not None:
            # these fields are single line
            tune_builder.add_meta_text(field, directive.parse_font_change_line(rest_of_line), Obj(startChar=mv.iChar, endChar=mv.iChar + len(line)))
        else:
            start_char = mv.iChar
            end_char = start_char + len(line)
            c = line[0]
            if c == 'H':
                # History is a little different because once it starts it continues until another header field is encountered
                tune_builder.add_meta_text_array("history", directive.parse_font_change_line(rest_of_line), Obj(startChar=mv.iChar, endChar=mv.iChar + len(line)))
                line = tokenizer.peek_line()
                while line and at(line, 1) != ':':
                    tokenizer.next_line()
                    tune_builder.add_meta_text_array("history", directive.parse_font_change_line(tokenizer.translate_string(tokenizer.strip_comment(line))), Obj(startChar=mv.iChar, endChar=mv.iChar + len(line)))
                    line = tokenizer.peek_line()
            elif c == 'K':
                # since the key is the last thing that can happen in the header, we can resolve the tempo now
                self.resolve_tempo()
                result = self.key_voice.parse_key(line[2:], False)
                if not mv.is_in_header and tune_builder.has_begin_music() and mv.keywarn is not False:
                    if result.foundClef:
                        tune_builder.append_starting_element('clef', start_char, end_char, mv.clef)
                    if result.foundKey:
                        tune_builder.append_starting_element('key', start_char, end_char, self.key_voice.fix_key(mv.clef, mv.key))
                mv.is_in_header = False  # The first key signifies the end of the header.
            elif c == 'L':
                self.set_default_length(line, 2, len(line))
            elif c == 'M':
                mv.origMeter = mv.meter = self.set_meter(line[2:])
            elif c == 'P':
                if mv.is_in_header:
                    tune_builder.add_meta_text("partOrder", directive.parse_font_change_line(rest_of_line), Obj(startChar=mv.iChar, endChar=mv.iChar + len(line)))
                else:
                    mv.partForNextLine = Obj(title=rest_of_line, startChar=start_char, endChar=end_char)
            elif c == 'Q':
                tempo = self.set_tempo(line, 2, len(line), mv.iChar)
                if tempo.type == 'delaySet':
                    mv.tempo = tempo.tempo
                elif tempo.type == 'immediate':
                    if not self.tune.metaText.get('tempo'):
                        self.tune.metaText.tempo = tempo.tempo
                    else:
                        mv.tempoForNextLine = ['tempo', start_char, end_char, tempo.tempo]
            elif c == 'T':
                if mv.titlecaps:
                    rest_of_line = rest_of_line.upper()
                self.set_title(directive.parse_font_change_line(tokenizer.the_reverser(rest_of_line)), orig_size)
            elif c == 'U':
                self.add_user_definition(line, 2, len(line))
            elif c == 'V':
                self.key_voice.parse_voice(line, 2, len(line))
                if not mv.is_in_header:
                    return Obj(newline=True)
            elif c == 's':
                return Obj(symbols=True)
            elif c == 'w':
                return Obj(words=True)
            elif c == 'X':
                pass
            elif c in ('E', 'm'):
                self.warn("Ignored header", line, 0)
            else:
                return Obj(regular=True)
        return Obj()
