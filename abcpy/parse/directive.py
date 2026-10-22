"""Handling of ``%%`` directives and ``I:`` fields (port of ``abc_parse_directive.js``)."""

import re

from ..jsutil import Obj, at, last, parse_int, parse_float, is_nan, js_round, js_str, strip, truthy


font_type_can_have_box = {
    'gchordfont': True, 'measurefont': True, 'partsfont': True, 'annotationfont': True,
    'composerfont': True, 'historyfont': True, 'infofont': True, 'subtitlefont': True,
    'textfont': True, 'titlefont': True, 'voicefont': True,
}


def _f(face, weight, style):
    return {'face': face, 'weight': weight, 'style': style, 'decoration': "none"}


_font_translation = {
    "Arial-Italic": _f("Arial", "normal", "italic"),
    "Arial-Bold": _f("Arial", "bold", "normal"),
    "Bookman-Demi": _f("Bookman,serif", "bold", "normal"),
    "Bookman-DemiItalic": _f("Bookman,serif", "bold", "italic"),
    "Bookman-Light": _f("Bookman,serif", "normal", "normal"),
    "Bookman-LightItalic": _f("Bookman,serif", "normal", "italic"),
    "Courier": _f("\"Courier New\"", "normal", "normal"),
    "Courier-Oblique": _f("\"Courier New\"", "normal", "italic"),
    "Courier-Bold": _f("\"Courier New\"", "bold", "normal"),
    "Courier-BoldOblique": _f("\"Courier New\"", "bold", "italic"),
    "AvantGarde-Book": _f("AvantGarde,Arial", "normal", "normal"),
    "AvantGarde-BookOblique": _f("AvantGarde,Arial", "normal", "italic"),
    "AvantGarde-Demi": _f("AvantGarde,Arial", "bold", "normal"),
    "Avant-Garde-Demi": _f("AvantGarde,Arial", "bold", "normal"),
    "AvantGarde-DemiOblique": _f("AvantGarde,Arial", "bold", "italic"),
    "Helvetica-Oblique": _f("Helvetica", "normal", "italic"),
    "Helvetica-Bold": _f("Helvetica", "bold", "normal"),
    "Helvetica-BoldOblique": _f("Helvetica", "bold", "italic"),
    "Helvetica-Narrow": _f("\"Helvetica Narrow\",Helvetica", "normal", "normal"),
    "Helvetica-Narrow-Oblique": _f("\"Helvetica Narrow\",Helvetica", "normal", "italic"),
    "Helvetica-Narrow-Bold": _f("\"Helvetica Narrow\",Helvetica", "bold", "normal"),
    "Helvetica-Narrow-BoldOblique": _f("\"Helvetica Narrow\",Helvetica", "bold", "italic"),
    "Palatino-Roman": _f("Palatino", "normal", "normal"),
    "Palatino-Italic": _f("Palatino", "normal", "italic"),
    "Palatino-Bold": _f("Palatino", "bold", "normal"),
    "Palatino-BoldItalic": _f("Palatino", "bold", "italic"),
    "NewCenturySchlbk-Roman": _f("\"New Century\",serif", "normal", "normal"),
    "NewCenturySchlbk-Italic": _f("\"New Century\",serif", "normal", "italic"),
    "NewCenturySchlbk-Bold": _f("\"New Century\",serif", "bold", "normal"),
    "NewCenturySchlbk-BoldItalic": _f("\"New Century\",serif", "bold", "italic"),
    "Times": _f("\"Times New Roman\"", "normal", "normal"),
    "Times-Roman": _f("\"Times New Roman\"", "normal", "normal"),
    "Times-Narrow": _f("\"Times New Roman\"", "normal", "normal"),
    "Times-Courier": _f("\"Times New Roman\"", "normal", "normal"),
    "Times-New-Roman": _f("\"Times New Roman\"", "normal", "normal"),
    "Times-Italic": _f("\"Times New Roman\"", "normal", "italic"),
    "Times-Italics": _f("\"Times New Roman\"", "normal", "italic"),
    "Times-Bold": _f("\"Times New Roman\"", "bold", "normal"),
    "Times-BoldItalic": _f("\"Times New Roman\"", "bold", "italic"),
    "ZapfChancery-MediumItalic": _f("\"Zapf Chancery\",cursive,serif", "normal", "normal"),
}


def font_translation(font_face):
    """Translate a Postscript font name into a web alternative (or None)."""
    f = _font_translation.get(font_face)
    return Obj(f) if f else None


# starts at 35
drum_names = [
    "acoustic-bass-drum", "bass-drum-1", "side-stick", "acoustic-snare", "hand-clap",
    "electric-snare", "low-floor-tom", "closed-hi-hat", "high-floor-tom", "pedal-hi-hat",
    "low-tom", "open-hi-hat", "low-mid-tom", "hi-mid-tom", "crash-cymbal-1", "high-tom",
    "ride-cymbal-1", "chinese-cymbal", "ride-bell", "tambourine", "splash-cymbal", "cowbell",
    "crash-cymbal-2", "vibraslap", "ride-cymbal-2", "hi-bongo", "low-bongo", "mute-hi-conga",
    "open-hi-conga", "low-conga", "high-timbale", "low-timbale", "high-agogo", "low-agogo",
    "cabasa", "maracas", "short-whistle", "long-whistle", "short-guiro", "long-guiro",
    "claves", "hi-wood-block", "low-wood-block", "mute-cuica", "open-cuica",
    "mute-triangle", "open-triangle",
]


def interpret_perc_map(rest_of_string):
    tokens = re.split(r"\s+", rest_of_string)  # Allow multiple spaces.
    if len(tokens) != 2 and len(tokens) != 3:
        return Obj(error='Expected parameters "abc-note", "drum-sound", and optionally "note-head"')
    key = tokens[0]
    # The percussion sound can either be a MIDI number or a drum name. If it is not a number then check for a name.
    pitch = parse_int(tokens[1], 10)
    if (is_nan(pitch) or pitch < 35 or pitch > 81) and tokens[1]:
        low = tokens[1].lower()
        pitch = (drum_names.index(low) if low in drum_names else -1) + 35
    if is_nan(pitch) or pitch < 35 or pitch > 81:
        return Obj(error='Expected drum name, received "' + tokens[1] + '"')
    value = Obj(sound=pitch)
    if len(tokens) == 3:
        value.noteHead = tokens[2]
    return Obj(key=key, value=value)


midi_cmd_param0 = [
    "nobarlines", "barlines", "beataccents", "nobeataccents", "droneon", "droneoff",
    "drumon", "drumoff", "fermatafixed", "fermataproportional", "gchordon", "gchordoff",
    "controlcombo", "temperamentnormal", "noportamento",
]
midi_cmd_param1_string = ["gchord", "ptstress", "beatstring"]
midi_cmd_param1_integer = [
    "bassvol", "chordvol", "c", "channel", "beatmod", "deltaloudness", "drumbars",
    "gracedivider", "makechordchannels", "randomchordattack", "chordattack", "stressmodel",
    "transpose", "rtranspose", "vol", "volinc", "gchordbars",
]
midi_cmd_param1_integer1_optional_integer = ["program"]
midi_cmd_param2_integer = ["ratio", "snt", "bendvelocity", "pitchbend", "control", "temperamentlinear"]
midi_cmd_param4_integer = ["beat"]
midi_cmd_param5_integer = ["drone"]
midi_cmd_param1_string1_integer = ["portamento"]
midi_cmd_param_fraction = ["expand", "grace", "trim"]
midi_cmd_param1_string_variable_integers = ["drum", "chordname"]
midi_cmd_param1_integer1_optional_string = ["bassprog", "chordprog"]

position_choices = ['auto', 'above', 'below', 'hidden']


def _parse_stretch_last(tokens):
    if len(tokens) == 0:
        return Obj(value=1)  # if there is no value then the presence of this is the same as "true"
    elif len(tokens) == 1:
        if tokens[0].type == "number":
            if tokens[0].floatt >= 0 or tokens[0].floatt <= 1:
                return Obj(value=tokens[0].floatt)
        elif tokens[0].token == 'false':
            return Obj(value=0)
        elif tokens[0].token == 'true':
            return Obj(value=1)
    return Obj(error="Directive stretchlast requires zero or one parameter: false, true, or number between 0 and 1 (received " + js_str(tokens[0].token) + ')')


class ParseDirective:
    def __init__(self):
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
        self._initialize_fonts()

    def _initialize_fonts(self):
        mv = self.multiline_vars
        tune = self.tune

        def font(face, size, weight, style):
            return Obj(face=face, size=size, weight=weight, style=style, decoration="none")

        mv.annotationfont = font("Helvetica", 12, "normal", "normal")
        mv.gchordfont = font("Helvetica", 12, "normal", "normal")
        mv.historyfont = font("\"Times New Roman\"", 16, "normal", "normal")
        mv.infofont = font("\"Times New Roman\"", 14, "normal", "italic")
        mv.measurefont = font("\"Times New Roman\"", 14, "normal", "italic")
        mv.partsfont = font("\"Times New Roman\"", 15, "normal", "normal")
        mv.repeatfont = font("\"Times New Roman\"", 13, "normal", "normal")
        mv.textfont = font("\"Times New Roman\"", 16, "normal", "normal")
        mv.tripletfont = font("Times", 11, "normal", "italic")
        mv.vocalfont = font("\"Times New Roman\"", 13, "bold", "normal")
        mv.wordsfont = font("\"Times New Roman\"", 16, "normal", "normal")

        # These fonts are global for the entire tune.
        tune.formatting.composerfont = font("\"Times New Roman\"", 14, "normal", "italic")
        tune.formatting.subtitlefont = font("\"Times New Roman\"", 16, "normal", "normal")
        tune.formatting.tempofont = font("\"Times New Roman\"", 15, "bold", "normal")
        tune.formatting.titlefont = font("\"Times New Roman\"", 20, "normal", "normal")
        tune.formatting.footerfont = font("\"Times New Roman\"", 12, "normal", "normal")
        tune.formatting.headerfont = font("\"Times New Roman\"", 12, "normal", "normal")
        tune.formatting.voicefont = font("\"Times New Roman\"", 13, "bold", "normal")
        tune.formatting.tablabelfont = font("\"Trebuchet MS\"", 16, "normal", "normal")
        tune.formatting.tabnumberfont = font("\"Arial\"", 11, "normal", "normal")
        tune.formatting.tabgracefont = font("\"Arial\"", 8, "normal", "normal")

        # these are the default fonts for these element types. In the printer, these fonts might change as the tune progresses.
        for name in ("annotationfont", "gchordfont", "historyfont", "infofont", "measurefont", "partsfont",
                     "repeatfont", "textfont", "tripletfont", "vocalfont", "wordsfont"):
            tune.formatting[name] = mv[name]

    # -- fonts -----------------------------------------------------------------
    def get_font_parameter(self, tokens, current_setting, s, position, cmd):
        # Every font parameter has the following format:
        # <face> <utf8> <size> <modifiers> <box>
        warn = self.warn

        def process_number_only():
            size = parse_int(tokens[0].token)
            tokens.pop(0)
            if not current_setting:
                warn("Can't set just the size of the font since there is no default value.", s, position)
                return Obj(face="\"Times New Roman\"", weight="normal", style="normal", decoration="none", size=size)
            if len(tokens) == 0:
                return Obj(face=current_setting.face, weight=current_setting.weight, style=current_setting.style, decoration=current_setting.decoration, size=size)
            if len(tokens) == 1 and tokens[0].token == "box" and font_type_can_have_box.get(cmd):
                return Obj(face=current_setting.face, weight=current_setting.weight, style=current_setting.style, decoration=current_setting.decoration, size=size, box=True)
            warn("Extra parameters in font definition.", s, position)
            return Obj(face=current_setting.face, weight=current_setting.weight, style=current_setting.style, decoration=current_setting.decoration, size=size)

        # format 1: asterisk and number only
        if tokens[0].token == '*':
            tokens.pop(0)
            if tokens and tokens[0].type == 'number':
                return process_number_only()
            else:
                warn("Expected font size number after *.", s, position)

        # format 2: number only
        if tokens and tokens[0].type == 'number':
            return process_number_only()

        # format 3: whole definition
        face = []
        size = None
        weight = "normal"
        style = "normal"
        decoration = "none"
        box = False
        state = 'face'
        hyphen_last = False
        while len(tokens):
            curr_token = tokens.pop(0)
            word = curr_token.token.lower()
            if state == 'face':
                if hyphen_last or (word != 'utf' and curr_token.type != 'number' and word != "bold" and word != "italic" and word != "underline" and word != "box"):
                    if len(face) > 0 and curr_token.token == '-':
                        hyphen_last = True
                        face[-1] = face[-1] + curr_token.token
                    else:
                        if hyphen_last:
                            hyphen_last = False
                            face[-1] = face[-1] + curr_token.token
                        else:
                            face.append(curr_token.token)
                else:
                    if curr_token.type == 'number':
                        if truthy(size):
                            warn("Font size specified twice in font definition.", s, position)
                        else:
                            size = curr_token.token
                        state = 'modifier'
                    elif word == "bold":
                        weight = "bold"
                    elif word == "italic":
                        style = "italic"
                    elif word == "underline":
                        decoration = "underline"
                    elif word == "box":
                        if font_type_can_have_box.get(cmd):
                            box = True
                        else:
                            warn("This font style doesn't support \"box\"", s, position)
                        state = "finished"
                    elif word == "utf":
                        if tokens:
                            curr_token = tokens.pop(0)  # this gets rid of the "8" after "utf"
                        state = "size"
                    else:
                        warn("Unknown parameter " + curr_token.token + " in font definition.", s, position)
            elif state == "size":
                if curr_token.type == 'number':
                    if truthy(size):
                        warn("Font size specified twice in font definition.", s, position)
                    else:
                        size = curr_token.token
                else:
                    warn("Expected font size in font definition.", s, position)
                state = 'modifier'
            elif state == "modifier":
                if word == "bold":
                    weight = "bold"
                elif word == "italic":
                    style = "italic"
                elif word == "underline":
                    decoration = "underline"
                elif word == "box":
                    if font_type_can_have_box.get(cmd):
                        box = True
                    else:
                        warn("This font style doesn't support \"box\"", s, position)
                    state = "finished"
                else:
                    warn("Unknown parameter " + curr_token.token + " in font definition.", s, position)
            elif state == "finished":
                warn("Extra characters found after \"box\" in font definition.", s, position)

        if size is None:
            if not current_setting:
                warn("Must specify the size of the font since there is no default value.", s, position)
                size = 12
            else:
                size = current_setting.size
        else:
            size = parse_float(size)

        face = ' '.join(face)
        if face == '':
            if not current_setting:
                warn("Must specify the name of the font since there is no default value.", s, position)
                face = "sans-serif"
            else:
                face = current_setting.face
        ps_font = font_translation(face)
        font = Obj()
        if ps_font:
            font.face = ps_font.face
            font.weight = ps_font.weight
            font.style = ps_font.style
            font.decoration = ps_font.decoration
            font.size = size
            if box:
                font.box = True
            return font
        font.face = face
        font.weight = weight
        font.style = style
        font.decoration = decoration
        font.size = size
        if box:
            font.box = True
        return font

    def _get_changing_font(self, cmd, tokens, s):
        if len(tokens) == 0:
            return "Directive \"" + cmd + "\" requires a font as a parameter."
        mv = self.multiline_vars
        mv[cmd] = self.get_font_parameter(tokens, mv[cmd], s, 0, cmd)
        if mv.is_in_header:  # If the font appears in the header, then it becomes the default font.
            self.tune.formatting[cmd] = mv[cmd]
        return None

    def _get_global_font(self, cmd, tokens, s):
        if len(tokens) == 0:
            return "Directive \"" + cmd + "\" requires a font as a parameter."
        self.tune.formatting[cmd] = self.get_font_parameter(tokens, self.tune.formatting[cmd], s, 0, cmd)
        return None

    def _set_scale(self, cmd, tokens):
        scratch = "".join(js_str(tok.token) for tok in tokens)
        num = parse_float(scratch)
        if is_nan(num) or num == 0:
            return "Directive \"" + cmd + "\" requires a number as a parameter."
        self.tune.formatting.scale = num
        return None

    def _get_required_measurement(self, cmd, tokens):
        points = self.tokenizer.get_measurement(tokens)
        if points.used == 0 or len(tokens) != 0:
            return Obj(error="Directive \"" + cmd + "\" requires a measurement as a parameter.")
        return points.value

    def _one_parameter_measurement(self, cmd, tokens):
        points = self.tokenizer.get_measurement(tokens)
        if points.used == 0 or len(tokens) != 0:
            return "Directive \"" + cmd + "\" requires a measurement as a parameter."
        self.tune.formatting[cmd] = points.value
        return None

    def _add_multiline_var(self, key, cmd, tokens, mn=None, mx=None):
        if len(tokens) != 1 or tokens[0].type != 'number':
            return "Directive \"" + cmd + "\" requires a number as a parameter."
        i = tokens[0].intt
        if mn is not None and i is not None and i < mn:
            return "Directive \"" + cmd + "\" requires a number greater than or equal to " + js_str(mn) + " as a parameter."
        if mx is not None and i is not None and i > mx:
            return "Directive \"" + cmd + "\" requires a number less than or equal to " + js_str(mx) + " as a parameter."
        self.multiline_vars[key] = i
        return None

    def _add_multiline_var_bool(self, key, cmd, tokens):
        if len(tokens) == 1 and (tokens[0].token == 'true' or tokens[0].token == 'false'):
            self.multiline_vars[key] = tokens[0].token == 'true'
            return None
        st = self._add_multiline_var(key, cmd, tokens, 0, 1)
        if st is not None:
            return st
        self.multiline_vars[key] = (self.multiline_vars[key] == 1)
        return None

    def _add_multiline_var_one_param_choice(self, key, cmd, tokens, choices):
        if len(tokens) != 1:
            return "Directive \"" + cmd + "\" requires one of [ " + ", ".join(choices) + " ] as a parameter."
        choice = tokens[0].token
        if choice not in choices:
            return "Directive \"" + cmd + "\" requires one of [ " + ", ".join(choices) + " ] as a parameter."
        self.multiline_vars[key] = choice
        return None

    # -- midi --------------------------------------------------------------
    def _parse_midi_command(self, midi, tune, rest_of_string):
        warn = self.warn
        midi_cmd = midi.pop(0).token
        midi_params = []
        if midi_cmd in midi_cmd_param0:
            # NO PARAMETERS
            if len(midi) != 0:
                warn("Unexpected parameter in MIDI " + midi_cmd, rest_of_string, 0)
        elif midi_cmd in midi_cmd_param1_string:
            # ONE STRING PARAMETER
            if len(midi) != 1:
                warn("Expected one parameter in MIDI " + midi_cmd, rest_of_string, 0)
            else:
                midi_params.append(midi[0].token)
        elif midi_cmd in midi_cmd_param1_integer:
            # ONE INT PARAMETER
            if len(midi) != 1:
                warn("Expected one parameter in MIDI " + midi_cmd, rest_of_string, 0)
            elif midi[0].type != "number":
                warn("Expected one integer parameter in MIDI " + midi_cmd, rest_of_string, 0)
            else:
                midi_params.append(midi[0].intt)
        elif midi_cmd in midi_cmd_param1_integer1_optional_integer:
            # ONE INT PARAMETER, ONE OPTIONAL PARAMETER
            if len(midi) != 1 and len(midi) != 2:
                warn("Expected one or two parameters in MIDI " + midi_cmd, rest_of_string, 0)
            elif midi[0].type != "number":
                warn("Expected integer parameter in MIDI " + midi_cmd, rest_of_string, 0)
            elif len(midi) == 2 and midi[1].type != "number":
                warn("Expected integer parameter in MIDI " + midi_cmd, rest_of_string, 0)
            else:
                midi_params.append(midi[0].intt)
                if len(midi) == 2:
                    midi_params.append(midi[1].intt)
        elif midi_cmd in midi_cmd_param2_integer:
            # TWO INT PARAMETERS
            if len(midi) != 2:
                warn("Expected two parameters in MIDI " + midi_cmd, rest_of_string, 0)
            elif midi[0].type != "number" or midi[1].type != "number":
                warn("Expected two integer parameters in MIDI " + midi_cmd, rest_of_string, 0)
            else:
                midi_params.append(midi[0].intt)
                midi_params.append(midi[1].intt)
        elif midi_cmd in midi_cmd_param1_string1_integer:
            # ONE STRING PARAMETER, ONE INT PARAMETER
            if len(midi) != 2:
                warn("Expected two parameters in MIDI " + midi_cmd, rest_of_string, 0)
            elif midi[0].type != "alpha" or midi[1].type != "number":
                warn("Expected one string and one integer parameters in MIDI " + midi_cmd, rest_of_string, 0)
            else:
                midi_params.append(midi[0].token)
                midi_params.append(midi[1].intt)
        elif midi_cmd == 'drummap':
            # BUILD AN OBJECT OF ABC NOTE => MIDI NOTE
            if len(midi) == 2 and midi[0].type == 'alpha' and midi[1].type == 'number':
                if tune.formatting.midi is None:
                    tune.formatting.midi = Obj()
                if not isinstance(tune.formatting.midi.drummap, dict):
                    # (in abcjs a failed drummap leaves an array here, which then gets string properties)
                    tune.formatting.midi.drummap = Obj()
                tune.formatting.midi.drummap[midi[0].token] = midi[1].intt
                midi_params = tune.formatting.midi.drummap
            elif len(midi) == 3 and midi[0].type == 'punct' and midi[1].type == 'alpha' and midi[2].type == 'number':
                if tune.formatting.midi is None:
                    tune.formatting.midi = Obj()
                if not isinstance(tune.formatting.midi.drummap, dict):
                    # (in abcjs a failed drummap leaves an array here, which then gets string properties)
                    tune.formatting.midi.drummap = Obj()
                tune.formatting.midi.drummap[midi[0].token + midi[1].token] = midi[2].intt
                midi_params = tune.formatting.midi.drummap
            else:
                warn("Expected one note name and one integer parameter in MIDI " + midi_cmd, rest_of_string, 0)
        elif midi_cmd in midi_cmd_param_fraction:
            # ONE FRACTION PARAMETER
            if len(midi) != 3:
                warn("Expected fraction parameter in MIDI " + midi_cmd, rest_of_string, 0)
            elif midi[0].type != "number" or midi[1].token != "/" or midi[2].type != "number":
                warn("Expected fraction parameter in MIDI " + midi_cmd, rest_of_string, 0)
            else:
                midi_params.append(midi[0].intt)
                midi_params.append(midi[2].intt)
        elif midi_cmd in midi_cmd_param4_integer:
            # FOUR INT PARAMETERS
            if len(midi) != 4:
                warn("Expected four parameters in MIDI " + midi_cmd, rest_of_string, 0)
            elif any(m.type != "number" for m in midi[0:4]):
                warn("Expected four integer parameters in MIDI " + midi_cmd, rest_of_string, 0)
            else:
                for m in midi[0:4]:
                    midi_params.append(m.intt)
        elif midi_cmd in midi_cmd_param5_integer:
            # FIVE INT PARAMETERS
            if len(midi) != 5:
                warn("Expected five parameters in MIDI " + midi_cmd, rest_of_string, 0)
            elif any(m.type != "number" for m in midi[0:5]):
                warn("Expected five integer parameters in MIDI " + midi_cmd, rest_of_string, 0)
            else:
                for m in midi[0:5]:
                    midi_params.append(m.intt)
        elif midi_cmd in midi_cmd_param1_string_variable_integers:
            # ONE STRING, VARIABLE INT PARAMETERS
            if len(midi) < 2:
                warn("Expected string parameter and at least one integer parameter in MIDI " + midi_cmd, rest_of_string, 0)
            elif midi[0].type != "alpha":
                warn("Expected string parameter and at least one integer parameter in MIDI " + midi_cmd, rest_of_string, 0)
            else:
                p = midi.pop(0)
                midi_params.append(p.token)
                while len(midi) > 0:
                    p = midi.pop(0)
                    if p.type != "number":
                        warn("Expected integer parameter in MIDI " + midi_cmd, rest_of_string, 0)
                    midi_params.append(p.intt)
        elif midi_cmd in midi_cmd_param1_integer1_optional_string:
            # ONE INT PARAMETER, ONE OPTIONAL string
            if len(midi) != 1 and len(midi) != 2:
                warn("Expected one or two parameters in MIDI " + midi_cmd, rest_of_string, 0)
            elif midi[0].type != "number":
                warn("Expected integer parameter in MIDI " + midi_cmd, rest_of_string, 0)
            elif len(midi) == 2 and midi[1].type != "alpha":
                warn("Expected alpha parameter in MIDI " + midi_cmd, rest_of_string, 0)
            else:
                midi_params.append(midi[0].intt)
                # Currently only bassprog and chordprog with optional octave shifts use this path
                if len(midi) == 2:
                    cmd = midi[1].token
                    if "octave=" in cmd:
                        cmd = parse_int(cmd.replace("octave=", "", 1))
                        if not is_nan(cmd):
                            # Limit range from -1 to 3 octaves
                            if cmd < -1:
                                warn("Expected octave= in MIDI " + midi_cmd + ' to be >= -1 (recv:' + js_str(cmd) + ')')
                                cmd = -1
                            if cmd > 3:
                                warn("Expected octave= in MIDI " + midi_cmd + ' to be <= 3 (recv:' + js_str(cmd) + ')')
                                cmd = 3
                            midi_params.append(cmd)
                        else:
                            warn("Expected octave value in MIDI" + midi_cmd)
                    else:
                        warn("Expected octave= in MIDI" + midi_cmd)

        if self.tune_builder.has_begin_music():
            self.tune_builder.append_element('midi', -1, -1, Obj(cmd=midi_cmd, params=midi_params))
        else:
            if tune.formatting.get('midi') is None:
                tune.formatting['midi'] = Obj()
            tune.formatting['midi'][midi_cmd] = midi_params

    # -- text with font changes ---------------------------------------------
    def parse_font_change_line(self, textstr):
        # We don't want to match two dollar signs, so change those temporarily
        textstr = textstr.replace("$$", "\x03")
        text_parts = textstr.split('$')
        mv = self.multiline_vars
        if len(text_parts) > 1 and mv.setfont:
            textarr = []
            if text_parts[0] != '':  # did the original string start with `$`?
                textarr.append(Obj(text=text_parts[0]))
            for part in text_parts[1:]:
                if at(part, 0) == '0':
                    textarr.append(Obj(text=part[1:].replace("\x03", "$")))
                else:
                    which_font = parse_int(at(part, 0), 10)
                    font = None if is_nan(which_font) else at(mv.setfont, which_font)
                    if font:
                        textarr.append(Obj(font=font, text=part[1:].replace("\x03", "$")))
                    else:
                        textarr[-1].text += '$' + part.replace("\x03", "$")
            return textarr
        return textstr.replace("\x03", "$")

    # -- the main entry point -------------------------------------------
    def add_directive(self, s):
        tokenizer = self.tokenizer
        mv = self.multiline_vars
        tune = self.tune
        tune_builder = self.tune_builder
        warn = self.warn

        tokens = tokenizer.tokenize(s, 0, len(s))  # 3 or more % in a row, or just spaces after %% is just a comment
        if len(tokens) == 0 or tokens[0].type != 'alpha':
            return None
        rest_of_string = s[s.find(tokens[0].token) + len(tokens[0].token):]
        rest_of_string = tokenizer.strip_comment(rest_of_string)
        cmd = tokens.pop(0).token.lower()

        if cmd == "bagpipes":
            tune.formatting.bagpipes = True
        elif cmd == "flatbeams":
            tune.formatting.flatbeams = True
        elif cmd == "jazzchords":
            tune.formatting.jazzchords = True
        elif cmd == "accentAbove":  # never matches since cmd is lower case (same as abcjs)
            tune.formatting.accentAbove = True
        elif cmd == "germanAlphabet":  # never matches since cmd is lower case (same as abcjs)
            tune.formatting.germanAlphabet = True
        elif cmd == "landscape":
            mv.landscape = True
        elif cmd == "papersize":
            mv.papersize = rest_of_string
        elif cmd == "graceslurs":
            if len(tokens) != 1:
                return "Directive graceslurs requires one parameter: 0 or 1"
            if tokens[0].token == '0' or tokens[0].token == 'false':
                tune.formatting.graceSlurs = False
            elif tokens[0].token == '1' or tokens[0].token == 'true':
                tune.formatting.graceSlurs = True
            else:
                return "Directive graceslurs requires one parameter: 0 or 1 (received " + tokens[0].token + ')'
        elif cmd == "lineThickness":  # never matches since cmd is lower case (same as abcjs)
            lt = _parse_stretch_last(tokens)
            if lt.value is not None:
                tune.formatting.lineThickness = lt.value
            if lt.error:
                return lt.error
        elif cmd == "stretchlast":
            sl = _parse_stretch_last(tokens)
            if sl.value is not None:
                tune.formatting.stretchlast = sl.value
            if sl.error:
                return sl.error
        elif cmd == "titlecaps":
            mv.titlecaps = True
        elif cmd == "titleleft":
            tune.formatting.titleleft = True
        elif cmd == "measurebox":
            tune.formatting.measurebox = True
        elif cmd == "vocal":
            return self._add_multiline_var_one_param_choice("vocalPosition", cmd, tokens, position_choices)
        elif cmd == "dynamic":
            return self._add_multiline_var_one_param_choice("dynamicPosition", cmd, tokens, position_choices)
        elif cmd == "gchord":
            return self._add_multiline_var_one_param_choice("chordPosition", cmd, tokens, position_choices)
        elif cmd == "ornament":
            return self._add_multiline_var_one_param_choice("ornamentPosition", cmd, tokens, position_choices)
        elif cmd == "volume":
            return self._add_multiline_var_one_param_choice("volumePosition", cmd, tokens, position_choices)
        elif cmd in ("botmargin", "botspace", "composerspace", "indent", "leftmargin", "linesep",
                     "musicspace", "partsspace", "pageheight", "pagewidth", "rightmargin",
                     "stafftopmargin", "staffsep", "staffwidth", "subtitlespace", "sysstaffsep",
                     "systemsep", "textspace", "titlespace", "topmargin", "topspace", "vocalspace",
                     "wordsspace"):
            return self._one_parameter_measurement(cmd, tokens)
        elif cmd == "voicescale":
            if len(tokens) != 1 or tokens[0].type != 'number':
                return "voicescale requires one float as a parameter"
            voice_scale = tokens.pop(0)
            if mv.currentVoice:
                mv.currentVoice.scale = voice_scale.floatt
                tune_builder.change_voice_scale(mv.currentVoice.scale)
            return None
        elif cmd == "voicecolor":
            if len(tokens) != 1:  # this could either be of type alpha or quote, but it's ok if it is a number
                return "voicecolor requires one string as a parameter"
            voice_color = tokens.pop(0)
            if mv.currentVoice:
                mv.currentVoice.color = voice_color.token
                tune_builder.change_voice_color(mv.currentVoice.color)
            return None
        elif cmd == "vskip":
            m = self._get_required_measurement(cmd, tokens)
            vskip = float('nan') if isinstance(m, dict) else js_round(m)
            tune_builder.add_spacing(vskip)
            return None
        elif cmd == "scale":
            self._set_scale(cmd, tokens)
        elif cmd == "sep":
            if len(tokens) == 0:
                tune_builder.add_separator(14, 14, 85, Obj(startChar=mv.iChar, endChar=mv.iChar + 5))  # If no parameters are given, then there is a default size.
            else:
                points = tokenizer.get_measurement(tokens)
                if points.used == 0:
                    return "Directive \"" + cmd + "\" requires 3 numbers: space above, space below, length of line"
                space_above = points.value

                points = tokenizer.get_measurement(tokens)
                if points.used == 0:
                    return "Directive \"" + cmd + "\" requires 3 numbers: space above, space below, length of line"
                space_below = points.value

                points = tokenizer.get_measurement(tokens)
                if points.used == 0 or len(tokens) != 0:
                    return "Directive \"" + cmd + "\" requires 3 numbers: space above, space below, length of line"
                len_line = points.value
                tune_builder.add_separator(space_above, space_below, len_line, Obj(startChar=mv.iChar, endChar=mv.iChar + len(rest_of_string)))
        elif cmd == "barsperstaff":
            scratch = self._add_multiline_var('barsperstaff', cmd, tokens)
            if scratch is not None:
                return scratch
        elif cmd == "staffnonote":
            # The sense of the boolean is opposite here. "0" means true.
            if len(tokens) != 1:
                return "Directive staffnonote requires one parameter: 0 or 1"
            if tokens[0].token == '0':
                mv.staffnonote = True
            elif tokens[0].token == '1':
                mv.staffnonote = False
            else:
                return "Directive staffnonote requires one parameter: 0 or 1 (received " + tokens[0].token + ')'
        elif cmd == "printtempo":
            scratch = self._add_multiline_var_bool('printTempo', cmd, tokens)
            if scratch is not None:
                return scratch
        elif cmd == "partsbox":
            scratch = self._add_multiline_var_bool('partsBox', cmd, tokens)
            if scratch is not None:
                return scratch
            mv.partsfont.box = mv.partsBox
        elif cmd == "freegchord":
            scratch = self._add_multiline_var_bool('freegchord', cmd, tokens)
            if scratch is not None:
                return scratch
        elif cmd in ("measurenb", "barnumbers"):
            scratch = self._add_multiline_var('barNumbers', cmd, tokens)
            if scratch is not None:
                return scratch
        elif cmd == "setbarnb":
            if len(tokens) != 1 or tokens[0].type != 'number':
                return 'Directive setbarnb requires a number as a parameter.'
            mv.currBarNumber = tune_builder.set_bar_number_immediate(tokens[0].intt)
        elif cmd == "keywarn":
            if len(tokens) != 1 or tokens[0].type != 'number' or (tokens[0].intt != 1 and tokens[0].intt != 0):
                return 'Directive ' + cmd + ' requires 0 or 1 as a parameter.'
            mv[cmd] = tokens[0].intt == 1
        elif cmd == "begintext":
            text_block = ''
            line = tokenizer.next_line()
            while line and line.find('%%endtext') != 0:
                # for text blocks with just white space
                if line.startswith("%%"):
                    the_line = line[2:]
                    the_line = strip(the_line) + "\n"
                    text_block += the_line
                else:
                    text_block += strip(line) + "\n"
                line = tokenizer.next_line()
            tune_builder.add_text(text_block, Obj(startChar=mv.iChar, endChar=mv.iChar + len(text_block) + 7))
        elif cmd == "continueall":
            mv.continueall = True
        elif cmd == "beginps":
            line = tokenizer.next_line()
            while line and line.find('%%endps') != 0:
                # (abcjs never advances `line` here and so loops forever; we advance it.)
                line = tokenizer.next_line()
            warn("Postscript ignored", s, 0)
        elif cmd == "deco":
            if len(rest_of_string) > 0:
                sp = rest_of_string.find(' ')
                mv.ignoredDecorations.append(rest_of_string[0:sp] if sp >= 0 else "")
            warn("Decoration redefinition ignored", s, 0)
        elif cmd == "text":
            textstr = tokenizer.translate_string(rest_of_string)
            tune_builder.add_text(self.parse_font_change_line(textstr), Obj(startChar=mv.iChar, endChar=mv.iChar + len(rest_of_string) + 7))
        elif cmd == "center":
            centerstr = tokenizer.translate_string(rest_of_string)
            tune_builder.add_centered(self.parse_font_change_line(centerstr))
        elif cmd == "font":
            # don't need to do anything for this; it is a useless directive
            pass
        elif cmd == "setfont":
            sf_tokens = tokenizer.tokenize(rest_of_string, 0, len(rest_of_string))
            if len(sf_tokens) >= 4:
                if sf_tokens[0].token == '-' and sf_tokens[1].type == 'number':
                    sf_num = parse_int(sf_tokens[1].token)
                    if 1 <= sf_num <= 9:
                        if not mv.setfont:
                            mv.setfont = []
                        sf_tokens.pop(0)
                        sf_tokens.pop(0)
                        while len(mv.setfont) <= sf_num:
                            mv.setfont.append(None)
                        mv.setfont[sf_num] = self.get_font_parameter(sf_tokens, mv.setfont[sf_num], s, 0, 'setfont')
        elif cmd in ("gchordfont", "partsfont", "tripletfont", "vocalfont", "textfont", "annotationfont",
                     "historyfont", "infofont", "measurefont", "repeatfont", "wordsfont"):
            return self._get_changing_font(cmd, tokens, s)
        elif cmd in ("composerfont", "subtitlefont", "tempofont", "titlefont", "voicefont", "footerfont", "headerfont"):
            return self._get_global_font(cmd, tokens, s)
        elif cmd in ("barlabelfont", "barnumberfont", "barnumfont"):
            return self._get_changing_font("measurefont", tokens, s)
        elif cmd in ("staves", "score"):
            self._parse_score(cmd, tokens, s)
        elif cmd == "maxstaves":
            n_staves = tokenizer.get_int(rest_of_string)
            if n_staves.digits == 0:
                warn("Expected number of staves in maxstaves")
            else:
                if n_staves.value > 0:
                    tune.formatting.maxStaves = n_staves.value
        elif cmd == "newpage":
            pg_num = tokenizer.get_int(rest_of_string)
            tune_builder.add_new_page(-1 if pg_num.digits == 0 else pg_num.value)
        elif cmd == "abc":
            arr = rest_of_string.split(' ')
            if arr[0] in ("-copyright", "-creator", "-edited-by", "-version", "-charset"):
                sub_cmd = arr.pop(0)
                tune_builder.add_meta_text(cmd + sub_cmd, ' '.join(arr), Obj(startChar=mv.iChar, endChar=mv.iChar + len(rest_of_string) + 5))
            else:
                return "Unknown directive: " + cmd + arr[0]
        elif cmd in ("header", "footer"):
            footer_str = tokenizer.get_meat(rest_of_string, 0, len(rest_of_string))
            footer_str = rest_of_string[footer_str.start:footer_str.end]
            if at(footer_str, 0) == '"' and at(footer_str, len(footer_str) - 1) == '"':
                footer_str = footer_str[1:len(footer_str) - 1]
            footer_arr = footer_str.split('\t')
            if len(footer_arr) == 1:
                footer = Obj(left="", center=footer_arr[0], right="")
            elif len(footer_arr) == 2:
                footer = Obj(left=footer_arr[0], center=footer_arr[1], right="")
            else:
                footer = Obj(left=footer_arr[0], center=footer_arr[1], right=footer_arr[2])
            if len(footer_arr) > 3:
                warn("Too many tabs in " + cmd + ": " + js_str(len(footer_arr)) + " found.", rest_of_string, 0)
            tune_builder.add_meta_text_obj(cmd, footer, Obj(startChar=mv.iChar, endChar=mv.iChar + len(s)))
        elif cmd == "midi":
            midi = tokenizer.tokenize(rest_of_string, 0, len(rest_of_string), True)
            if len(midi) > 0 and midi[0].token == '=':
                midi.pop(0)
            if len(midi) == 0:
                warn("Expected midi command", rest_of_string, 0)
            else:
                self._parse_midi_command(midi, tune, rest_of_string)
        elif cmd == "percmap":
            percmap = interpret_perc_map(rest_of_string)
            if percmap.error:
                warn(percmap.error, s, 8)
            else:
                if not tune.formatting.percmap:
                    tune.formatting.percmap = Obj()
                tune.formatting.percmap[percmap.key] = percmap.value
        elif cmd == "visualtranspose":
            half_steps = tokenizer.get_int(rest_of_string)
            if half_steps.digits == 0:
                warn("Expected number of half steps in visualTranspose")
            else:
                mv.globalTranspose = half_steps.value
        elif cmd in ("map", "playtempo", "auquality", "continuous", "nobarcheck"):
            tune.formatting[cmd] = rest_of_string
        else:
            return "Unknown directive: " + cmd
        return None

    def _parse_score(self, cmd, tokens, s):
        mv = self.multiline_vars
        warn = self.warn
        mv.score_is_present = True

        def add_voice(vid, new_staff, bracket, brace, continue_bar):
            if new_staff or len(mv.staves) == 0:
                mv.staves.append(Obj(index=len(mv.staves), numVoices=0))
            staff = last(mv.staves)
            if bracket is not None and staff.bracket is None:
                staff.bracket = bracket
            if brace is not None and staff.brace is None:
                staff.brace = brace
            if continue_bar:
                staff.connectBarLines = 'end'
            if mv.voices.get(vid) is None:
                mv.voices[vid] = Obj(staffNum=staff.index, index=staff.numVoices)
                staff.numVoices += 1

        state = Obj(openParen=False, openBracket=False, openBrace=False, justOpenParen=False,
                    justOpenBracket=False, justOpenBrace=False, continueBar=False, lastVoice=None)

        def add_continue_bar():
            state.continueBar = True
            last_voice = state.lastVoice
            if last_voice:
                ty = 'start'
                if last_voice.staffNum > 0:
                    prev = mv.staves[last_voice.staffNum - 1].connectBarLines
                    if prev == 'start' or prev == 'continue':
                        ty = 'continue'
                mv.staves[last_voice.staffNum].connectBarLines = ty

        while len(tokens):
            t = tokens.pop(0)
            tok = t.token
            if tok == '(':
                if state.openParen:
                    warn("Can't nest parenthesis in %%score", s, t.start)
                else:
                    state.openParen = True
                    state.justOpenParen = True
            elif tok == ')':
                if not state.openParen or state.justOpenParen:
                    warn("Unexpected close parenthesis in %%score", s, t.start)
                else:
                    state.openParen = False
            elif tok == '[':
                if state.openBracket:
                    warn("Can't nest brackets in %%score", s, t.start)
                else:
                    state.openBracket = True
                    state.justOpenBracket = True
            elif tok == ']':
                if not state.openBracket or state.justOpenBracket:
                    warn("Unexpected close bracket in %%score", s, t.start)
                else:
                    state.openBracket = False
                    mv.staves[state.lastVoice.staffNum].bracket = 'end'
            elif tok == '{':
                if state.openBrace:
                    warn("Can't nest braces in %%score", s, t.start)
                else:
                    state.openBrace = True
                    state.justOpenBrace = True
            elif tok == '}':
                if not state.openBrace or state.justOpenBrace:
                    warn("Unexpected close brace in %%score", s, t.start)
                else:
                    state.openBrace = False
                    mv.staves[state.lastVoice.staffNum].brace = 'end'
            elif tok == '|':
                add_continue_bar()
            else:
                vc = ""
                while t is not None and (t.type == 'alpha' or t.type == 'number'):
                    vc += t.token
                    if t.continueId:
                        t = tokens.pop(0) if tokens else None
                    else:
                        break
                new_staff = not state.openParen or state.justOpenParen
                bracket = 'start' if state.justOpenBracket else ('continue' if state.openBracket else None)
                brace = 'start' if state.justOpenBrace else ('continue' if state.openBrace else None)
                add_voice(vc, new_staff, bracket, brace, state.continueBar)
                state.justOpenParen = False
                state.justOpenBracket = False
                state.justOpenBrace = False
                state.continueBar = False
                state.lastVoice = mv.voices.get(vc)
                if cmd == 'staves':
                    add_continue_bar()

    def global_formatting(self, format_hash):
        warn = self.warn
        tune = self.tune
        mv = self.multiline_vars
        for cmd in format_hash:
            v = format_hash[cmd]
            value = js_str(v) if not isinstance(v, str) else v
            tokens = self.tokenizer.tokenize(value, 0, len(value))
            if cmd in ("titlefont", "gchordfont", "composerfont", "footerfont", "headerfont", "historyfont",
                       "infofont", "measurefont", "partsfont", "repeatfont", "subtitlefont", "tempofont",
                       "textfont", "voicefont", "tripletfont", "vocalfont", "wordsfont", "annotationfont",
                       "tablabelfont", "tabnumberfont", "tabgracefont"):
                self._get_changing_font(cmd, tokens, value)
            elif cmd == "scale":
                self._set_scale(cmd, tokens)
            elif cmd == "partsbox":
                scratch = self._add_multiline_var_bool('partsBox', cmd, tokens)
                if scratch is not None:
                    warn(scratch)
                mv.partsfont.box = mv.partsBox
            elif cmd == "freegchord":
                scratch = self._add_multiline_var_bool('freegchord', cmd, tokens)
                if scratch is not None:
                    warn(scratch)
            elif cmd == "fontboxpadding":
                if len(tokens) != 1 or tokens[0].type != 'number':
                    warn("Directive \"" + cmd + "\" requires a number as a parameter.")
                tune.formatting.fontboxpadding = tokens[0].floatt
            elif cmd == "stafftopmargin":
                if len(tokens) != 1 or tokens[0].type != 'number':
                    warn("Directive \"" + cmd + "\" requires a number as a parameter.")
                tune.formatting.stafftopmargin = tokens[0].floatt
            elif cmd == "stretchlast":
                sl = _parse_stretch_last(tokens)
                if sl.value is not None:
                    tune.formatting.stretchlast = sl.value
                if sl.error:
                    return sl.error
            else:
                warn("Formatting directive unrecognized: ", cmd, 0)
        return None
