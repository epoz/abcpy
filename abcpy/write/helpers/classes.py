"""Generates the CSS class names put on the SVG elements (port of ``classes.js``)."""

from ...jsutil import Obj, js_set, at, js_str


class Classes:
    def __init__(self, options):
        self.shouldAddClasses = options.get('shouldAddClasses')
        self.reset()

    def reset(self):
        self.lineNumber = None
        self.voiceNumber = None
        self.measureNumber = None
        self.measureTotalPerLine = []
        self.noteNumber = None

    def incr_line(self):
        if self.lineNumber is None:
            self.lineNumber = 0
        else:
            self.lineNumber += 1
        self.voiceNumber = None
        self.measureNumber = None
        self.noteNumber = None

    def incr_voice(self):
        if self.voiceNumber is None:
            self.voiceNumber = 0
        else:
            self.voiceNumber += 1
        self.measureNumber = None
        self.noteNumber = None

    def is_in_measure(self):
        return self.measureNumber is not None

    def new_measure(self):
        if self.measureNumber:
            js_set(self.measureTotalPerLine, self.lineNumber, self.measureNumber)
        self.measureNumber = None
        self.noteNumber = None

    def start_measure(self):
        self.measureNumber = 0
        self.noteNumber = 0

    def incr_measure(self):
        self.measureNumber = (self.measureNumber if self.measureNumber is not None else float('nan')) + 1
        self.noteNumber = 0

    def incr_note(self):
        self.noteNumber = (self.noteNumber if self.noteNumber is not None else float('nan')) + 1

    def measure_total(self):
        total = 0
        for i in range(self.lineNumber or 0):
            v = at(self.measureTotalPerLine, i)
            total += v if v else 0  # This can be null when non-music things are present.
        if self.measureNumber:
            total += self.measureNumber
        return total

    def get_current(self, c=None):
        return Obj(line=self.lineNumber, measure=self.measureNumber, measureTotal=self.measure_total(),
                   voice=self.voiceNumber, note=self.noteNumber)

    def generate(self, c=None):
        if not self.shouldAddClasses:
            return ""
        ret = []
        if c and len(c) > 0:
            ret.append(c)
        if c == "abcjs-tab-number":  # TODO-PER-HACK! straighten out the tablature
            return ' '.join(ret)
        if c == "text instrument-name":
            return "abcjs-text abcjs-instrument-name"
        if self.lineNumber is not None:
            ret.append("l" + js_str(self.lineNumber))
        if self.measureNumber is not None:
            ret.append("m" + js_str(self.measureNumber))
        if self.measureNumber is not None:
            ret.append("mm" + js_str(self.measure_total()))  # measureNumber is null between measures so this is still the test for measureTotal
        if self.voiceNumber is not None:
            ret.append("v" + js_str(self.voiceNumber))
        if c and ('note' in c or 'rest' in c or 'lyric' in c) and self.noteNumber is not None:
            ret.append("n" + js_str(self.noteNumber))
        # add a prefix to all classes that abcjs adds.
        if len(ret) > 0:
            ret = ' '.join(ret).split(' ')  # Some strings are compound classes - that is, specify more than one class in a string.
            for i in range(len(ret)):
                if not ret[i].startswith('abcjs-') and len(ret[i]) > 0:  # if the prefix doesn't already exist and the class is not blank.
                    ret[i] = 'abcjs-' + ret[i]
        return ' '.join(ret)
