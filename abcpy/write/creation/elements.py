"""The building blocks of the engraved music.

Ports of the abcjs files in ``write/creation/elements``: AbsoluteElement,
RelativeElement, BeamElem, BraceElem, CrescendoElem, DynamicDecoration,
EndingElem, GlissandoElem, TempoElement, TieElem, TripletElem, VoiceElement and
StaffGroupElement.

Everything that is placed in the SVG is first created as an absolute element:
one unit of graphic information (a clef, a time signature, a bar line, a note
with its accidentals, grace notes, chord symbol, decorations, stem, flags...).
The drawing information is contained in a list of RelativeElements, the
"children" of the absolute element.
"""

from ...jsutil import JSObj, Obj, js_round, js_str, gt, lt, add, truthy, jget
from ..helpers import spacing


def _special_y():
    return Obj(
        tempoHeightAbove=0,
        partHeightAbove=0,
        volumeHeightAbove=0,
        dynamicHeightAbove=0,
        endingHeightAbove=0,
        chordHeightAbove=0,
        lyricHeightAbove=0,

        lyricHeightBelow=0,
        chordHeightBelow=0,
        volumeHeightBelow=0,
        dynamicHeightBelow=0,
    )


_LIMITS = ('tempoHeightAbove', 'partHeightAbove', 'volumeHeightAbove', 'dynamicHeightAbove', 'endingHeightAbove',
           'chordHeightAbove', 'lyricHeightAbove', 'lyricHeightBelow', 'chordHeightBelow', 'volumeHeightBelow',
           'dynamicHeightBelow')


class AbsoluteElement(JSObj):
    # duration - actual musical duration - different from notehead duration in triplets. refer to abcelem to get the notehead duration
    # minspacing - spacing which must be taken on top of the width defined by the duration
    # type is a meta-type for the element. It is not necessary for drawing, but it is useful to make semantic sense of the element.
    def __init__(self, abcelem, duration, minspacing, typ, tune_number, options=None):
        if not options:
            options = {}
        self.tuneNumber = tune_number
        self.abcelem = abcelem
        self.duration = duration
        self.durationClass = options.get('durationClassOveride') if options.get('durationClassOveride') else self.duration
        self.minspacing = minspacing or 0
        self.x = 0
        self.children = []
        self.heads = []
        self.extra = []
        self.extraw = 0
        self.w = 0
        self.right = []
        self.invisible = False
        self.bottom = None
        self.top = None
        self.type = typ
        if jget(abcelem, 'extraClass'):
            self.extraClass = abcelem.extraClass

        # The following are the dimensions of the fixed part of the element.
        # That is, the chord text will be a different height depending on lot of factors, but the 8th flag will always be in the same place.
        self.fixed = Obj(w=0, t=None, b=None)  # there is no x-coord here, because that is set later.

        # these are the heights of all of the vertical elements that can't be placed until the end of the line.
        # the vertical order of elements that are above is: tempo, part, volume/dynamic, ending/chord, lyric
        # the vertical order of elements that are below is: lyric, chord, volume/dynamic
        self.specialY = _special_y()

    def get_fixed_coords(self):
        return Obj(x=self.x, w=self.fixed.w, t=self.fixed.t, b=self.fixed.b)

    def add_extra(self, extra):
        # used for accidentals, multi-measure rest text, left-side decorations, gracenote heads,
        # left annotations, gracenote stems.
        self.fixed.w = _max(self.fixed.w, extra.dx + extra.w)
        if self.fixed.t is None:
            self.fixed.t = extra.top
        else:
            self.fixed.t = _max(self.fixed.t, extra.top)
        if self.fixed.b is None:
            self.fixed.b = extra.bottom
        else:
            self.fixed.b = _min(self.fixed.b, extra.bottom)
        if extra.dx < self.extraw:
            self.extraw = extra.dx
        self.extra.append(extra)
        self._add_child(extra)

    def add_head(self, head):
        if head.dx < self.extraw:
            self.extraw = head.dx
        self.heads.append(head)
        self.add_right(head)

    def add_right(self, right):
        # These are the elements that are the fixed part.
        self.fixed.w = _max(self.fixed.w, right.dx + right.w)
        if right.top is not None:
            if self.fixed.t is None:
                self.fixed.t = right.top
            else:
                self.fixed.t = _max(self.fixed.t, right.top)
        if right.bottom is not None:
            if self.fixed.b is None:
                self.fixed.b = right.bottom
            else:
                self.fixed.b = _min(self.fixed.b, right.bottom)
        if right.dx + right.w > self.w:
            self.w = right.dx + right.w
        self.right.append(right)
        self._add_child(right)

    def add_fixed(self, elem):
        # used for elements that can't move relative to other elements after they have been placed.
        # used for ledger lines, bar numbers, debug msgs, clef, key sigs, time sigs
        self._add_child(elem)

    def add_fixed_x(self, elem):
        # used for elements that can't move horizontally relative to other elements after they have been placed.
        # used for parts, tempo, decorations
        self._add_child(elem)

    def add_centered(self, elem):
        # used for chord labels, lyrics
        half = elem.w / 2
        if -half < self.extraw:
            self.extraw = -half
        self.extra.append(elem)
        if elem.dx + half > self.w:
            self.w = elem.dx + half
        self.right.append(elem)
        self._add_child(elem)

    def set_limit(self, member, child):
        v = getattr(child, member)
        if not v:
            return
        if not self.specialY[member]:
            self.specialY[member] = v
        else:
            self.specialY[member] = _max(self.specialY[member], v)

    def _add_child(self, child):
        # To avoid extra space for chords if there is only a bar number on the clef
        ok_to_push_top = True
        if jget(self.abcelem, 'el_type') == "clef" and child.type == "barNumber":
            ok_to_push_top = False

        child.parent = self
        self.children.append(child)

        if ok_to_push_top:
            self.push_top(child.top)

        self.push_bottom(child.bottom)
        for m in _LIMITS:
            self.set_limit(m, child)

    def push_top(self, top):
        if top is not None:
            if self.top is None:
                self.top = top
            else:
                self.top = _max(top, self.top)

    def push_bottom(self, bottom):
        if bottom is not None:
            if self.bottom is None:
                self.bottom = bottom
            else:
                self.bottom = _min(bottom, self.bottom)

    def set_x(self, x):
        self.x = x
        for c in self.children:
            c.set_x(x)

    def center(self, before, after):
        # Used to center whole rests
        midpoint = (after.x - before.x) / 2 + before.x
        self.x = midpoint - self.w / 2
        for c in self.children:
            c.set_x(self.x)

    def set_hint(self):
        self.hint = True

    def highlight(self, klass=None, color=None):
        from ..interactive.highlight import highlight
        highlight(self, klass, color)

    def unhighlight(self, klass=None, color=None):
        from ..interactive.highlight import unhighlight
        unhighlight(self, klass, color)


def _max(a, b):
    """``Math.max`` with JavaScript NaN/undefined behavior."""
    if a is None or b is None:
        return float('nan')
    if a != a or b != b:
        return float('nan')
    return a if a >= b else b


def _min(a, b):
    if a is None or b is None:
        return float('nan')
    if a != a or b != b:
        return float('nan')
    return a if a <= b else b


class RelativeElement(JSObj):
    def __init__(self, c, dx, w, pitch, opt=None):
        if not isinstance(opt, dict):
            opt = {}  # (abcjs sometimes passes a string here, whose properties are all undefined)
        self.x = 0
        self.c = c  # character or path or string
        self.dx = dx  # relative x position
        self.w = w  # minimum width taken up by this element (can include gratuitous space)
        self.pitch = pitch  # relative y position by pitch
        self.scalex = opt.get('scalex') if truthy(opt.get('scalex')) else 1  # should the character/path be scaled?
        self.scaley = opt.get('scaley') if truthy(opt.get('scaley')) else 1  # should the character/path be scaled?
        self.type = opt.get('type') or "symbol"  # cheap types.
        self.pitch2 = opt.get('pitch2')
        self.linewidth = opt.get('linewidth')
        self.klass = opt.get('klass')
        self.chordPos = opt.get('chordPos')
        self.anchor = opt.get('anchor') if opt.get('anchor') else 'middle'
        self.top = pitch
        if self.pitch2 is not None and gt(self.pitch2, self.top):
            self.top = self.pitch2
        self.bottom = pitch
        if self.pitch2 is not None and lt(self.pitch2, self.bottom):
            self.bottom = self.pitch2
        if truthy(opt.get('thickness')):
            self.top = add(self.top, opt['thickness'] / 2)
            self.bottom = add(self.bottom, -opt['thickness'] / 2)
        if truthy(opt.get('stemHeight')):
            if opt['stemHeight'] > 0:
                self.top = add(self.top, opt['stemHeight'])
            else:
                self.bottom = add(self.bottom, opt['stemHeight'])
        if truthy(opt.get('dim')):
            self.dim = opt['dim']
        if truthy(opt.get('position')):
            self.position = opt['position']
        if opt.get('voiceNumber') is not None:
            self.voiceNumber = opt['voiceNumber']
        self.height = opt.get('height') if truthy(opt.get('height')) else 4  # The +1 is to give a little bit of padding.
        if truthy(opt.get('top')):
            self.top = opt['top']
        if truthy(opt.get('bottom')):
            self.bottom = opt['bottom']
        if truthy(opt.get('name')):
            self.name = opt['name']
        elif self.c:
            self.name = self.c
        else:
            self.name = self.type
        if truthy(opt.get('realWidth')):
            self.realWidth = opt['realWidth']
        else:
            self.realWidth = self.w
        self.centerVertically = False
        t = self.type
        if t == "debug":
            self.chordHeightAbove = self.height
        elif t == "lyric":
            if opt.get('position') and opt['position'] == 'below':
                self.lyricHeightBelow = self.height
            else:
                self.lyricHeightAbove = self.height
        elif t == "chord":
            if opt.get('position') and opt['position'] == 'below':
                self.chordHeightBelow = self.height
            else:
                self.chordHeightAbove = self.height
        elif t == "text":
            if self.pitch is None:
                if opt.get('position') and opt['position'] == 'below':
                    self.chordHeightBelow = self.height
                else:
                    self.chordHeightAbove = self.height
            else:
                self.centerVertically = True
        elif t == "part":
            self.partHeightAbove = self.height

    def get_chord_dim(self):
        if self.type == "debug":
            return None
        if not self.chordHeightAbove and not self.chordHeightBelow:
            return None
        # Chords are centered, annotations are left justified.
        margin = 0
        offset = self.realWidth / 2 if self.type == "chord" else 0
        left = self.x - offset - margin
        right = left + self.realWidth + margin
        return Obj(left=left, right=right)

    def invert_lane(self, total):
        if self.lane is None:
            self.lane = 0
        self.lane = total - self.lane - 1

    def put_chord_in_lane(self, i):
        self.lane = i
        # Add some extra space to account for the character's descenders.
        if self.chordHeightAbove:
            self.chordHeightAbove = (self.height * 1.25) * self.lane
        else:
            self.chordHeightBelow = (self.height * 1.25) * self.lane

    def get_lane(self):
        if self.lane is None:
            return 0
        return self.lane

    def set_x(self, x):
        self.x = x + self.dx


class BeamElem(JSObj):
    # Most elements on the page are related to a particular absolute element -- notes, rests, bars, etc. Beams, however, span multiple elements.
    # This means that beams can't be laid out until the absolute elements are placed.
    def __init__(self, stem_height, typ=None, flat=None, first_element=None):
        # type is "grace", "up", "down", or undefined. flat is used to force flat beams, as it commonly found in the grace notes of bagpipe music.
        self.type = "BeamElem"
        self.isflat = bool(flat)
        self.isgrace = bool(typ and typ == "grace")
        self.forceup = bool(self.isgrace or (typ and typ == "up"))
        self.forcedown = bool(typ and typ == "down")
        self.elems = []  # all the AbsoluteElements that this beam touches. It may include embedded rests.
        self.total = 0
        self.average = 6  # use middle line as start for average.
        self.allrests = True
        self.stemHeight = stem_height
        self.beams = []  # During the layout phase, this will become a list of the beams that need to be drawn.
        if first_element and truthy(first_element.duration):
            self.duration = first_element.duration
            if first_element.startTriplet:
                self.duration *= first_element.tripletMultiplier
            self.duration = js_round(self.duration * 1000) / 1000
        else:
            self.duration = 0

    def set_hint(self):
        self.hint = True

    def running_direction(self, abcelem):
        pitch = abcelem.averagepitch
        if pitch is None:
            return  # don't include elements like spacers in beams
        self.total = js_round(self.total + pitch)
        if not self.count:
            self.count = 0
        self.count += 1

    def add(self, abselem):
        pitch = abselem.abcelem.averagepitch
        if pitch is None:
            return  # don't include elements like spacers in beams
        if not abselem.abcelem.rest:
            self.allrests = False
        abselem.beam = self
        self.elems.append(abselem)
        self.total = js_round(self.total + pitch)
        if self.min is None or abselem.abcelem.minpitch < self.min:
            self.min = abselem.abcelem.minpitch
        if self.max is None or abselem.abcelem.maxpitch > self.max:
            self.max = abselem.abcelem.maxpitch

    def add_beam(self, beam):
        self.beams.append(beam)

    def set_stem_direction(self):
        # Have to figure this out before the notes are placed because placing the notes also places the decorations.
        self.average = _calc_average(self.total, self.count)
        if self.forceup:
            self.stemsUp = True
        elif self.forcedown:
            self.stemsUp = False
        else:
            middle_line = 6  # hardcoded 6 is B
            self.stemsUp = self.average < middle_line  # true is up, false is down;
        self.__dict__.pop('count', None)
        self.total = 0

    def calc_dir(self):
        self.average = _calc_average(self.total, len(self.elems))
        if self.forceup:
            self.stemsUp = True
        elif self.forcedown:
            self.stemsUp = False
        else:
            middle_line = 6  # hardcoded 6 is B
            self.stemsUp = self.average < middle_line  # true is up, false is down;
        d = 'up' if self.stemsUp else 'down'
        for e in self.elems:
            for h in e.heads:
                h.stemDir = d


def _calc_average(total, num_elements):
    if not num_elements:
        return 0
    return total / num_elements


class BraceElem(JSObj):
    def __init__(self, voice, typ):
        self.startVoice = voice
        self.type = typ

    def set_bottom_staff(self, voice):
        self.endVoice = voice
        # If only the start brace has a name then the name belongs to the brace instead of the staff.
        if self.startVoice.header and not self.endVoice.header:
            self.header = self.startVoice.header
            self.startVoice.__dict__.pop('header', None)

    def continuing(self, voice):
        # If the final staff isn't present, then use the last one we saw.
        self.lastContinuedVoice = voice

    def get_width(self):
        return 10  # TODO-PER: right now the drawing function doesn't vary the width at all.

    def is_start_voice(self, voice):
        if self.startVoice and self.startVoice.staff and len(self.startVoice.staff.voices) > 0 and self.startVoice.staff.voices[0] is voice:
            return True
        return False


class CrescendoElem(JSObj):
    def __init__(self, anchor1, anchor2, d, positioning):
        self.type = "CrescendoElem"
        self.anchor1 = anchor1  # must have a .x and a .parent property or be null (means starts at the "beginning" of the line - after keysig)
        self.anchor2 = anchor2  # must have a .x property or be null (means ends at the end of the line)
        self.dir = d  # either "<" or ">"
        if positioning == 'above':
            self.dynamicHeightAbove = 6
        else:
            self.dynamicHeightBelow = 6
        self.pitch = None  # This will be set later


class DynamicDecoration(JSObj):
    def __init__(self, anchor, dec, position):
        self.type = "DynamicDecoration"
        self.anchor = anchor
        self.dec = dec
        if position == 'below':
            self.volumeHeightBelow = 6
        else:
            self.volumeHeightAbove = 6
        self.pitch = None  # This will be set later


class EndingElem(JSObj):
    def __init__(self, text, anchor1, anchor2):
        self.type = "EndingElem"
        self.text = text  # text to be displayed top left
        self.anchor1 = anchor1  # must have a .x property or be null (means starts at the "beginning" of the line - after keysig)
        self.anchor2 = anchor2  # must have a .x property or be null (means ends at the end of the line)
        self.endingHeightAbove = 5
        self.pitch = None  # This will be set later


class GlissandoElem(JSObj):
    def __init__(self, anchor1, anchor2):
        self.type = "GlissandoElem"
        self.anchor1 = anchor1
        self.anchor2 = anchor2


class TempoElement(JSObj):
    def __init__(self, tempo, tune_number, create_note_head):
        self.type = "TempoElement"
        self.tempo = tempo
        self.tempo.type = "tempo"  # TODO-PER: this should be set earlier, in the parser, probably.
        self.tuneNumber = tune_number
        # TODO: can these two properties be merged?
        self.totalHeightInPitches = 6
        self.tempoHeightAbove = self.totalHeightInPitches
        self.pitch = None  # This will be set later
        if self.tempo.duration and not self.tempo.suppressBpm:
            self.note = self.create_note(create_note_head, tempo, tune_number)

    def set_x(self, x):
        self.x = x

    def create_note(self, create_note_head, tempo, tune_number):
        temposcale = 0.75
        duration = tempo.duration[0]  # TODO when multiple durations
        abs_elem = AbsoluteElement(tempo, duration, 1, 'tempo', tune_number)
        # There aren't an infinite number of note values, but we are passed a float, so just in case something is off upstream,
        # merge all of the in between points.
        flag = None
        if duration <= 1 / 32:
            note, flag, dot = "noteheads.quarter", "flags.u32nd", 0
        elif duration <= 1 / 16:
            note, flag, dot = "noteheads.quarter", "flags.u16th", 0
        elif duration <= 3 / 32:
            note, flag, dot = "noteheads.quarter", "flags.u16nd", 1
        elif duration <= 1 / 8:
            note, flag, dot = "noteheads.quarter", "flags.u8th", 0
        elif duration <= 3 / 16:
            note, flag, dot = "noteheads.quarter", "flags.u8th", 1
        elif duration <= 1 / 4:
            note, dot = "noteheads.quarter", 0
        elif duration <= 3 / 8:
            note, dot = "noteheads.quarter", 1
        elif duration <= 1 / 2:
            note, dot = "noteheads.half", 0
        elif duration <= 3 / 4:
            note, dot = "noteheads.half", 1
        elif duration <= 1:
            note, dot = "noteheads.whole", 0
        elif duration <= 1.5:
            note, dot = "noteheads.whole", 1
        elif duration <= 2:
            note, dot = "noteheads.dbl", 0
        else:
            note, dot = "noteheads.dbl", 1

        ret = create_note_head(abs_elem, note, Obj(verticalPos=0),  # This is just temporary: we'll offset the vertical positioning when we get the actual vertical spot.
                               Obj(dir="up", flag=flag, dot=dot, scale=temposcale))
        tempo_note = ret.notehead
        abs_elem.add_head(tempo_note)
        if note != "noteheads.whole" and note != "noteheads.dbl":
            p1 = 1 / 3 * temposcale
            p2 = 5 * temposcale
            dx = tempo_note.dx + tempo_note.w
            width = -0.6
            stem = RelativeElement(None, dx, 0, p1, Obj(type="stem", pitch2=p2, linewidth=width))
            abs_elem.add_right(stem)
        return abs_elem


class TieElem(JSObj):
    def __init__(self, options):
        self.type = "TieElem"
        self.anchor1 = options.get('anchor1')  # must have a .x and a .pitch, and a .parent property or be null (means starts at the "beginning" of the line - after keysig)
        self.anchor2 = options.get('anchor2')  # must have a .x and a .pitch property or be null (means ends at the end of the line)
        if options.get('isGrace'):
            self.isGrace = True
        if options.get('fixedY'):
            self.fixedY = True
        if options.get('stemDir'):
            self.stemDir = options['stemDir']
        if options.get('voiceNumber') is not None:
            self.voiceNumber = options['voiceNumber']
        if options.get('style') is not None:
            self.dotted = True
        self.internalNotes = []

    def add_internal_note(self, note):
        self.internalNotes.append(note)

    def set_end_anchor(self, anchor2):
        self.anchor2 = anchor2  # must have a .x and a .pitch property or be null (means ends at the end of the line)

        # we don't really have enough info to know what the vertical extent is yet and we won't until drawing. This will just give it enough
        # room on either side (we don't even know if the slur will be above yet).
        if self.anchor1:
            self.top = _max(self.anchor1.pitch, self.anchor2.pitch) + 4
            self.bottom = _min(self.anchor1.pitch, self.anchor2.pitch) - 4
        else:
            self.top = self.anchor2.pitch + 4
            self.bottom = self.anchor2.pitch - 4

    # If we encounter a repeat sign, then we don't want to extend either a tie or a slur past it, so these are called to be a limit.
    def set_start_x(self, start_limit_elem):
        self.startLimitX = start_limit_elem

    def set_end_x(self, end_limit_elem):
        self.endLimitX = end_limit_elem

    def set_hint(self):
        self.hint = True

    def calc_tie_direction(self):
        # The rules:
        # 1) If it is in a grace note group, then the direction is always BELOW.
        # 2) If it is in a single voice, then the direction is always OPPOSITE of the stem (or where the stem would have been in the case of whole notes.)
        # 3) If the stem direction is forced (probably because there are two voices on the same line), then the direction is the SAME as the stem direction.
        if self.isGrace:
            self.above = False
        elif self.voiceNumber == 0:
            self.above = True
        elif self.voiceNumber is not None and self.voiceNumber > 0:
            self.above = False
        else:
            if self.anchor1:
                reference_pitch = self.anchor1.pitch
            elif self.anchor2:
                reference_pitch = self.anchor2.pitch
            else:
                reference_pitch = 14  # TODO-PER: this can't really happen normally.
            # Put the arc in the opposite direction of the stem. That isn't always the pitch if one or both of the notes are beamed with something that affects its stem.
            if (self.anchor1 and self.anchor1.stemDir == 'down') and (self.anchor2 and self.anchor2.stemDir == "down"):
                self.above = True
            elif (self.anchor1 and self.anchor1.stemDir == 'up') and (self.anchor2 and self.anchor2.stemDir == "up"):
                self.above = False
            elif self.anchor1 and self.anchor2:
                self.above = reference_pitch >= 6
            elif self.anchor1:
                self.above = self.anchor1.stemDir == "down"
            elif self.anchor2:
                self.above = self.anchor2.stemDir == "down"
            else:
                self.above = reference_pitch >= 6

    # From "standard music notation practice" by Music Publishers' Association:
    # 1) Slurs are placed under the note heads if all stems go up.
    # 2) Slurs are placed over the note heads if all stems go down.
    # 3) If there are both up stems and down stems, prefer placing the slur over.
    # 4) When the staff has opposite stemmed voices, all slurs should be on the stemmed side.
    def calc_slur_direction(self):
        if self.isGrace:
            self.above = False
        elif self.voiceNumber == 0:
            self.above = True
        elif self.voiceNumber is not None and self.voiceNumber > 0:
            self.above = False
        else:
            has_down_stem = False
            if self.anchor1 and self.anchor1.stemDir == "down":
                has_down_stem = True
            if self.anchor2 and self.anchor2.stemDir == "down":
                has_down_stem = True
            for n in self.internalNotes:
                if n.stemDir == "down":
                    has_down_stem = True
            self.above = has_down_stem

    def calc_x(self, line_start_x, line_end_x):
        if self.anchor1:
            self.startX = self.anchor1.x  # The normal case where there is a starting element to attach to.
            if self.anchor1.scalex < 1:  # this is a grace note - don't offset the tie as much.
                self.startX -= 3
        elif self.startLimitX:
            self.startX = self.startLimitX.x + self.startLimitX.w  # if there is no start element, but there is a repeat mark before the start of the line.
        else:
            if self.anchor2:
                self.startX = self.anchor2.x - 20  # There is no element and no repeat mark: make a small arc
            else:
                self.startX = line_start_x  # Don't have any guidance, so extend to beginning of line
        if not self.anchor1 and self.dotted:
            self.startX -= 3  # The arc needs to be long enough to tell that it is dotted.

        if self.anchor2:
            self.endX = self.anchor2.x  # The normal case where there is a starting element to attach to.
        elif self.endLimitX:
            self.endX = self.endLimitX.x  # if there is no start element, but there is a repeat mark before the start of the line.
        else:
            self.endX = line_end_x  # There is no element and no repeat mark: extend to the beginning of the line.

    def calc_tie_y(self):
        # If the tie comes from another line, then one or both anchors will be missing.
        if self.anchor1:
            self.startY = self.anchor1.pitch
        elif self.anchor2:
            self.startY = self.anchor2.pitch
        else:
            self.startY = 14 if self.above else 0

        if self.anchor2:
            self.endY = self.anchor2.pitch
        elif self.anchor1:
            self.endY = self.anchor1.pitch
        else:
            self.endY = 14 if self.above else 0

    # From "standard music notation practice" by Music Publishers' Association:
    # 1) If the anchor note is down stem, the slur points to the note head.
    # 2) If the anchor note is up stem, and the slur is over, then point to middle of stem.
    def calc_slur_y(self):
        if self.anchor1 and self.anchor2:
            if self.above and self.anchor1.stemDir == "up" and not self.fixedY:
                self.startY = (self.anchor1.highestVert + self.anchor1.pitch) / 2
                self.startX += self.anchor1.w / 2  # When going to the middle of the stem, bump the line to the right a little bit to make it look right.
            else:
                self.startY = self.anchor1.pitch

            # If the closing note has an up stem, and it is beamed, and it isn't the first note in the beam, then the beam will get in the way.
            p2 = self.anchor2.parent
            beam_interferes = bool(p2.beam and p2.beam.stemsUp and p2.beam.elems[0] is not p2)
            mid_point = (self.anchor2.highestVert + self.anchor2.pitch) / 2 if self.anchor2.highestVert is not None else float('nan')
            if self.above and self.anchor2.stemDir == "up" and not self.fixedY and not beam_interferes and (mid_point < self.startY):
                self.endY = mid_point
                self.endX += js_round(self.anchor2.w / 2)  # When going to the middle of the stem, bump the line to the right a little bit to make it look right.
            else:
                self.endY = self.anchor2.highestVert if (self.above and beam_interferes) else self.anchor2.pitch

            if self.anchor1.scalex == 1:  # Need a way to tell if this is a grace note - if so then keep the slur as close as possible.
                has_beam1 = bool(self.anchor1.parent.beam)
                has_beam2 = bool(self.anchor2.parent.beam)
                if has_beam1:
                    is_last_in_beam = self.anchor1.parent is self.anchor1.parent.beam.elems[-1]
                    if not is_last_in_beam:
                        if self.above:
                            self.startY = self.anchor1.parent.fixed.t
                        else:
                            self.startY = self.anchor1.parent.fixed.b

                if has_beam2:
                    is_first_in_beam = self.anchor2.parent is self.anchor2.parent.beam.elems[0]
                    if not is_first_in_beam:
                        if self.above:
                            self.endY = self.anchor2.parent.fixed.t
                        else:
                            self.endY = self.anchor2.parent.fixed.b
        elif self.anchor1:
            self.startY = self.endY = self.anchor1.pitch
        elif self.anchor2:
            self.startY = self.endY = self.anchor2.pitch
        else:
            # This is the case where the slur covers the entire line.
            # TODO-PER: figure out where the real top and bottom of the line are.
            self.startY = 14 if self.above else 0
            self.endY = 14 if self.above else 0

    def avoid_collision_above(self):
        # Double check that an interior note in the slur isn't so high that it interferes.
        if self.above:
            max_inner_height = -50
            for n in self.internalNotes:
                if n.highestVert is not None and n.highestVert > max_inner_height:
                    max_inner_height = n.highestVert
            if max_inner_height > self.startY and max_inner_height > self.endY:
                self.startY = self.endY = max_inner_height - 1

    def get_y_bounds(self):
        line_start_x = 10  # TODO-PER: I'm not sure where to get this number from but it probably doesn't matter much
        line_end_x = 1000
        if self.isTie:
            self.calc_tie_direction()
            self.calc_x(line_start_x, line_end_x)
            self.calc_tie_y()
        else:
            self.calc_slur_direction()
            self.calc_x(line_start_x, line_end_x)
            self.calc_slur_y()
        # TODO-PER: It's hard to tell how far the arc is, so I'm just using 3 as the max
        if self.above:
            bottom = _min(self.startY, self.endY)
            top = bottom + 3
        else:
            top = _min(self.startY, self.endY)
            bottom = top - 3
        return [top, bottom]


class TripletElem(JSObj):
    def __init__(self, number, anchor1, options):
        self.type = "TripletElem"
        self.anchor1 = anchor1  # must have a .x and a .parent property or be null (means starts at the "beginning" of the line - after key signature)
        self.number = number
        self.durationClass = ('d' + js_str(js_round(anchor1.parent.durationClass * 1000) / 1000)).replace('.', '-', 1)
        self.middleElems = []  # This is to calculate the highest interior pitch.
        self.flatBeams = options.get('flatBeams')

    def is_closed(self):
        return bool(self.anchor2)

    def middle_note(self, elem):
        self.middleElems.append(elem)

    def set_close_anchor(self, anchor2):
        self.anchor2 = anchor2
        # TODO-PER: This used to be just for beamed triplets but it looks like bracketed triplets need extra room, too.
        if not self.anchor1.parent.beam or self.anchor1.stemDir == 'up':
            self.endingHeightAbove = 4


class VoiceElement(JSObj):
    def __init__(self, voicenumber, voicetotal):
        self.children = []
        self.beams = []
        self.otherchildren = []  # ties, slurs, triplets
        self.w = 0
        self.duplicate = False
        self.voicenumber = voicenumber  # number of the voice on a given stave (not staffgroup)
        self.voicetotal = voicetotal
        self.bottom = 7
        self.top = 7
        self.specialY = _special_y()

    def add_child(self, abs_elem):
        # This is always passed an AbsoluteElement
        if abs_elem.type == 'bar':
            first_item = True
            for c in self.children:
                if "staff-extra" not in c.type and c.type != "tempo":
                    first_item = False
                    break
            if not first_item:
                self.beams.append("bar")
                self.otherchildren.append("bar")
        self.children.append(abs_elem)
        self.set_range(abs_elem)

    def set_limit(self, member, child):
        # Sometimes we get an absolute element in here and sometimes we get some type of relative element.
        # If there is a "specialY" element, then assume it is an absolute element. If that doesn't exist, look for the
        # same members at the top level, because that's where they are in relative elements.
        special_y = child.specialY
        if not special_y:
            special_y = child
        v = getattr(special_y, member)
        if not v:
            return
        if not self.specialY[member]:
            self.specialY[member] = v
        else:
            self.specialY[member] = _max(self.specialY[member], v)

    def adjust_range(self, child):
        if child.bottom is not None:
            self.bottom = _min(self.bottom, child.bottom)
        if child.top is not None:
            self.top = _max(self.top, child.top)

    def set_range(self, child):
        self.adjust_range(child)
        for m in _LIMITS:
            self.set_limit(m, child)

    def add_other(self, child):
        self.otherchildren.append(child)
        self.set_range(child)

    def add_beam(self, child):
        self.beams.append(child)

    def set_width(self, width):
        self.w = width


def calc_height(staff_group):
    # the height is calculated here in a parallel way to the drawing below in hopes that both of these functions will be modified together.
    height = 0
    for v in staff_group.voices:
        staff = v.staff
        if not v.duplicate:
            height += staff.top
            height += -staff.bottom
    return height


class StaffGroupElement(JSObj):
    # StaffGroupElement contains all the elements that go together to make one line of music.
    # That might be multiple staves that are tied together, and it might be multiple voices on one staff.
    def __init__(self, get_text_size):
        self.getTextSize = get_text_size
        self.voices = []
        self.staffs = []
        self.brace = None
        self.bracket = None

    def set_limit(self, member, voice):
        if not voice.specialY[member]:
            return
        if not voice.staff.specialY[member]:
            voice.staff.specialY[member] = voice.specialY[member]
        else:
            voice.staff.specialY[member] = _max(voice.staff.specialY[member], voice.specialY[member])

    def add_voice(self, voice, staffnumber, stafflines):
        voice_num = len(self.voices)
        self.voices.append(voice)
        if staffnumber < len(self.staffs) and self.staffs[staffnumber]:
            self.staffs[staffnumber].voices.append(voice_num)
        else:
            # TODO-PER: how does the min/max change when stafflines is not 5?
            self.staffs.append(Obj(
                top=10,
                bottom=2,
                lines=stafflines,
                voices=[voice_num],
                specialY=_special_y(),
            ))
        voice.staff = self.staffs[staffnumber] if staffnumber < len(self.staffs) else None

    def set_height(self):
        self.height = calc_height(self)

    def set_width(self, width):
        self.w = width
        for v in self.voices:
            v.set_width(width)

    def set_staff_limits(self, voice):
        voice.staff.top = _max(voice.staff.top, voice.top)
        voice.staff.bottom = _min(voice.staff.bottom, voice.bottom)
        for m in _LIMITS:
            self.set_limit(m, voice)
