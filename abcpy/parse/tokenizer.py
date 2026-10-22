"""Tokenizes an ABC Music Notation string to support the parser.

Port of abcjs ``abc_tokenizer.js``.  Each ``get_*`` function extracts a
particular element from the passed stream.  The return value is normally a
dict ``{len: num_chars_consumed, token: str}``; ``len == 0`` means that the
element was not found.
"""

import re

from ..jsutil import Obj, at, substring, parse_int, parse_float, is_nan, js_str, strip


def _is_letter(ch):
    return ch is not None and (("A" <= ch <= "Z") or ("a" <= ch <= "z"))


def _is_number(ch):
    return ch is not None and "0" <= ch <= "9"


def _finished(s, i):
    return i >= len(s)


_char_map = {
    "`a": 'à', "'a": "á", "^a": "â", "~a": "ã", "\"a": "ä", "oa": "å", "aa": "å", "=a": "ā", "ua": "ă", ";a": "ą",
    "`e": 'è', "'e": "é", "^e": "ê", "\"e": "ë", "=e": "ē", "ue": "ĕ", ";e": "ę", ".e": "ė",
    "`i": 'ì', "'i": "í", "^i": "î", "\"i": "ï", "=i": "ī", "ui": "ĭ", ";i": "į",
    "`o": 'ò', "'o": "ó", "^o": "ô", "~o": "õ", "\"o": "ö", "=o": "ō", "uo": "ŏ", "/o": "ø",
    "`u": 'ù', "'u": "ú", "^u": "û", "~u": "ũ", "\"u": "ü", "ou": "ů", "=u": "ū", "uu": "ŭ", ";u": "ų",
    "`A": 'À', "'A": "Á", "^A": "Â", "~A": "Ã", "\"A": "Ä", "oA": "Å", "AA": "Å", "=A": "Ā", "uA": "Ă", ";A": "Ą",
    "`E": 'È', "'E": "É", "^E": "Ê", "\"E": "Ë", "=E": "Ē", "uE": "Ĕ", ";E": "Ę", ".E": "Ė",
    "`I": 'Ì', "'I": "Í", "^I": "Î", "~I": "Ĩ", "\"I": "Ï", "=I": "Ī", "uI": "Ĭ", ";I": "Į", ".I": "İ",
    "`O": 'Ò', "'O": "Ó", "^O": "Ô", "~O": "Õ", "\"O": "Ö", "=O": "Ō", "uO": "Ŏ", "/O": "Ø",
    "`U": 'Ù', "'U": "Ú", "^U": "Û", "~U": "Ũ", "\"U": "Ü", "oU": "Ů", "=U": "Ū", "uU": "Ŭ", ";U": "Ų",
    "ae": "æ", "AE": "Æ", "oe": "œ", "OE": "Œ", "ss": "ß",
    "'c": "ć", "^c": "ĉ", "uc": "č", "cc": "ç", ".c": "ċ", "cC": "Ç", "'C": "Ć", "^C": "Ĉ", "uC": "Č", ".C": "Ċ",
    "~N": "Ñ", "~n": "ñ",
    "=s": "š", "vs": "š",
    "DH": "Ð", "dh": "ð",
    "HO": "Ő", "Ho": "ő", "HU": "Ű", "Hu": "ű",
    "'Y": "Ý", "'y": "ý", "^Y": "Ŷ", "^y": "ŷ", "\"Y": "Ÿ", "\"y": "ÿ",
    "vS": "Š", "vZ": "Ž", "vz": 'ž',
}
_char_map1 = {
    "#": "♯",
    "b": "♭",
    "=": "♮",
}
_char_map2 = {
    "201": "♯",
    "202": "♭",
    "203": "♮",
    "241": "¡",
    "242": "¢", "252": "a", "262": "2", "272": "o", "302": "Â", "312": "Ê", "322": "Ò", "332": "Ú", "342": "â", "352": "ê", "362": "ò", "372": "ú",
    "243": "£", "253": "«", "263": "3", "273": "»", "303": "Ã", "313": "Ë", "323": "Ó", "333": "Û", "343": "ã", "353": "ë", "363": "ó", "373": "û",
    "244": "¤", "254": "¬", "264": "  ́", "274": "1⁄4", "304": "Ä", "314": "Ì", "324": "Ô", "334": "Ü", "344": "ä", "354": "ì", "364": "ô", "374": "ü",
    "245": "¥", "255": "-", "265": "μ", "275": "1⁄2", "305": "Å", "315": "Í", "325": "Õ", "335": "Ý", "345": "å", "355": "í", "365": "õ", "375": "ý",
    "246": "¦", "256": "®", "266": "¶", "276": "3⁄4", "306": "Æ", "316": "Î", "326": "Ö", "336": "Þ", "346": "æ", "356": "î", "366": "ö", "376": "þ",
    "247": "§", "257": " ̄", "267": "·", "277": "¿", "307": "Ç", "317": "Ï", "327": "×", "337": "ß", "347": "ç", "357": "ï", "367": "÷", "377": "ÿ",
    "250": " ̈", "260": "°", "270": " ̧", "300": "À", "310": "È", "320": "Ð", "330": "Ø", "340": "à", "350": "è", "360": "ð", "370": "ø",
    "251": "©", "261": "±", "271": "1", "301": "Á", "311": "É", "321": "Ñ", "331": "Ù", "341": "á", "351": "é", "361": "ñ", "371": "ù"}

_the_patterns = [
    (re.compile(r",\s*The$"), "The "),
    (re.compile(r",\s*the$"), "the "),
    (re.compile(r",\s*A$"), "A "),
    (re.compile(r",\s*a$"), "a "),
    (re.compile(r",\s*An$"), "An "),
    (re.compile(r",\s*an$"), "an "),
    (re.compile(r",\s*Da$"), "Da "),
    (re.compile(r",\s*La$"), "La "),
    (re.compile(r",\s*Le$"), "Le "),
    (re.compile(r",\s*Les$"), "Les "),
    (re.compile(r",\s*Ye$"), "Ye "),
]

_title_number = re.compile(r"^(\d+)\.")

_acc_translation = {
    '^': 'sharp',
    '^^': 'dblsharp',
    '=': 'natural',
    '_': 'flat',
    '__': 'dblflat',
    '_/': 'quarterflat',
    '^/': 'quartersharp',
}

_note_letters = "abcdefgABCDEFG"


def translate_string(s):
    """Replace the abc backslash escapes (``\\'e`` etc.) with unicode characters."""
    arr = s.split('\\')
    if len(arr) == 1:
        return s
    out = None
    for part in arr:
        if out is None:
            out = part
        else:
            c = _char_map.get(part[0:2])
            if c is not None:
                out += c + part[2:]
            else:
                c = _char_map2.get(part[0:3])
                if c is not None:
                    out += c + part[3:]
                else:
                    c = _char_map1.get(part[0:1])
                    if c is not None:
                        out += c + part[1:]
                    else:
                        out += "\\" + part
    return out


def is_white_space(ch):
    return ch == ' ' or ch == '\t' or ch == '\x12'


class Tokenizer:
    def __init__(self, lines, multiline_vars):
        self.line_index = 0
        self.lines = lines
        self.multiline_vars = multiline_vars

    # -- line handling -----------------------------------------------------
    def peek_line(self):
        return at(self.lines, self.line_index)

    def next_line(self):
        if self.line_index > 0:
            self.multiline_vars.iChar += len(self.lines[self.line_index - 1]) + 1
        if self.line_index < len(self.lines):
            result = self.lines[self.line_index]
            self.line_index += 1
            return result
        return None

    # -- whitespace ----------------------------------------------------------
    is_white_space = staticmethod(is_white_space)
    translate_string = staticmethod(translate_string)

    def skip_white_space(self, s):
        for i in range(len(s)):
            if not is_white_space(s[i]):
                return i
        return len(s)

    def eat_white_space(self, line, index):
        i = index
        while i < len(line):
            if not is_white_space(line[i]):
                return i - index
            i += 1
        return i - index

    # -- keys ----------------------------------------------------------------
    def get_key_pitch(self, s):
        i = self.skip_white_space(s)
        if _finished(s, i):
            return Obj(len=0)
        if s[i] in "ABCDEFG":
            return Obj(len=i + 1, token=s[i])
        return Obj(len=0)

    def get_sharp_flat(self, s):
        if s == 'bass':
            return Obj(len=0)
        c = at(s, 0)
        if c == '#':
            return Obj(len=1, token='#')
        if c == 'b':
            return Obj(len=1, token='b')
        return Obj(len=0)

    def get_mode(self, s):
        def skip_alpha(st, start):
            while start < len(st) and _is_letter(st[start]):
                start += 1
            return start

        i = self.skip_white_space(s)
        if _finished(s, i):
            return Obj(len=0)
        first_three = s[i:i + 3].lower()
        f1 = at(first_three, 1)
        if (len(first_three) > 1 and f1 == ' ') or f1 == '^' or f1 == '_' or f1 == '=':
            first_three = first_three[0]
        table = {
            'mix': 'Mix', 'dor': 'Dor', 'phr': 'Phr', 'lyd': 'Lyd', 'loc': 'Loc',
            'aeo': 'm', 'maj': '', 'ion': '', 'min': 'm', 'm': 'm',
        }
        if first_three in table:
            return Obj(len=skip_alpha(s, i), token=table[first_three])
        return Obj(len=0)

    def get_clef(self, s, b_explicit_only=False):
        str_orig = s
        i = self.skip_white_space(s)
        if _finished(s, i):
            return Obj(len=0)
        needs_clef = False
        str_clef = s[i:]
        if str_clef.startswith('clef='):
            needs_clef = True
            str_clef = str_clef[5:]
            i += 5
        if len(str_clef) == 0 and needs_clef:
            return Obj(len=i + 5, warn="No clef specified: " + str_orig)

        j = self.skip_white_space(str_clef)
        if _finished(str_clef, j):
            return Obj(len=0)
        if j > 0:
            i += j
            str_clef = str_clef[j:]
        name = None
        if str_clef.startswith('treble'):
            name = 'treble'
        elif str_clef.startswith('bass3'):
            name = 'bass3'
        elif str_clef.startswith('bass'):
            name = 'bass'
        elif str_clef.startswith('tenor'):
            name = 'tenor'
        elif str_clef.startswith('alto2'):
            name = 'alto2'
        elif str_clef.startswith('alto1'):
            name = 'alto1'
        elif str_clef.startswith('alto'):
            name = 'alto'
        elif not b_explicit_only and (needs_clef and str_clef.startswith('none')):
            name = 'none'
        elif str_clef.startswith('perc'):
            name = 'perc'
        elif not b_explicit_only and (needs_clef and str_clef.startswith('C')):
            name = 'tenor'
        elif not b_explicit_only and (needs_clef and str_clef.startswith('F')):
            name = 'bass'
        elif not b_explicit_only and (needs_clef and str_clef.startswith('G')):
            name = 'treble'
        else:
            return Obj(len=i + 5, warn="Unknown clef specified: " + str_orig)

        str_clef = str_clef[len(name):]
        j = self.is_match(str_clef, '+8')
        if j > 0:
            name += "+8"
        else:
            j = self.is_match(str_clef, '-8')
            if j > 0:
                name += "-8"
        return Obj(len=i + len(name), token=name, explicit=needs_clef)

    # -- bar lines -------------------------------------------------------
    def get_bar_line(self, line, i):
        c = at(line, i)
        if c == ']':
            i += 1
            c = at(line, i)
            if c == '|':
                return Obj(len=2, token="bar_thick_thin")
            if c == '[':
                i += 1
                c = at(line, i)
                if (c is not None and '1' <= c <= '9') or c == '"':
                    return Obj(len=2, token="bar_invisible")
                return Obj(len=1, warn="Unknown bar symbol")
            return Obj(len=1, token="bar_invisible")
        if c == ':':
            i += 1
            c = at(line, i)
            if c == ':':
                return Obj(len=2, token="bar_dbl_repeat")
            if c == '|':
                i += 1
                c = at(line, i)
                if c == ']':
                    i += 1
                    c = at(line, i)
                    if c == '|':
                        i += 1
                        if at(line, i) == ':':
                            return Obj(len=5, token="bar_dbl_repeat")
                        return Obj(len=3, token="bar_right_repeat")
                    return Obj(len=3, token="bar_right_repeat")
                if c == '|':
                    i += 1
                    if at(line, i) == ':':
                        return Obj(len=4, token="bar_dbl_repeat")
                    return Obj(len=3, token="bar_right_repeat")
                return Obj(len=2, token="bar_right_repeat")
            return Obj(len=1, warn="Unknown bar symbol")
        if c == '[':
            i += 1
            if at(line, i) == '|':
                i += 1
                c = at(line, i)
                if c == ':':
                    return Obj(len=3, token="bar_left_repeat")
                if c == ']':
                    return Obj(len=3, token="bar_invisible")
                return Obj(len=2, token="bar_thick_thin")
            c = at(line, i)
            if (c is not None and '1' <= c <= '9') or c == '"':
                return Obj(len=1, token="bar_invisible")
            return Obj(len=0)
        if c == '|':
            i += 1
            c = at(line, i)
            if c == ']':
                return Obj(len=2, token="bar_thin_thick")
            if c == '|':
                i += 1
                if at(line, i) == ':':
                    return Obj(len=3, token="bar_left_repeat")
                return Obj(len=2, token="bar_thin_thin")
            if c == ':':
                colons = 0
                while at(line, i + colons) == ':':
                    colons += 1
                return Obj(len=1 + colons, token="bar_left_repeat")
            return Obj(len=1, token="bar_thin")
        return Obj(len=0)

    # -- generic helpers --------------------------------------------------
    def get_token_of(self, s, legal_chars):
        for i in range(len(s)):
            if s[i] not in legal_chars:
                return Obj(len=i, token=s[0:i])
        return Obj(len=len(s), token=s)

    def get_token(self, s, start, end):
        i = start
        while i < end and not is_white_space(at(s, i)):
            i += 1
        return substring(s, start, i)

    def is_match(self, s, match):
        i = self.skip_white_space(s)
        if _finished(s, i):
            return 0
        if s[i:].startswith(match):
            return i + len(match)
        return 0

    def get_pitch_from_tokens(self, tokens):
        ret = Obj()
        pitches = {'A': 5, 'B': 6, 'C': 0, 'D': 1, 'E': 2, 'F': 3, 'G': 4, 'a': 12, 'b': 13, 'c': 7, 'd': 8, 'e': 9, 'f': 10, 'g': 11}
        position = pitches.get(tokens[0].token)
        if position is None:
            return Obj(warn="Pitch expected. Found: " + js_str(tokens[0].token))
        ret.position = position
        tokens.pop(0)
        while len(tokens):
            t = tokens[0].token
            if t == ',':
                ret.position -= 7
                tokens.pop(0)
            elif t == "'":
                ret.position += 7
                tokens.pop(0)
            else:
                return ret
        return ret

    def get_key_accidentals2(self, tokens):
        accs = None
        # find and strip off all accidentals in the token list
        while len(tokens) > 0:
            if tokens[0].token == '^':
                acc = 'sharp'
                tokens.pop(0)
                if len(tokens) == 0:
                    return Obj(accs=accs, warn='Expected note name after ' + acc)
                t = tokens[0].token
                if t == '^':
                    acc = 'dblsharp'
                    tokens.pop(0)
                elif t == '/':
                    acc = 'quartersharp'
                    tokens.pop(0)
            elif tokens[0].token == '=':
                acc = 'natural'
                tokens.pop(0)
            elif tokens[0].token == '_':
                acc = 'flat'
                tokens.pop(0)
                if len(tokens) == 0:
                    return Obj(accs=accs, warn='Expected note name after ' + acc)
                t = tokens[0].token
                if t == '_':
                    acc = 'dblflat'
                    tokens.pop(0)
                elif t == '/':
                    acc = 'quarterflat'
                    tokens.pop(0)
            else:
                # Not an accidental, we'll assume that a later parse will recognize it.
                return Obj(accs=accs)
            if len(tokens) == 0:
                return Obj(accs=accs, warn='Expected note name after ' + acc)
            first = at(tokens[0].token, 0)
            if first is not None and first in _note_letters:
                if accs is None:
                    accs = []
                accs.append(Obj(acc=acc, note=first))
                if len(tokens[0].token) == 1:
                    tokens.pop(0)
                else:
                    tokens[0].token = tokens[0].token[1:]
            else:
                return Obj(accs=accs, warn='Expected note name after ' + acc + ' Found: ' + js_str(tokens[0].token))
        return Obj(accs=accs)

    def get_key_accidental(self, s):
        i = self.skip_white_space(s)
        if _finished(s, i):
            return Obj(len=0)
        acc = None
        if s[i] in '^_=':
            acc = s[i]
        else:
            return Obj(len=0)
        i += 1
        if _finished(s, i):
            return Obj(len=1, warn='Expected note name after accidental')
        if s[i] in _note_letters:
            return Obj(len=i + 1, token=Obj(acc=_acc_translation.get(acc), note=s[i]))
        if s[i] in '^_/':
            acc += s[i]
            i += 1
            if _finished(s, i):
                return Obj(len=2, warn='Expected note name after accidental')
            if s[i] in _note_letters:
                return Obj(len=i + 1, token=Obj(acc=_acc_translation.get(acc), note=s[i]))
            return Obj(len=2, warn='Expected note name after accidental')
        return Obj(len=1, warn='Expected note name after accidental')

    def get_meat(self, line, start, end):
        # This removes any comments starting with '%' and trims the ends of the string so that there are no leading or trailing spaces.
        comment = line.find('%', start) if start <= len(line) else -1
        if 0 <= comment < end:
            end = comment
        while start < end and at(line, start) in (' ', '\t', '\x12'):
            start += 1
        while start < end and at(line, end - 1) in (' ', '\t', '\x12'):
            end -= 1
        return Obj(start=start, end=end)

    def tokenize(self, line, start, end, alpha_until_white_space=False):
        # this returns all the tokens inside the passed string. A token is a punctuation mark, a string of digits, a string of letters.
        #  Quoted strings are one token.
        #  If there is a minus sign next to a number, then it is included in the number.
        # If there is a period immediately after a number, with a number immediately following, then a float is returned.
        # The type of token is returned: quote, alpha, number, punct
        # If alphaUntilWhiteSpace is true, then the behavior of the alpha token changes.
        ret = self.get_meat(line, start, end)
        start = ret.start
        end = ret.end
        tokens = []
        i = None
        while start < end:
            c = at(line, start)
            if c == '"':
                i = start + 1
                while i < end and line[i] != '"':
                    i += 1
                tokens.append(Obj(type='quote', token=substring(line, start + 1, i), start=start + 1, end=i))
                i += 1
            elif _is_letter(c):
                i = start + 1
                if alpha_until_white_space:
                    while i < end and not is_white_space(line[i]):
                        i += 1
                else:
                    while i < end and _is_letter(line[i]):
                        i += 1
                tokens.append(Obj(type='alpha', token=substring(line, start, i), continueId=_is_number(at(line, i)), start=start, end=i))
                start = i + 1
            elif c == '.' and _is_number(at(line, None if i is None else i + 1)):
                i = start + 1
                while i < end and _is_number(line[i]):
                    i += 1
                float2 = parse_float(substring(line, start, i))
                tokens.append(Obj(type='number', token=substring(line, start, i), intt=None, floatt=float2, continueId=_is_letter(at(line, i)), start=start, end=i))
                start = i + 1
            elif _is_number(c) or (c == '-' and _is_number(at(line, None if i is None else i + 1))):
                i = start + 1
                intt = None
                while i < end and _is_number(line[i]):
                    i += 1
                if at(line, i) == '.' and _is_number(at(line, i + 1)):
                    i += 1
                    while i < end and _is_number(line[i]):
                        i += 1
                else:
                    intt = parse_int(substring(line, start, i))
                floatt = parse_float(substring(line, start, i))
                tokens.append(Obj(type='number', token=substring(line, start, i), intt=intt, floatt=floatt, continueId=_is_letter(at(line, i)), start=start, end=i))
                start = i + 1
            elif c == ' ' or c == '\t':
                i = start + 1
            else:
                tokens.append(Obj(type='punct', token=c, start=start, end=start + 1))
                i = start + 1
            start = i
        return tokens

    def get_voice_token(self, line, start, end):
        # This finds the next token. A token is delimited by a space or an equal sign. If it starts with a quote, then the portion between the quotes is returned.
        i = start
        while (i < end and is_white_space(at(line, i))) or at(line, i) == '=':
            i += 1

        if at(line, i) == '"':
            close = line.find('"', i + 1)
            if close == -1 or close >= end:
                return Obj(len=1, err="Missing close quote")
            return Obj(len=close - start + 1, token=translate_string(substring(line, i + 1, close)))
        ii = i
        while ii < end and not is_white_space(at(line, ii)) and at(line, ii) != '=':
            ii += 1
        return Obj(len=ii - start + 1, token=substring(line, i, ii))

    def get_number(self, line, index):
        num = 0
        while index < len(line):
            c = line[index]
            if '0' <= c <= '9':
                num = num * 10 + (ord(c) - 48)
                index += 1
            else:
                return Obj(num=num, index=index)
        return Obj(num=num, index=index)

    def get_fraction(self, line, index):
        num = 1
        den = 1
        if at(line, index) != '/':
            ret = self.get_number(line, index)
            num = ret.num
            index = ret.index
        if at(line, index) == '/':
            index += 1
            if at(line, index) == '/':
                div = 0.5
                while True:
                    c = at(line, index)
                    index += 1
                    if c != '/':
                        break
                    div = div / 2
                return Obj(value=num * div, index=index - 1)
            i_save = index
            ret2 = self.get_number(line, index)
            if ret2.num == 0 and i_save == index:  # If we didn't use any characters, it is an implied 2
                ret2.num = 2
            if ret2.num != 0:
                den = ret2.num
            index = ret2.index
        return Obj(value=num / den, index=index)

    def the_reverser(self, s):
        for pattern, replace in _the_patterns:
            match = pattern.search(s)
            if match:
                m = _title_number.match(s)
                the_title_number = m.group(1) if m else None
                if the_title_number:
                    s = s.replace(the_title_number + ".", "", 1)
                    s = strip(s)
                length = len(match.group(0))
                result = replace + s[0:len(s) - length]
                if the_title_number:
                    result = the_title_number + ". " + result
                return result
        return s

    def strip_comment(self, s):
        i = s.find('%')
        if i >= 0:
            return strip(s[0:i])
        return strip(s)

    def get_int(self, s):
        # This parses the beginning of the string for a number and returns { value: num, digits: num }
        # If digits is 0, then the string didn't point to a number.
        x = parse_int(s)
        if is_nan(x):
            return Obj(digits=0)
        st = js_str(x)
        i = s.find(st)  # This is to account for leading spaces
        return Obj(value=x, digits=i + len(st))

    def get_float(self, s):
        x = parse_float(s)
        if is_nan(x):
            return Obj(digits=0)
        st = js_str(x)
        i = s.find(st)  # This is to account for leading spaces
        return Obj(value=x, digits=i + len(st))

    def get_measurement(self, tokens):
        if len(tokens) == 0:
            return Obj(used=0)
        used = 1
        num = ''
        if tokens[0].token == '-':
            tokens.pop(0)
            num = '-'
            used += 1
        elif tokens[0].type != 'number':
            return Obj(used=0)
        num += tokens.pop(0).token
        if len(tokens) == 0:
            return Obj(used=1, value=parse_int(num))
        x = tokens.pop(0)
        if x.token == '.':
            used += 1
            if len(tokens) == 0:
                return Obj(used=used, value=parse_int(num))
            if tokens[0].type == 'number':
                x = tokens.pop(0)
                num = num + '.' + x.token
                used += 1
                if len(tokens) == 0:
                    return Obj(used=used, value=parse_float(num))
            x = tokens.pop(0) if tokens else Obj()
        t = x.token
        if t == 'pt':
            return Obj(used=used + 1, value=parse_float(num))
        if t == 'px':
            return Obj(used=used + 1, value=parse_float(num))
        if t == 'cm':
            return Obj(used=used + 1, value=parse_float(num) / 2.54 * 72)
        if t == 'in':
            return Obj(used=used + 1, value=parse_float(num) * 72)
        tokens.insert(0, x)
        return Obj(used=used, value=parse_float(num))

    def get_bracketted_substring(self, line, i, max_error_chars, match_char=None):
        # This extracts the sub string by looking at the first character and searching for that
        # character later in the line (or search for the optional _matchChar).
        # It returns the substring and the number of characters consumed.
        match_char = match_char or at(line, i)
        pos = i + 1
        esc = False
        while pos < len(line) and (esc or line[pos] != match_char):
            esc = line[pos] == '\\'
            pos += 1
        if at(line, pos) == match_char:
            return [pos - i + 1, _subst_in_chord(substring(line, i + 1, pos)), True]
        # we hit the end of line, so we'll just pick an arbitrary num of chars so the line doesn't disappear.
        pos = i + max_error_chars
        if pos > len(line) - 1:
            pos = len(line) - 1
        return [pos - i + 1, _subst_in_chord(substring(line, i + 1, pos)), False]


def _subst_in_chord(s):
    s = s.replace("\\n", "\n")
    s = s.replace('\\"', '"')
    return s
