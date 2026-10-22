"""Draws the laid out music into the SVG.

Ports of the abcjs files in ``write/draw``.
"""

import math
import re

from ...jsutil import Obj, assign, at, js_round, js_str, js_floor, js_max, js_min, to_fixed, truthy, is_nan
from ..helpers import spacing
from ..helpers.set_class import set_class
from ..creation import glyphs


def round_number(x):
    """``parseFloat(x.toFixed(2))``."""
    if x is None:
        return float('nan')
    if is_nan(x) or (isinstance(x, float) and math.isinf(x)):
        return x
    v = float(to_fixed(x, 2))
    return int(v) if v == int(v) else v


def sprintf(fmt, *args):
    """The subset of sprintf that abcjs uses: ``%f`` prints a number the JavaScript way."""
    out = []
    parts = fmt.split("%f")
    for i, p in enumerate(parts):
        out.append(p)
        if i < len(parts) - 1:
            a = args[i]
            if a is None:
                raise ValueError("Too few arguments.")
            out.append(js_str(a))
    return "".join(out)


# -- group-elements.js -------------------------------------------------------------------

class _Group:
    def __init__(self):
        self.ingroup = False
        self.paper = None
        self.controller = None
        self.path = []
        self.lastM = [0, 0]

    def begin_group(self, paper, controller):
        self.paper = paper
        self.controller = controller
        self.path = []
        self.lastM = [0, 0]
        self.ingroup = True
        self.paper.open_group()

    def is_in_group(self):
        return self.ingroup

    def end_group(self, klass, name, extra_class):
        self.ingroup = False
        self.path = []
        ret = self.paper.close_group()
        if ret:
            c = self.controller.classes.generate(klass)
            if c:
                if extra_class:
                    c += ' ' + extra_class
                ret.set_attribute("class", c)
            ret.set_attribute("fill", self.controller.renderer.foregroundColor)
            ret.set_attribute("stroke", "none")
            ret.set_attribute("data-name", name)
        return ret


# There is just a singleton of this object.
element_group = _Group()


# -- selectables.js -------------------------------------------------------------------------

class Selectables:
    def __init__(self, paper, select_types, tune_number):
        self.elements = []
        self.paper = paper
        self.tuneNumber = tune_number
        self.selectTypes = select_types

    def get_elements(self):
        return self.elements

    def add(self, abs_el, svg_el, is_note_or_tab_number, staff_pos=None):
        if not self.can_select(abs_el):
            return
        if self.selectTypes is None:
            params = Obj(selectable=False)  # This is the old behavior.
            params["data-index"] = len(self.elements)
        else:
            params = Obj(selectable=True, tabindex=0)
            params["data-index"] = len(self.elements)
        self.paper.set_attribute_on_element(svg_el, params)
        sel = Obj(absEl=abs_el, svgEl=svg_el, isDraggable=is_note_or_tab_number)
        if staff_pos is not None:
            sel.staffPos = staff_pos
        self.elements.append(sel)

    def can_select(self, abs_el):
        if self.selectTypes is False:
            return False
        if not abs_el or not abs_el.abcelem:
            return False
        if self.selectTypes is True:
            return True
        if self.selectTypes is None:
            # by default, only notes and tab numbers can be clicked.
            return abs_el.abcelem.el_type == 'note' or abs_el.abcelem.el_type == 'tabNumber'
        return abs_el.abcelem.el_type in self.selectTypes

    def wrap_svg_el(self, abcelem, el):
        abs_el = Obj(tuneNumber=self.tuneNumber, abcelem=abcelem, elemset=[el])
        self.add(abs_el, el, False)


# -- print helpers --------------------------------------------------------------------------

def print_path(renderer, attrs, params=None):
    return renderer.paper.path(attrs)


def print_stem(renderer, x, dx, y1, y2, klass, name):
    if dx < 0 or y1 < y2:  # correct path "handedness" for intersection with other elements
        tmp = round_number(y2)
        y2 = round_number(y1)
        y1 = tmp
    else:
        y1 = round_number(y1)
        y2 = round_number(y2)
    x = round_number(x)
    x2 = round_number(x + dx)
    if renderer.firefox:
        x += dx / 2  # Because the x coordinate is the edge of where the line goes but the width widens from the middle.
        attr = Obj(x1=x, x2=x, y1=y1, y2=y2, stroke=renderer.foregroundColor)
        attr['stroke-width'] = abs(dx)
        if klass:
            attr['class'] = klass
        if name:
            attr['data-name'] = name
        return renderer.paper.line_to_back(attr)
    path_array = [["M", x, y1], ["L", x, y2], ["L", x2, y2], ["L", x2, y1], ["z"]]
    attr = Obj(path="".join(" ".join(js_str(v) for v in p) for p in path_array))
    if klass:
        attr['class'] = klass
    if name:
        attr['data-name'] = name
    if not element_group.is_in_group():
        attr.stroke = "none"
        attr.fill = renderer.foregroundColor
    return renderer.paper.path_to_back(attr)


def print_line(renderer, x1, x2, y, klass, name, dy):
    fill = renderer.foregroundColor
    x1 = round_number(x1)
    x2 = round_number(x2)
    y1 = round_number(y - dy)
    y2 = round_number(y + dy)
    if renderer.firefox:
        y += dy / 2
        attr = Obj(x1=x1, x2=x2, y1=y, y2=y, stroke=renderer.foregroundColor)
        attr['stroke-width'] = abs(dy * 2)
        if klass:
            attr['class'] = klass
        if name:
            attr['data-name'] = name
        return renderer.paper.line_to_back(attr)

    path_string = sprintf("M %f %f L %f %f L %f %f L %f %f z", x1, y1, x2, y1, x2, y2, x1, y2)
    options = Obj(path=path_string, stroke="none", fill=fill)
    if name:
        options['data-name'] = name
    if klass:
        options['class'] = klass
    return renderer.paper.path_to_back(options)


def print_staff_line(renderer, x1, x2, pitch, klass, name, dy):
    y = renderer.calc_y(pitch)
    return print_line(renderer, x1, x2, y, klass, name, dy)


def print_staff(renderer, startx, endx, num_lines, line_pitch, dy):
    klass = "abcjs-top-line"
    pitch = 2
    if line_pitch:
        pitch = line_pitch
    renderer.paper.open_group(Obj(prepend=True, klass=renderer.controller.classes.generate("abcjs-staff")))
    # If there is one line, it is the B line. Otherwise, the bottom line is the E line.
    first_y_line = 0
    last_y_line = 0
    if num_lines == 1:
        print_staff_line(renderer, startx, endx, 6, klass, None, dy + renderer.lineThickness)
        first_y_line = renderer.calc_y(10)
        last_y_line = renderer.calc_y(2)
    else:
        i = int(num_lines) - 1 if isinstance(num_lines, (int, float)) and not is_nan(num_lines) else -1
        while i >= 0:
            curpitch = (i + 1) * pitch
            last_y_line = renderer.calc_y(curpitch)
            if first_y_line == 0:
                first_y_line = last_y_line
            print_staff_line(renderer, startx, endx, curpitch, klass, None, dy + renderer.lineThickness)
            klass = None
            i -= 1
    renderer.paper.close_group()
    return [first_y_line, last_y_line]


def print_debug_box(renderer, attr, comment=None):
    box = renderer.paper.rect_beneath(attr)
    if comment:
        a = Obj(x=0, y=attr['y'] + 7)
        a["text-anchor"] = "start"
        a["font-size"] = "14px"
        a.fill = "rgba(0,0,255,.4)"
        a.stroke = "rgba(0,0,255,.4)"
        renderer.paper.text(comment, a)
    return box


def _kern_symbols(last_symbol, this_symbol, last_symbol_width):
    # This is just some adjustments to make it look better.
    width = last_symbol_width
    if last_symbol == 'f' and this_symbol == 'f':
        width = width * 2 / 3
    if last_symbol == 'p' and this_symbol == 'p':
        width = width * 5 / 6
    if last_symbol == 'f' and this_symbol == 'z':
        width = width * 5 / 8
    return width


def print_symbol(renderer, x, offset, symbol, options):
    # if symbol is a multichar string without a . (as in scripts.staccato) 1 symbol per char is assumed
    if not symbol:
        return None
    if len(symbol) > 1 and "." not in symbol:
        group_class = '' if element_group.is_in_group() else options.get('klass')  # If this is already in a group then don't repeat the classes for the sub-group)
        go = Obj()
        go["data-name"] = options.get('name')
        go.klass = group_class
        renderer.paper.open_group(go)
        dx = 0
        for i in range(len(symbol)):
            s = symbol[i]
            ycorr = glyphs.get_y_corr(s)
            el = glyphs.print_symbol(x + dx, renderer.calc_y(offset + ycorr), s, renderer.paper, Obj(stroke=options.get('stroke'), fill=options.get('fill')))
            if el:
                if i < len(symbol) - 1:
                    dx += _kern_symbols(s, symbol[i + 1], glyphs.get_symbol_width(s))
            else:
                render_text(renderer, Obj(x=x, y=renderer.y, text="no symbol:" + symbol, type="debugfont", klass='debug-msg', anchor='start'), False)
        g = renderer.paper.close_group()
        return g
    ycorr = glyphs.get_y_corr(symbol)
    if element_group.is_in_group():
        a = Obj()
        a["data-name"] = options.get('name')
        el = glyphs.print_symbol(x, renderer.calc_y(offset + ycorr), symbol, renderer.paper, a)
    else:
        a = Obj(klass=options.get('klass'), stroke=options.get('stroke'), fill=options.get('fill'))
        a["data-name"] = options.get('name')
        el = glyphs.print_symbol(x, renderer.calc_y(offset + ycorr), symbol, renderer.paper, a)
    if el:
        return el
    render_text(renderer, Obj(x=x, y=renderer.y, text="no symbol:" + symbol, type="debugfont", klass='debug-msg', anchor='start'), False)
    return None


# -- text.js -------------------------------------------------------------------------------

def render_text(renderer, params, already_in_group=False):
    y = params.y

    # TODO-PER: Probably need to merge the regular text and rich text better. At the least, rich text loses the font box.
    if params.phrases:
        return renderer.paper.rich_text_line(params.phrases, params.x, params.y, params.klass, params.anchor)

    if params.lane:
        lane_margin = params.dim.font.size * 0.25
        y += (params.dim.font.size + lane_margin) * params.lane

    if params.dim:
        h = params.dim
        h.attr['class'] = params.klass
    else:
        h = renderer.controller.getFontAndAttr.calc(params.type, params.klass)
    if params.anchor:
        h.attr["text-anchor"] = params.anchor
    if params['dominant-baseline']:
        h.attr["dominant-baseline"] = params['dominant-baseline']
    h.attr['x'] = params.x
    h.attr['y'] = y
    if not params.centerVertically:
        h.attr['y'] += h.font.size
    if params.type == 'debugfont':
        h.attr['stroke'] = "#ff0000"
    if params.cursor:
        h.attr['cursor'] = params.cursor

    # For free text blocks
    t = params.text if isinstance(params.text, str) else js_str(params.text)
    if params.name == "free-text":
        text = re.sub(r"^[ \t]*\n", ' \n', t, flags=re.M)
    else:
        text = t.replace("\n\n", "\n \n")
    if text.startswith("\n"):
        text = "\xA0\n" + text[1:]

    if h.font.box:
        if not already_in_group:
            go = Obj(klass=h.attr['class'], fill=renderer.foregroundColor)
            go["data-name"] = params.name
            renderer.paper.open_group(go)
        if h.attr["text-anchor"] == "end":
            h.attr['x'] -= h.font.padding
        elif h.attr["text-anchor"] == "start":
            h.attr['x'] += h.font.padding
        h.attr['y'] += h.font.padding
        h.attr.pop('class', None)
    if params.noClass:
        h.attr.pop('class', None)
    h.attr['x'] = round_number(h.attr['x'])
    h.attr['y'] = round_number(h.attr['y'])
    if params.name:
        h.attr["data-name"] = params.name
    elem = renderer.paper.text(text, h.attr)
    if h.font.box:
        size = elem.get_bbox()

        delta = 0
        if h.attr["text-anchor"] == "middle":
            delta = size.width / 2 + h.font.padding
        elif h.attr["text-anchor"] == "end":
            delta = size.width + h.font.padding * 2
        delta_y = 0
        if params.centerVertically:
            delta_y = size.height - h.font.padding
        r = Obj()
        r["data-name"] = "box"
        r.x = js_round(params.x - delta)
        r.y = js_round(y - delta_y)
        r.width = js_round(size.width + h.font.padding * 2)
        r.height = js_round(size.height + h.font.padding * 2)
        renderer.paper.rect(r)
        if not already_in_group:
            elem = renderer.paper.close_group()
    return elem


# -- relative.js -------------------------------------------------------------------------

def draw_relative_element(renderer, params, bartop):
    y = renderer.calc_y(params.pitch)
    t = params.type
    if t == "symbol":
        if params.c is None:
            return None
        klass = "symbol"
        if params.klass:
            klass += " " + params.klass
        params.graphelem = print_symbol(renderer, params.x, params.pitch, params.c, Obj(
            scalex=params.scalex,
            scaley=params.scaley,
            klass=renderer.controller.classes.generate(klass),
            name=params.name))
    elif t == "debug":
        params.graphelem = render_text(renderer, Obj(x=params.x, y=renderer.calc_y(15), text=js_str(params.c), type="debugfont", klass=renderer.controller.classes.generate('debug-msg'), anchor='start', centerVertically=False, dim=params.dim), False)
    elif t == "tabNumber":
        h_anchor = "middle"
        tab_font = "tabnumberfont"
        tab_class = 'abcjs-tab-number'
        if params.isGrace:
            tab_font = "tabgracefont"
            y += 2.5
            tab_class = 'tab-grace'
        params.graphelem = render_text(renderer, Obj(x=params.x, y=y, text=js_str(params.c), type=tab_font, klass=renderer.controller.classes.generate(tab_class), anchor=h_anchor, centerVertically=False, dim=params.dim, cursor='default'), False)
    elif t == "barNumber":
        params.graphelem = render_text(renderer, Obj(x=params.x, y=y, text=js_str(params.c), type="measurefont", klass=renderer.controller.classes.generate('bar-number'), anchor="middle", dim=params.dim, name="bar-number"), True)
    elif t == "lyric":
        params.graphelem = render_text(renderer, Obj(x=params.x, y=y, text=params.c, type="vocalfont", klass=renderer.controller.classes.generate('lyric'), anchor="middle", dim=params.dim, name="lyric"), False)
    elif t == "chord":
        params.graphelem = render_text(renderer, Obj(x=params.x, y=y, text=params.c, type='gchordfont', klass=renderer.controller.classes.generate("chord"), anchor="middle", dim=params.dim, lane=params.get_lane(), name="chord"), False)
    elif t == "decoration":
        # The +6 is to compensate for the placement of text in svg: to be on the same row as symbols, the y-coord needs to compensate for the center line.
        params.graphelem = render_text(renderer, Obj(x=params.x, y=y + 6, text=params.c, type='annotationfont', klass=renderer.controller.classes.generate("annotation"), anchor=params.anchor, centerVertically=True, dim=params.dim), False)
    elif t == "text":
        params.graphelem = render_text(renderer, Obj(x=params.x, y=y, text=params.c, type='annotationfont', klass=renderer.controller.classes.generate("annotation"), anchor="start", centerVertically=params.centerVertically, dim=params.dim, lane=params.get_lane(), name="annotation"), False)
    elif t == "multimeasure-text":
        params.graphelem = render_text(renderer, Obj(x=params.x + params.w / 2, y=y, text=params.c, type='tempofont', klass=renderer.controller.classes.generate("rest"), anchor="middle", centerVertically=False, dim=params.dim), False)
    elif t == "part":
        params.graphelem = render_text(renderer, Obj(x=params.x, y=y, text=params.c, type='partsfont', klass=renderer.controller.classes.generate("part"), anchor="start", dim=params.dim, name=params.c), True)
    elif t == "bar":
        params.graphelem = print_stem(renderer, params.x, params.linewidth + renderer.lineThickness, y, bartop if bartop else renderer.calc_y(params.pitch2), None, "bar")  # bartop can't be 0
    elif t == "stem":
        stem_width = params.linewidth + renderer.lineThickness if params.linewidth > 0 else params.linewidth - renderer.lineThickness
        params.graphelem = print_stem(renderer, params.x, stem_width, y, renderer.calc_y(params.pitch2), 'abcjs-stem', 'stem')
    elif t == "ledger":
        params.graphelem = print_staff_line(renderer, params.x, params.x + params.w, params.pitch, "abcjs-ledger", "ledger", 0.35 + renderer.lineThickness)
    if params.scalex != 1 and params.graphelem:
        _scale_existing_elem(renderer.paper, params.graphelem, params.scalex, params.scaley, params.x, y)
    return params.graphelem


def _scale_existing_elem(paper, elem, scale_x, scale_y, x, y):
    paper.set_attribute_on_element(elem, Obj(
        transform="translate(" + js_str(x) + " " + js_str(y) + ") scale(" + js_str(scale_x) + "," + js_str(scale_y) + ") translate(-" + js_str(x) + " -" + js_str(y) + ")"))


# -- tempo.js -------------------------------------------------------------------------------

def draw_tempo(renderer, params):
    x = params.x
    params.tempo.el_type = "tempo"
    # The text is aligned with extra room for descenders but numbers look like they are a little too high, so bump it a little.
    y = renderer.calc_y(params.pitch) + 2
    if params.tempo.preString:
        text = render_text(renderer, Obj(x=x, y=y, text=params.tempo.preString, type='tempofont', klass='abcjs-tempo', anchor="start", noClass=True, name="pre"), True)
        size = renderer.controller.getTextSize.calc(params.tempo.preString, 'tempofont', 'tempo', text)
        pre_width = size.width
        char_width = pre_width / len(params.tempo.preString)  # Just get some average number to increase the spacing.
        x += pre_width + char_width
    if params.note:
        params.note.set_x(x)
        for child in params.note.children:
            draw_relative_element(renderer, child, x)
        x += (params.note.w + 5)
        s = "= " + js_str(params.tempo.bpm)
        text = render_text(renderer, Obj(x=x, y=y, text=s, type='tempofont', klass='abcjs-tempo', anchor="start", noClass=True, name="beats"))
        size = renderer.controller.getTextSize.calc(s, 'tempofont', 'tempo', text)
        post_width = size.width
        char_width2 = post_width / len(s)  # Just get some average number to increase the spacing.
        x += post_width + char_width2
    if params.tempo.postString:
        render_text(renderer, Obj(x=x, y=y, text=params.tempo.postString, type='tempofont', klass='abcjs-tempo', anchor="start", noClass=True, name="post"), True)


# -- absolute.js -----------------------------------------------------------------------------

def draw_absolute(renderer, params, bartop, selectables, staff_pos):
    if params.invisible:
        return
    is_tempo = len(params.children) > 0 and params.children[0].type == "TempoElement"
    params.elemset = []
    element_group.begin_group(renderer.paper, renderer.controller)
    for child in params.children:
        if child.type == "TempoElement":
            draw_tempo(renderer, child)
        else:
            el = draw_relative_element(renderer, child, bartop)
            if child.type == "symbol" and child.c and 'notehead' in child.c:
                el.set_attribute('class', 'abcjs-notehead')
            if el and child.chordPos and not js_str(child.name).startswith('flags.'):
                klass = el.get_attribute("class")
                if klass:
                    klass = klass + ' abcjs-chord-pos-' + js_str(child.chordPos)
                else:
                    klass = 'abcjs-chord-pos-' + js_str(child.chordPos)
                el.set_attribute('class', klass)
    klass = params.type
    if params.type == 'note' or params.type == 'rest':
        params.counters = renderer.controller.classes.get_current()
        klass += ' d' + js_str(js_round(params.durationClass * 1000) / 1000) if params.durationClass is not None else ' dNaN'
        klass = klass.replace('.', '-')
        if params.abcelem.pitches:
            for p in params.abcelem.pitches:
                klass += ' p' + js_str(p.pitch)
    g = element_group.end_group(klass, params.type, params.extraClass)
    if g:
        # TODO-PER-HACK! This corrects the classes because the tablature is not being created at the right time.
        if params.cloned:
            params.cloned.overrideClasses = g.get_attribute("class") or ""
        if params.overrideClasses:
            cls = (g.get_attribute("class") or "").split()
            typ = cls[0] + ' ' if cls else ''
            g.set_attribute("class", typ + params.overrideClasses)
        if is_tempo:
            params.startChar = params.abcelem.startChar
            params.endChar = params.abcelem.endChar
            selectables.add(params, g, False, staff_pos)
        else:
            params.elemset.append(g)
            is_selectable = params.type == 'note' or params.type == 'tabNumber'
            selectables.add(params, g, is_selectable, staff_pos)
    elif len(params.elemset) > 0:
        selectables.add(params, params.elemset[0], params.type == 'note', staff_pos)
    # If there was no output, then don't add to the selectables. This happens when using the "y" spacer, for instance.

    if params.klass:
        set_class(params.elemset, "mark", "", "#00ff00")
    if params.hint:
        set_class(params.elemset, "abcjs-hint", "", None)
    params.abcelem.abselem = params

    if params.heads and len(params.heads) > 0:
        params.notePositions = []
        for h in params.heads:
            params.notePositions.append(Obj(x=h.x + h.w / 2, y=staff_pos.zero - h.pitch * spacing.STEP))


# -- beam.js --------------------------------------------------------------------------------

def draw_beam(renderer, params, selectables=None):
    if len(params.beams) == 0:
        return None

    path_string = ""
    for beam in params.beams:
        if beam.split:
            slope = (beam.endY - beam.startY) / (beam.endX - beam.startX) if beam.endX != beam.startX else float('nan')
            xes = []
            for j in range(0, len(beam.split), 2):
                xes.append([beam.split[j], at(beam.split, j + 1)])
            for xe in xes:
                y1 = beam.startY + (xe[0] - beam.startX) * slope
                y2 = beam.startY + ((xe[1] if xe[1] is not None else float('nan')) - beam.startX) * slope
                path_string += _beam_draw(renderer, xe[0], y1, xe[1], y2, beam.dy)
        else:
            path_string += _beam_draw(renderer, beam.startX, beam.startY, beam.endX, beam.endY, beam.dy)
    duration_class = ("abcjs-d" + js_str(params.duration)).replace(".", "-")
    klasses = renderer.controller.classes.generate('beam-elem ' + duration_class)
    el = print_path(renderer, Obj([('path', path_string), ('stroke', "none"), ('fill', renderer.foregroundColor), ('class', klasses)]))
    return [el]


def _beam_draw(renderer, start_x, start_y, end_x, end_y, dy):
    # the X coordinates are actual coordinates, but the Y coordinates are in pitches.
    start_y = round_number(renderer.calc_y(start_y))
    end_y = round_number(renderer.calc_y(end_y))
    start_x = round_number(start_x)
    end_x = round_number(end_x)
    start_y2 = round_number(start_y + dy)
    end_y2 = round_number(end_y + dy)
    return ("M" + js_str(start_x) + " " + js_str(start_y) + " L" + js_str(end_x) + " " + js_str(end_y) +
            "L" + js_str(end_x) + " " + js_str(end_y2) + " L" + js_str(start_x) + " " + js_str(start_y2) + "z")


# -- brace.js --------------------------------------------------------------------------------

def draw_brace(renderer, params, selectables):
    # The absoluteY number is the spot where the note on the first ledger line is drawn (i.e. middle C if treble clef)
    # The STEP offset here moves it to the top and bottom lines
    start_y = params.startVoice.staff.absoluteY - spacing.STEP * 10
    if params.endVoice and params.endVoice.staff:
        params.endY = params.endVoice.staff.absoluteY - spacing.STEP * 2
    elif params.lastContinuedVoice and params.lastContinuedVoice.staff:
        params.endY = params.lastContinuedVoice.staff.absoluteY - spacing.STEP * 2
    else:
        params.endY = params.startVoice.staff.absoluteY - spacing.STEP * 2
    return _brace_draw(renderer, params.x, start_y, params.endY, params.type, params.header, selectables)


def _straight_path(renderer, x_left, y_top, y_bottom, typ):
    x_left += spacing.STEP
    x_line_width = spacing.STEP * 0.75
    y_overlap = spacing.STEP * 0.75
    height = y_bottom - y_top
    # Straight line
    path_string = sprintf("M %f %f l %f %f l %f %f l %f %f z",
                          x_left, y_top - y_overlap,  # top left line
                          0, height + y_overlap * 2,  # bottom left line
                          x_line_width, 0,  # bottom right line
                          0, - (height + y_overlap * 2))  # top right line
    # Top arm
    w_curve = spacing.STEP * 2
    h_curve = spacing.STEP
    path_string += sprintf("M %f %f q %f %f %f %f q %f %f %f %f z",
                           x_left + x_line_width, y_top - y_overlap,  # top left arm
                           w_curve * 0.6, h_curve * 0.2,
                           w_curve, -h_curve,  # right point
                           -w_curve * 0.1, h_curve * 0.3,
                           -w_curve, h_curve + spacing.STEP)  # left bottom
    # Bottom arm
    path_string += sprintf("M %f %f q %f %f %f %f q %f %f %f %f z",
                           x_left + x_line_width, y_top + y_overlap + height,  # bottom left arm
                           w_curve * 0.6, -h_curve * 0.2,
                           w_curve, h_curve,  # right point
                           -w_curve * 0.1, -h_curve * 0.3,
                           -w_curve, -h_curve - spacing.STEP)  # left bottom
    a = Obj([('path', path_string), ('stroke', renderer.foregroundColor), ('fill', renderer.foregroundColor), ('class', renderer.controller.classes.generate(typ)), ("data-name", typ)])
    return renderer.paper.path(a)


def _curve(x_left, y_top, x_curve, y_curve):
    return sprintf("M %f %f C %f %f %f %f %f %f C %f %f %f %f %f %f z",
                   x_left + x_curve[0], y_top + y_curve[0],
                   x_left + x_curve[1], y_top + y_curve[1],
                   x_left + x_curve[2], y_top + y_curve[2],
                   x_left + x_curve[3], y_top + y_curve[3],
                   x_left + x_curve[4], y_top + y_curve[4],
                   x_left + x_curve[5], y_top + y_curve[5],
                   x_left + x_curve[6], y_top + y_curve[6])


def _curvy_path(renderer, x_left, y_top, y_bottom, typ):
    y_height = y_bottom - y_top

    path_string = _curve(x_left, y_top,
                         [7.5, -8, 21, 0, 18.5, -10.5, 7.5],
                         [0, y_height / 5.5, y_height / 3.14, y_height / 2, y_height / 2.93, y_height / 4.88, 0])

    path_string += _curve(x_left, y_top,
                          [0, 17.5, -7.5, 6.6, -5, 20, 0],
                          [y_height / 2, y_height / 1.46, y_height / 1.22, y_height, y_height / 1.19, y_height / 1.42, y_height / 2])

    a = Obj([('path', path_string), ('stroke', renderer.foregroundColor), ('fill', renderer.foregroundColor), ('class', renderer.controller.classes.generate(typ)), ("data-name", typ)])
    return renderer.paper.path(a)


def _brace_draw(renderer, x_left, y_top, y_bottom, typ, header, selectables):
    ret = None
    if header:
        go = Obj(klass=renderer.controller.classes.generate("staff-extra voice-name"))
        go["data-name"] = typ
        renderer.paper.open_group(go)
        position = y_top + (y_bottom - y_top) / 2
        position = position - renderer.controller.getTextSize.baseline_to_center(header, "voicefont", 'staff-extra voice-name', 0, 1)

        render_text(renderer, Obj(x=renderer.padding.left, y=position, text=header, type='voicefont', klass='staff-extra voice-name', anchor='start', centerVertically=True))
    if typ == "brace":
        ret = _curvy_path(renderer, x_left, y_top, y_bottom, typ)
    elif typ == "bracket":
        ret = _straight_path(renderer, x_left, y_top, y_bottom, typ)
    if header:
        ret = renderer.paper.close_group()
    selectables.wrap_svg_el(Obj(el_type=typ, startChar=-1, endChar=-1), ret)
    return ret


# -- crescendo.js, dynamics.js, ending.js, glissando.js -----------------------------------

def draw_crescendo(renderer, params, selectables):
    y = renderer.calc_y(params.pitch) + 4  # This is the top pixel to use (it is offset a little so that it looks good with the volume marks.)
    height = 8

    # TODO-PER: This is just a quick hack to make the dynamic marks not crash if they are mismatched.
    left = params.anchor1.x if params.anchor1 else 0
    right = params.anchor2.x if params.anchor2 else 800

    if params.dir == "<":
        el = _cresc_line(renderer, y + height / 2, y, y + height / 2, y + height, left, right)
    else:
        el = _cresc_line(renderer, y, y + height / 2, y + height, y + height / 2, left, right)
    selectables.wrap_svg_el(Obj(el_type="dynamicDecoration", startChar=-1, endChar=-1), el)
    return [el]


def _cresc_line(renderer, y1, y2, y3, y4, left, right):
    y1 = round_number(y1)
    y2 = round_number(y2)
    y3 = round_number(y3)
    y4 = round_number(y4)
    left = round_number(left)
    right = round_number(right)

    path_string = sprintf("M %f %f L %f %f M %f %f L %f %f", left, y1, right, y2, left, y3, right, y4)
    a = Obj([('path', path_string), ('highlight', "stroke"), ('stroke', renderer.foregroundColor), ('class', renderer.controller.classes.generate('dynamics decoration')), ("data-name", "dynamics")])
    return print_path(renderer, a)


def draw_dynamics(renderer, params, selectables):
    el = print_symbol(renderer, params.anchor.x, params.pitch, params.dec, Obj(
        scalex=1,
        scaley=1,
        klass=renderer.controller.classes.generate('decoration dynamics'),
        fill=renderer.foregroundColor,
        stroke="none",
        name="dynamics"))
    selectables.wrap_svg_el(Obj(el_type="dynamicDecoration", startChar=-1, endChar=-1, decoration=params.dec), el)
    return [el]


def draw_ending(renderer, params, linestartx, lineendx, selectables):
    y = round_number(renderer.calc_y(params.pitch))
    height = 20
    path_string = ''

    if params.anchor1:
        linestartx = round_number(params.anchor1.x + params.anchor1.w)
        path_string += sprintf("M %f %f L %f %f ", linestartx, y, linestartx, round_number(y + height))

    if params.anchor2:
        lineendx = round_number(params.anchor2.x)
        path_string += sprintf("M %f %f L %f %f ", lineendx, y, lineendx, round_number(y + height))

    path_string += sprintf("M %f %f L %f %f ", linestartx, y, lineendx, y)
    go = Obj(klass=renderer.controller.classes.generate("ending"), fill=renderer.foregroundColor)
    go["data-name"] = "ending"
    renderer.paper.open_group(go)
    a = Obj([('path', path_string), ('stroke', renderer.foregroundColor), ('fill', renderer.foregroundColor), ("data-name", "line")])
    print_path(renderer, a)
    if params.anchor1:
        render_text(renderer, Obj(
            x=round_number(linestartx + 5),
            y=round_number(renderer.calc_y(params.pitch - 0.5)),
            text=params.text,
            type='repeatfont',
            klass='ending',
            anchor="start",
            noClass=True,
            name=params.text))
    g = renderer.paper.close_group()
    selectables.wrap_svg_el(Obj(el_type="ending", startChar=-1, endChar=-1), g)
    return [g]


def draw_glissando(renderer, params, selectables):
    margin = 4
    left_y = renderer.calc_y(params.anchor1.heads[0].pitch)
    right_y = renderer.calc_y(params.anchor2.heads[0].pitch)
    left_x = params.anchor1.x + params.anchor1.w / 2
    right_x = params.anchor2.x + params.anchor2.w / 2

    w = right_x - left_x
    hh = right_y - left_y
    length = math.sqrt(w * w + hh * hh)
    margin_left = params.anchor1.w / 2 + margin
    margin_right = params.anchor2.w / 2 + margin
    s = (right_y - left_y) / (right_x - left_x) if right_x != left_x else float('nan')
    left_y_adj = _gliss_get_y(left_y, s, margin_left)
    num = js_max(2, js_floor((length - margin_left - margin_right - 5 * 2) / 6))

    el = _draw_squiggly(renderer, left_x + margin_left, left_y_adj, num, s)
    selectables.wrap_svg_el(Obj(el_type="glissando", startChar=-1, endChar=-1), el)
    return [el]


def _gliss_get_y(y, slope, x_ofs):
    return round_number(y + x_ofs * slope)


_gl_left_start = [[3.5, -4.8]]
_gl_right = [[1.5, -1], [.3, -.3], [-3.5, 3.8]]
_gl_left_end = [[-1.5, 2]]
_gl_top = [[3, 4], [3, -4]]
_gl_bottom = [[-3, 4], [-3, -4]]


def _segment(arr, slope):
    ret = ""
    for a in arr:
        ret += 'l' + js_str(a[0]) + ' ' + js_str(_gliss_get_y(a[1], slope, a[0]))
    return ret


def _draw_squiggly(renderer, x, y, num, slope):
    p = sprintf("M %f %f", x, y)
    p += _segment(_gl_left_start, slope)
    for _ in range(int(num) if not is_nan(num) else 0):
        p += _segment(_gl_top, slope)
    p += _segment(_gl_right, slope)
    for _ in range(int(num) if not is_nan(num) else 0):
        p += _segment(_gl_bottom, slope)
    p += _segment(_gl_left_end, slope) + 'z'
    a = Obj([('path', p), ('highlight', "stroke"), ('stroke', renderer.foregroundColor), ('class', renderer.controller.classes.generate('decoration')), ("data-name", "glissando")])
    return print_path(renderer, a)


# -- tie.js ------------------------------------------------------------------------------------

def draw_tie(renderer, params, linestartx, lineendx, selectables):
    _tie_layout(params, linestartx, lineendx)

    klass = ''
    if params.anchor1:
        c = params.anchor1.parent.counters
        klass += 'abcjs-start-m' + js_str(c.measure if c else None) + '-n' + js_str(c.note if c else None)
    else:
        klass += 'abcjs-start-edge'
    if params.anchor2:
        c = params.anchor2.parent.counters
        klass += ' abcjs-end-m' + js_str(c.measure if c else None) + '-n' + js_str(c.note if c else None)
    else:
        klass += ' abcjs-end-edge'
    if params.hint:
        klass = "abcjs-hint"
    fudge_y = 1.5 if params.fixedY else 0  # TODO-PER: This just compensates for drawArc, which contains too much knowledge of ties and slurs.
    el = _draw_arc(renderer, params.startX, params.endX, params.startY + fudge_y, params.endY + fudge_y, params.above, klass, params.isTie, params.dotted)
    start_char = -1
    # This gets the start and end points of the contents of the slur. We assume that the parenthesis are just to the outside of that.
    if params.anchor1 and not params.isTie:
        start_char = params.anchor1.parent.abcelem.startChar - 1
    end_char = -1
    if params.anchor2 and not params.isTie:
        end_char = params.anchor2.parent.abcelem.endChar + 1

    selectables.wrap_svg_el(Obj(el_type="slur", startChar=start_char, endChar=end_char), el)
    return [el]


def _tie_layout(params, line_start_x, line_end_x):
    # We now have all of the input variables set, so we can figure out the start and ending x,y coordinates, and finalize the direction of the arc.
    if not params.anchor1 or not params.anchor2:
        params.isTie = True  # if the slur goes off the end of the line, then draw it like a tie
    elif params.anchor1.pitch == params.anchor2.pitch and len(params.internalNotes) == 0:
        params.isTie = True
    else:
        params.isTie = False

    if params.isTie:
        params.calc_tie_direction()
        params.calc_x(line_start_x, line_end_x)
        params.calc_tie_y()
    else:
        params.calc_slur_direction()
        params.calc_x(line_start_x, line_end_x)
        params.calc_slur_y()
    params.avoid_collision_above()


def _draw_arc(renderer, x1, x2, pitch1, pitch2, above, klass, is_tie, dotted):
    # If it is a tie vs. a slur, draw it shallower.
    sp = 1.2 if is_tie else 1.5

    x1 = round_number(x1 + 6)
    x2 = round_number(x2 + 4)
    pitch1 = pitch1 + (sp if above else -sp)
    pitch2 = pitch2 + (sp if above else -sp)
    y1 = round_number(renderer.calc_y(pitch1))
    y2 = round_number(renderer.calc_y(pitch2))

    # unit direction vector
    dx = x2 - x1
    dy = y2 - y1
    norm = math.sqrt(dx * dx + dy * dy) if not (is_nan(dx) or is_nan(dy)) else float('nan')
    ux = dx / norm if norm else (float('nan') if dx == 0 else math.copysign(float('inf'), dx))
    uy = dy / norm if norm else (float('nan') if dy == 0 else math.copysign(float('inf'), dy))

    flatten = norm / 3.5
    max_flatten = 10 if is_tie else 25  # If it is a tie vs. a slur, draw it shallower.
    curve = (-1 if above else 1) * js_min(max_flatten, js_max(4, flatten))

    controlx1 = round_number(x1 + flatten * ux - curve * uy)
    controly1 = round_number(y1 + flatten * uy + curve * ux)
    controlx2 = round_number(x2 - flatten * ux - curve * uy)
    controly2 = round_number(y2 - flatten * uy + curve * ux)
    thickness = 2
    if klass:
        klass += ' slur'
    else:
        klass = 'slur'
    klass += ' tie' if is_tie else ' legato'
    if dotted:
        klass += ' dotted'
        path_string2 = sprintf("M %f %f C %f %f %f %f %f %f", x1, y1, controlx1, controly1, controlx2, controly2, x2, y2)
        a = Obj([('path', path_string2), ('stroke', renderer.foregroundColor), ('fill', "none"), ('stroke-dasharray', "5 5"), ('class', renderer.controller.classes.generate(klass)), ("data-name", "tie" if is_tie else "slur")])
        ret = renderer.paper.path(a)
    else:
        path_string = sprintf("M %f %f C %f %f %f %f %f %f C %f %f %f %f %f %f z", x1, y1,
                              controlx1, controly1, controlx2, controly2, x2, y2,
                              round_number(controlx2 - thickness * uy), round_number(controly2 + thickness * ux), round_number(controlx1 - thickness * uy), round_number(controly1 + thickness * ux), x1, y1)
        a = Obj([('path', path_string), ('stroke', "none"), ('fill', renderer.foregroundColor), ('class', renderer.controller.classes.generate(klass)), ("data-name", "tie" if is_tie else "slur")])
        ret = renderer.paper.path(a)
    return ret


# -- triplet.js ----------------------------------------------------------------------------------

def draw_triplet(renderer, params, selectables):
    go = Obj(klass=renderer.controller.classes.generate('triplet ' + js_str(params.durationClass)))
    go["data-name"] = "triplet"
    renderer.paper.open_group(go)
    if not params.hasBeam:
        _draw_bracket(renderer, params.anchor1.x, params.startNote, params.anchor2.x + params.anchor2.w, params.endNote, params.up)
    # HACK: adjust the position of "3". It is too high in all cases so we fudge it by subtracting 1 here.
    render_text(renderer, Obj(x=params.xTextPos, y=renderer.calc_y(params.yTextPos - 1), text=js_str(params.number), type='tripletfont', anchor="middle", centerVertically=True, noClass=True, name=js_str(params.number)), True)
    g = renderer.paper.close_group()
    selectables.wrap_svg_el(Obj(el_type="triplet", startChar=-1, endChar=-1), g)
    return g


def _tline(l, t, r, b):
    return sprintf("M %f %f L %f %f", round_number(l), round_number(t), round_number(r), round_number(b))


def _draw_bracket(renderer, x1, y1, x2, y2, up):
    y1 = renderer.calc_y(y1)
    y2 = renderer.calc_y(y2)
    bracket_height = 5 if up else -5

    # Draw vertical lines at the beginning and end
    path_string = ""
    path_string += _tline(x1, y1, x1, y1 + bracket_height)
    path_string += _tline(x2, y2, x2, y2 + bracket_height)

    # figure out midpoints to draw the broken line.
    mid_x = x1 + (x2 - x1) / 2
    gap_width = 8
    slope = (y2 - y1) / (x2 - x1) if x2 != x1 else float('nan')
    left_end_x = mid_x - gap_width
    left_end_y = y1 + (left_end_x - x1) * slope
    path_string += _tline(x1, y1, left_end_x, left_end_y)
    right_start_x = mid_x + gap_width
    right_start_y = y1 + (right_start_x - x1) * slope
    path_string += _tline(right_start_x, right_start_y, x2, y2)
    a = Obj([('path', path_string), ('stroke', renderer.foregroundColor), ("data-name", "triplet-bracket")])
    print_path(renderer, a)


# -- separator.js, non-music.js ---------------------------------------------------------------------

def draw_separator(renderer, width):
    fill = "rgba(0,0,0,255)"
    stroke = "rgba(0,0,0,0)"
    y = js_round(renderer.y)
    staff_width = renderer.controller.width
    x1 = (staff_width - width) / 2
    x2 = x1 + width
    path_string = ('M ' + js_str(x1) + ' ' + js_str(y) +
                   ' L ' + js_str(x2) + ' ' + js_str(y) +
                   ' L ' + js_str(x2) + ' ' + js_str(y + 1) +
                   ' L ' + js_str(x1) + ' ' + js_str(y + 1) +
                   ' L ' + js_str(x1) + ' ' + js_str(y) + ' z')
    renderer.paper.path_to_back(Obj([('path', path_string), ('stroke', stroke), ('fill', fill), ('class', renderer.controller.classes.generate('defined-text'))]))


def non_music(renderer, obj, selectables=None):
    for row in obj.rows:
        if row.absmove:
            renderer.absolutemove_y(row.absmove)
        elif row.move:
            renderer.move_y(row.move)
        elif row.text or row.phrases:
            x = row.left if row.left else 0
            p = Obj(x=x, y=renderer.y, text=row.text, phrases=row.phrases)
            p['dominant-baseline'] = row['dominant-baseline']
            p.type = row.font
            p.klass = row.klass
            p.name = row.name
            p.anchor = row.anchor
            el = render_text(renderer, p)
            if row.absElemType:
                selectables.wrap_svg_el(Obj(el_type=row.absElemType, name=row.name, startChar=row.startChar, endChar=row.endChar, text=row.text), el)
        elif row.separator:
            draw_separator(renderer, row.separator)
        elif row.startGroup:
            go = Obj(klass=row.klass)
            go["data-name"] = row.name
            renderer.paper.open_group(go)
        elif row.endGroup:
            g = renderer.paper.close_group()
            if row.absElemType:
                selectables.wrap_svg_el(Obj(el_type=row.absElemType, name=row.name, startChar=row.startChar, endChar=row.endChar, text=""), g)


# -- voice.js -------------------------------------------------------------------------------------------

def _is_non_spacer_rest(elem):
    if elem.type != 'rest':
        return False
    if elem.abcelem and elem.abcelem.rest and elem.abcelem.rest.type != 'spacer':
        return True
    return False


def draw_voice(renderer, params, bartop, selectables, staff_pos):
    width = params.w - 1
    renderer.staffbottom = params.staff.bottom
    save_color = renderer.foregroundColor
    if params.color:
        renderer.foregroundColor = params.color

    if params.header:  # print voice name
        text_el = render_text(renderer, Obj(x=renderer.padding.left, y=renderer.calc_y(params.headerPosition), text=params.header, type='voicefont', klass='staff-extra voice-name', anchor='start', centerVertically=True, name="voice-name"), True)
        selectables.wrap_svg_el(Obj(el_type="voiceName", startChar=-1, endChar=-1, text=params.header), text_el)

    found_note = False
    classes = renderer.controller.classes
    n = len(params.children)
    for i in range(n):
        child = params.children[i]
        if child.type == 'note' or child.type == 'rest':
            found_note = True
        just_initialized_measure_number = False
        if child.type != 'staff-extra' and not classes.is_in_measure():
            classes.start_measure()
            just_initialized_measure_number = True
        if params.staff.isTabStaff:
            child.invisible = False
            if child.type == 'bar':
                if child.abcelem.lastBar:
                    bartop = params.topLine
        draw_absolute(renderer, child, bartop if (params.barto or i == n - 1) else 0, selectables, staff_pos)

        if child.type == 'note' or _is_non_spacer_rest(child):
            classes.incr_note()
        if child.type == 'bar' and not just_initialized_measure_number and found_note:
            classes.incr_measure()

    classes.start_measure()

    for beam in params.beams:
        if beam == 'bar':
            classes.incr_measure()
        else:
            draw_beam(renderer, beam, selectables)  # beams must be drawn first for proper printing of triplets, slurs and ties.

    classes.start_measure()
    for child in params.otherchildren:
        if child == 'bar':
            classes.incr_measure()
        else:
            t = child.type
            if t == "GlissandoElem":
                child.elemset = draw_glissando(renderer, child, selectables)
            elif t == "CrescendoElem":
                child.elemset = draw_crescendo(renderer, child, selectables)
            elif t == "DynamicDecoration":
                child.elemset = draw_dynamics(renderer, child, selectables)
            elif t == "TripletElem":
                draw_triplet(renderer, child, selectables)
            elif t == "EndingElem":
                child.elemset = draw_ending(renderer, child, params.startx + 10, width, selectables)
            elif t == "TieElem":
                child.elemset = draw_tie(renderer, child, params.startx + 10, width, selectables)
            else:
                draw_absolute(renderer, child, params.startx + 10, width, selectables, staff_pos)
    renderer.foregroundColor = save_color


# -- staff-group.js -------------------------------------------------------------------------------------

def draw_staff_group(renderer, params, selectables, line_number):
    # We enter this method with renderer.y pointing to the topmost coordinate that we're allowed to draw.
    # All of the children that will be drawn have a relative "pitch" set, where zero is the first ledger line below the staff.
    # renderer.y will be offset at the beginning of each staff by the amount required to make the relative pitch work.
    # If there are multiple staves, then renderer.y will be incremented for each new staff.
    start_y = renderer.y  # So that it can be restored after we're done.
    # Set the absolute Y position for each staff here, so the voice drawing below can just use if.
    for staff1 in params.staffs:
        renderer.move_y(spacing.STEP, staff1.top)
        staff1.absoluteY = renderer.y
        if renderer.showDebug:
            if "box" in renderer.showDebug and staff1.voices:
                _box_all_elements(renderer, params.voices, staff1.voices)
            if "grid" in renderer.showDebug:
                _debug_grid(renderer, staff1, start_y)
        renderer.move_y(spacing.STEP, -staff1.bottom)
        if renderer.showDebug:
            if "grid" in renderer.showDebug:
                renderer.paper.dotted_line(Obj(x1=renderer.padding.left, x2=renderer.padding.left + renderer.controller.width, y1=renderer.y, y2=renderer.y, stroke="#0000aa"))
    top_line = None  # these are to connect multiple staves. We need to remember where they are.
    bottom_line = None

    line_pitch = 2
    bartop = 0
    for i in range(len(params.voices)):
        voice = params.voices[i]
        staff = voice.staff
        tab_name = voice.tabNameInfos
        renderer.y = staff.absoluteY
        renderer.controller.classes.incr_voice()
        # offset for starting the counting at middle C
        if not voice.duplicate:
            if not top_line:
                top_line = renderer.calc_y(10)
            bottom_line = renderer.calc_y(line_pitch)
            if staff.lines != 0:
                if staff.linePitch:
                    line_pitch = staff.linePitch
                renderer.controller.classes.new_measure()
                lines = print_staff(renderer, params.startx, params.w, staff.lines, staff.linePitch, 0.35)
                bottom_line = lines[1]
                staff.bottomLine = bottom_line
                staff.topLine = lines[0]
                # rework bartop when tabs are present with current staff
                if staff.hasTab:
                    # do not link to staff above  (ugly looking)
                    bartop = staff.topLine
                if staff.hasStaff:
                    # this is a tab
                    bartop = staff.hasStaff.topLine
                    voice.barto = True
                    voice.topLine = top_line
            _print_brace(renderer, staff.absoluteY, params.brace, i, selectables)
            _print_brace(renderer, staff.absoluteY, params.bracket, i, selectables)
        draw_voice(renderer, voice, bartop, selectables, Obj(top=start_y, zero=renderer.y, height=params.height * spacing.STEP))
        tab_name_height = 0
        if tab_name:
            # print tab infos on staffBottom
            r = Obj(rows=[])
            r.rows.append(Obj(absmove=bottom_line + 2))
            left_margin = 8
            r.rows.append(Obj(left=params.startx + left_margin, text=tab_name.name, font='tablabelfont', klass='text instrument-name', anchor='start'))
            r.rows.append(Obj(move=tab_name.textSize.height))
            non_music(renderer, r)
            tab_name_height = tab_name.textSize.height

        renderer.controller.classes.new_measure()
        if not voice.duplicate:
            bartop = renderer.calc_y(2 + tab_name_height)  # This connects the bar lines between two different staves.
    renderer.controller.classes.new_measure()

    # connect all the staves together with a vertical line
    staff_size = len(params.staffs)
    if staff_size > 1:
        top_line = params.staffs[0].topLine
        bottom_line = params.staffs[staff_size - 1].bottomLine
        print_stem(renderer, params.startx, 0.6, top_line, bottom_line, None, None)
    renderer.y = start_y


def _debug_grid(renderer, staff1, start_y):
    renderer.paper.dotted_line(Obj(x1=renderer.padding.left, x2=renderer.padding.left + renderer.controller.width, y1=start_y, y2=start_y, stroke="#0000ff"))
    a = Obj(x=renderer.padding.left, y=renderer.calc_y(staff1.originalTop), width=renderer.controller.width,
            height=renderer.calc_y(staff1.originalBottom) - renderer.calc_y(staff1.originalTop),
            fill=renderer.foregroundColor, stroke=renderer.foregroundColor)
    a["fill-opacity"] = 0.1
    a["stroke-opacity"] = 0.1
    print_debug_box(renderer, a)
    colors = ["rgb(207,27,36)", "rgb(168,214,80)", "rgb(110,161,224)", "rgb(191,119,218)", "rgb(195,30,151)",
              "rgb(31,170,177)", "rgb(220,166,142)"]
    color_index = [0]
    for key in ('chordHeightAbove', 'chordHeightBelow', 'dynamicHeightAbove', 'dynamicHeightBelow', 'endingHeightAbove',
                'lyricHeightAbove', 'lyricHeightBelow', 'partHeightAbove', 'tempoHeightAbove', 'volumeHeightAbove', 'volumeHeightBelow'):
        if staff1.positionY and staff1.positionY[key]:
            height = staff1.specialY[key] * spacing.STEP
            if key == "chordHeightAbove" and staff1.specialY.chordLines and staff1.specialY.chordLines.above:
                height *= staff1.specialY.chordLines.above
            if key == "chordHeightBelow" and staff1.specialY.chordLines and staff1.specialY.chordLines.below:
                height *= staff1.specialY.chordLines.below
            a = Obj(x=renderer.padding.left, y=renderer.calc_y(staff1.positionY[key]), width=renderer.controller.width, height=height,
                    fill=colors[color_index[0]], stroke=colors[color_index[0]])
            a["fill-opacity"] = 0.4
            a["stroke-opacity"] = 0.4
            print_debug_box(renderer, a, key[0:4])
            color_index[0] += 1
            if color_index[0] > 6:
                color_index[0] = 0


def _print_brace(renderer, absolute_y, brace, index, selectables):
    if brace:
        for b in brace:
            if b.is_start_voice(index):
                b.startY = absolute_y - spacing.STEP * 10
                b.elemset = draw_brace(renderer, b, selectables)


def _box_all_elements(renderer, voices, which):
    for w in which:
        for elem in voices[w].children:
            coords = elem.get_fixed_coords()
            if elem.invisible or coords.t is None or coords.b is None:
                continue
            height = (coords.t - coords.b) * spacing.STEP
            a = Obj(x=coords.x, y=renderer.calc_y(coords.t), width=coords.w, height=height, fill="#88e888")
            a["fill-opacity"] = 0.4
            a.stroke = "#4aa93d"
            a["stroke-opacity"] = 0.8
            print_debug_box(renderer, a)
            for rel_elem in elem.children:
                chord = rel_elem.get_chord_dim() if getattr(type(rel_elem), 'get_chord_dim', None) else None
                if chord:
                    y = renderer.calc_y(rel_elem.pitch)
                    y += rel_elem.dim.font.size * rel_elem.get_lane()
                    a = Obj(x=chord.left, y=y, width=chord.right - chord.left, height=rel_elem.dim.font.size, fill="none", stroke="#4aa93d")
                    a["stroke-opacity"] = 0.8
                    print_debug_box(renderer, a)


# -- set-paper-size.js -----------------------------------------------------------------------------------

def set_paper_size(renderer, maxwidth, scale, responsive):
    w = (maxwidth + renderer.padding.left + renderer.padding.right) * scale
    h = (renderer.y + renderer.padding.bottom) * scale
    if renderer.isPrint:
        h = js_max(h, 1056)  # 11in x 72pt/in x 1.33px/pt

    # for accessibility
    if renderer.ariaLabel != '':
        text = "Sheet Music"
        title = renderer.abctune.metaText.get('title') if (renderer.abctune and renderer.abctune.metaText) else None
        if title:
            text += " for \"" + (title if isinstance(title, str) else js_str(title)) + '"'
        renderer.paper.set_title(text)
        label = renderer.ariaLabel if renderer.ariaLabel else text
        renderer.paper.set_attribute("aria-label", label)

    # for dragging - don't select during drag
    styles = [
        "-webkit-touch-callout: none;",
        "-webkit-user-select: none;",
        "-khtml-user-select: none;",
        "-moz-user-select: none;",
        "-ms-user-select: none;",
        "user-select: none;",
    ]
    renderer.paper.insert_styles(".abcjs-dragging-in-progress text, .abcjs-dragging-in-progress tspan {" + " ".join(styles) + "}")

    parent_styles = Obj(overflow="hidden")
    if responsive == 'resize':
        renderer.paper.set_responsive_width(w, h)
    else:
        parent_styles.width = ""
        parent_styles.height = js_str(h) + "px"
        if scale < 1:
            parent_styles.width = js_str(w) + "px"
            renderer.paper.set_size(w / scale, h / scale)
        else:
            renderer.paper.set_size(w, h)
    renderer.paper.set_scale(scale)
    renderer.paper.set_parent_styles(parent_styles)


# -- draw.js ------------------------------------------------------------------------------------------------

def draw(renderer, classes, abc_tune, width, max_width, responsive, scale, select_types, tune_number, line_offset, chord_grid=None):
    from .chord_grid import draw_chord_grid
    selectables = Selectables(renderer.paper, select_types, tune_number)
    group_classes = Obj()
    if classes.shouldAddClasses:
        group_classes.klass = "abcjs-meta-top"
    renderer.paper.open_group(group_classes)
    renderer.move_y(renderer.padding.top)
    non_music(renderer, abc_tune.topText, selectables)
    renderer.paper.close_group()
    renderer.move_y(renderer.spacing.music)

    suppress_music = False
    if chord_grid and abc_tune.chordGrid:
        draw_chord_grid(renderer, abc_tune.chordGrid, renderer.padding.left, width, abc_tune.formatting)
        if chord_grid == 'noMusic':
            suppress_music = True

    staffgroups = []
    n_staves = 0
    if not suppress_music:
        for line in range(len(abc_tune.lines)):
            classes.incr_line()
            abc_line = abc_tune.lines[line]
            if abc_line.staff:
                # for incipits staff count limiting
                n_staves += 1
                if abc_tune.formatting.maxStaves:
                    if n_staves > abc_tune.formatting.maxStaves:
                        break
                if classes.shouldAddClasses:
                    group_classes.klass = "abcjs-staff-wrapper abcjs-l" + js_str(classes.lineNumber)
                renderer.paper.open_group(group_classes)
                if truthy(abc_line.vskip):
                    renderer.move_y(abc_line.vskip)
                if len(staffgroups) >= 1:
                    _add_staff_padding(renderer, renderer.spacing.staffSeparation, staffgroups[-1], abc_line.staffGroup)
                elif line > 0:  # This happens if there is non-music stuff before the first staff line
                    renderer.move_y(renderer.spacing.staffSeparation)
                staffgroup = _engrave_staff_line(renderer, abc_line.staffGroup, selectables, line)
                staffgroup.line = line_offset + line  # If there are non-music lines then the staffgroup array won't line up with the line array, so this keeps track.
                staffgroups.append(staffgroup)
                renderer.paper.close_group()
            elif abc_line.nonMusic:
                if classes.shouldAddClasses:
                    group_classes.klass = "abcjs-non-music"
                renderer.paper.open_group(group_classes)
                non_music(renderer, abc_line.nonMusic, selectables)
                renderer.paper.close_group()

    classes.reset()
    if not suppress_music:
        if abc_tune.bottomText and abc_tune.bottomText.rows and len(abc_tune.bottomText.rows) > 0:
            if classes.shouldAddClasses:
                group_classes.klass = "abcjs-meta-bottom"
            renderer.paper.open_group(group_classes)
            renderer.move_y(24)  # TODO-PER: Empirically discovered. What variable should this be?
            non_music(renderer, abc_tune.bottomText, selectables)
            renderer.paper.close_group()
    set_paper_size(renderer, max_width, scale, responsive)
    return Obj(staffgroups=staffgroups, selectables=selectables.get_elements())


def _engrave_staff_line(renderer, staff_group, selectables, line_number):
    draw_staff_group(renderer, staff_group, selectables, line_number)
    height = staff_group.height * spacing.STEP
    renderer.move_y(height)
    return staff_group


def _add_staff_padding(renderer, staff_separation, last_staff_group, this_staff_group):
    last_staff = last_staff_group.staffs[-1]
    last_bottom_line = -(last_staff.bottom - 2)  # The 2 is because the scale goes to 2 below the last line.
    next_top_line = this_staff_group.staffs[0].top - 10  # Because 10 represents the top line.
    natural_separation = next_top_line + last_bottom_line  # This is how far apart they'd be without extra spacing
    separation_in_pixels = natural_separation * spacing.STEP
    if separation_in_pixels < staff_separation:
        renderer.move_y(staff_separation - separation_in_pixels)
