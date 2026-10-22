"""Controls the engraving process, from the parsed tune to the SVG (port of ``engraver-controller.js``)."""

from ..jsutil import Obj, js_round, js_str, parse_float, truthy
from .helpers import spacing
from .helpers.classes import Classes
from .helpers.get_font_and_attr import GetFontAndAttr
from .helpers.get_text_size import GetTextSize
from .creation.abstract_engraver import AbstractEngraver
from .creation import text_rows
from .renderer import Renderer
from .layout.layout import layout
from .draw.draw import draw
from .dom import Element


class EngraverController:
    """Call :meth:`engrave_abc` to run the process.

    The SVG is created inside ``paper`` (a :class:`abcpy.write.dom.Element`, normally a ``div``).
    """

    def __init__(self, paper, params=None):
        params = Obj(params or {})
        self.oneSvgPerLine = params.oneSvgPerLine
        self.selectionColor = params.selectionColor
        self.dragColor = params.dragColor if params.dragColor else params.selectionColor
        self.dragging = bool(params.dragging)
        self.selectTypes = params.selectTypes
        self.responsive = params.responsive
        self.space = 3 * spacing.SPACE
        self.initialClef = params.initialClef
        self.timeBasedLayout = params.timeBasedLayout
        self.expandToWidest = bool(params.expandToWidest)
        self.scale = parse_float(params.scale) if params.scale else 0
        self.classes = Classes(Obj(shouldAddClasses=params.add_classes))
        if not (self.scale == self.scale and self.scale > 0.1):
            self.scale = None
        self.jazzchords = None
        self.accentAbove = None
        self.germanAlphabet = None
        self.lineThickness = None
        self.chordGrid = None
        self.engraver = None
        self.svgs = []
        self.selectables = []
        self.staffgroups = []

        if params.staffwidth:
            # Note: Normally all measurements to the engraver are in POINTS. However, if a person is formatting for the
            # screen and directly inputting the width, then it is more logical to have the measurement in pixels.
            self.staffwidthScreen = params.staffwidth
            self.staffwidthPrint = params.staffwidth
        else:
            self.staffwidthScreen = 740  # TODO-PER: Not sure where this number comes from, but this is how it's always been.
            self.staffwidthPrint = 680  # The number of pixels in 8.5", after 1cm of margin has been removed.
        self.listeners = []
        if params.clickListener:
            self.add_select_listener(params.clickListener)

        self.renderer = Renderer(paper)
        self.renderer.set_padding_override(params)
        if params.showDebug:
            self.renderer.showDebug = params.showDebug
        if params.jazzchords:
            self.jazzchords = params.jazzchords
        if params.accentAbove:
            self.accentAbove = params.accentAbove
        if params.germanAlphabet:
            self.germanAlphabet = params.germanAlphabet
        if params.lineThickness:
            self.lineThickness = params.lineThickness
        if params.chordGrid:
            self.chordGrid = params.chordGrid
        self.renderer.controller = self  # TODO-GD needed for highlighting
        self.renderer.foregroundColor = params.foregroundColor if params.foregroundColor else "currentColor"
        if params.ariaLabel is not None:
            self.renderer.ariaLabel = params.ariaLabel
        self.renderer.minPadding = params.minPadding if params.minPadding else 0

        self.reset()

    def reset(self):
        self.selected = []
        self.staffgroups = []
        if self.engraver:
            self.engraver.reset()
        self.engraver = None
        self.renderer.reset()
        self.dragTarget = None
        self.dragIndex = -1
        self.dragMouseStart = Obj(x=-1, y=-1)
        self.dragYStep = 0
        if self.lineThickness:
            self.renderer.set_line_thickness(self.lineThickness)

    def engrave_abc(self, abctunes, tune_number=None, line_offset=None):
        """Run the engraving process."""
        if not isinstance(abctunes, list):
            abctunes = [abctunes]
        self.reset()

        for i in range(len(abctunes)):
            if tune_number is None:
                tune_number = i
            self.getFontAndAttr = GetFontAndAttr(abctunes[i].formatting, self.classes)
            self.getTextSize = GetTextSize(self.getFontAndAttr, self.renderer.paper)
            self.engrave_tune(abctunes[i], tune_number, line_offset)

    def adjust_non_scaled_items(self, scale):
        # Some of the items on the page are not scaled, so adjust them in the opposite direction of scaling to cancel out the scaling.
        self.width /= scale
        self.renderer.adjust_non_scaled_items(scale)

    def get_measure_widths(self, abc_tune):
        self.reset()
        self.getFontAndAttr = GetFontAndAttr(abc_tune.formatting, self.classes)
        self.getTextSize = GetTextSize(self.getFontAndAttr, self.renderer.paper)
        orig_jazz_chords = self.jazzchords

        self.setup_tune(abc_tune, 0)
        self.construct_tune_elements(abc_tune)
        # layout() sets the x-coordinate of the abcTune element here:
        layout(self.renderer, abc_tune, 0, self.space, self.timeBasedLayout)

        ret = []
        section = None
        need_new_section = True
        for abc_line in abc_tune.lines:
            if abc_line.staff:
                if need_new_section:
                    section = Obj(left=0, measureWidths=[], total=0)
                    ret.append(section)
                    need_new_section = False
                # At this point, the voices are laid out so that the bar lines are even with each other. So we just need to get the placement of the first voice.
                if len(abc_line.staffGroup.voices) > 0:
                    voice = abc_line.staffGroup.voices[0]
                    found_not_staff_extra = False
                    last_x_position = 0
                    for child in voice.children:
                        if not found_not_staff_extra and not child.isClef and not child.isKeySig:
                            found_not_staff_extra = True
                            section.left = child.x
                            last_x_position = child.x
                        if child.type == 'bar':
                            section.measureWidths.append(child.x - last_x_position)
                            section.total += (child.x - last_x_position)
                            last_x_position = child.x
            else:
                need_new_section = True
        self.jazzchords = orig_jazz_chords
        return ret

    def setup_tune(self, abc_tune, tune_number):
        self.classes.reset()

        if abc_tune.formatting.jazzchords is not None:
            self.jazzchords = abc_tune.formatting.jazzchords
        if abc_tune.formatting.accentAbove is not None:
            self.accentAbove = abc_tune.formatting.accentAbove

        self.renderer.new_tune(abc_tune)
        self.engraver = AbstractEngraver(self.getTextSize, tune_number, Obj(
            bagpipes=abc_tune.formatting.bagpipes,
            flatbeams=abc_tune.formatting.flatbeams,
            graceSlurs=abc_tune.formatting.graceSlurs is not False,  # undefined is the default, which is true
            percmap=abc_tune.formatting.percmap,
            initialClef=self.initialClef,
            jazzchords=self.jazzchords,
            timeBasedLayout=self.timeBasedLayout,
            accentAbove=self.accentAbove,
            germanAlphabet=self.germanAlphabet,
        ))
        self.engraver.set_stem_height(self.renderer.spacing.stemHeight)
        mf = abc_tune.get_meter_fraction()
        self.engraver.measureLength = mf.num / mf.den if mf.den else float('nan')
        if abc_tune.formatting.staffwidth:
            self.width = abc_tune.formatting.staffwidth * 1.33  # The width is expressed in pt; convert to px.
        else:
            self.width = self.staffwidthPrint if self.renderer.isPrint else self.staffwidthScreen

        scale = abc_tune.formatting.scale if abc_tune.formatting.scale else self.scale
        if self.responsive == "resize":  # The resizing will mess with the scaling, so just don't do it explicitly.
            scale = None
        if scale is None:
            scale = 0.75 if self.renderer.isPrint else 1
        self.adjust_non_scaled_items(scale)
        return scale

    def construct_tune_elements(self, abc_tune):
        r = self.renderer
        abc_tune.topText = text_rows.top_text(abc_tune.metaText, abc_tune.metaTextInfo, abc_tune.formatting, abc_tune.lines, self.width, r.isPrint, r.padding.left, r.spacing, self.classes.shouldAddClasses, self.getTextSize)

        # Generate the raw staff line data
        has_printed_tempo = False
        has_seen_non_subtitle = False
        for i in range(len(abc_tune.lines)):
            abc_line = abc_tune.lines[i]
            if abc_line.staff:
                has_seen_non_subtitle = True
                abc_line.staffGroup = self.engraver.create_abc_line(abc_line.staff, abc_tune.metaText.get('tempo') if not has_printed_tempo else None, i)
                has_printed_tempo = True
            elif abc_line.subtitle:
                # If the subtitle is at the top, then it was already accounted for. So skip all subtitles until the first non-subtitle line.
                if has_seen_non_subtitle:
                    center = self.width / 2 + r.padding.left
                    abc_line.nonMusic = text_rows.subtitle(r.spacing.subtitle, abc_tune.formatting, abc_line.subtitle, center, r.padding.left, self.getTextSize)
            elif abc_line.text is not None:
                has_seen_non_subtitle = True
                abc_line.nonMusic = text_rows.free_text(abc_line.text, abc_line.vskip, self.getFontAndAttr, r.padding.left, self.width, self.getTextSize)
            elif abc_line.separator is not None and abc_line.separator.lineLength:
                has_seen_non_subtitle = True
                abc_line.nonMusic = text_rows.separator(abc_line.separator.spaceAbove, abc_line.separator.lineLength, abc_line.separator.spaceBelow)
        abc_tune.bottomText = text_rows.bottom_text(abc_tune.metaText, self.width, r.isPrint, r.padding.left, r.spacing, self.classes.shouldAddClasses, self.getTextSize)

    def engrave_tune(self, abc_tune, tune_number, line_offset):
        orig_jazz_chords = self.jazzchords
        scale = self.setup_tune(abc_tune, tune_number)

        # Create all of the element objects that will appear on the page.
        self.construct_tune_elements(abc_tune)

        # Do all the positioning, both horizontally and vertically
        max_width = layout(self.renderer, abc_tune, self.width, self.space, self.expandToWidest, self.timeBasedLayout)

        # Set the top text now that we know the width
        if self.expandToWidest and max_width > self.width + 1:
            r = self.renderer
            abc_tune.topText = text_rows.top_text(abc_tune.metaText, abc_tune.metaTextInfo, abc_tune.formatting, abc_tune.lines, max_width, r.isPrint, r.padding.left, r.spacing, self.classes.shouldAddClasses, self.getTextSize)
            for entry in abc_tune.lines:
                if entry.nonMusic and entry.nonMusic.rows:
                    for this_row in entry.nonMusic.rows:
                        # Recenter the element if it's a subtitle or centered text
                        if this_row.left:
                            if entry.subtitle:
                                this_row.left = (max_width / 2) + r.padding.left
                            elif entry.text and isinstance(entry.text, list) and len(entry.text) > 0:
                                if entry.text[0].center:
                                    this_row.left = (max_width / 2) + r.padding.left

        # Deal with tablature for staff
        if abc_tune.tablatures:
            from ..tablatures.abc_tablatures import layout_tablatures
            layout_tablatures(self.renderer, abc_tune)

        # Do all the writing to the SVG
        ret = draw(self.renderer, self.classes, abc_tune, self.width, max_width, self.responsive, scale, self.selectTypes, tune_number, line_offset if line_offset is not None else 0, self.chordGrid)
        self.staffgroups = ret.staffgroups
        self.selectables = ret.selectables
        if self.oneSvgPerLine:
            div = self.renderer.paper.svg.parent
            self.svgs = _split_svg_into_lines(self.renderer, div, abc_tune.metaText.get('title'), self.responsive, scale)
        else:
            self.svgs = [self.renderer.paper.svg]
        self._setup_selection()

        self.jazzchords = orig_jazz_chords

    def _setup_selection(self):
        # (The mouse and keyboard handling of abcjs needs a browser; only the attributes are set here.)
        if self.dragging:
            for h in range(len(self.selectables)):
                hist = self.selectables[h]
                if hist.svgEl.get_attribute("selectable") == "true":
                    hist.svgEl.set_attribute("tabindex", 0)
                    hist.svgEl.set_attribute("data-index", h)

    def get_dim(self, history_el):
        # Get the dimensions on demand because the getBBox call is expensive.
        if not history_el.dim:
            box = history_el.svgEl.get_bbox()
            history_el.dim = Obj(left=js_round(box.x), top=js_round(box.y), right=js_round(box.x + box.width), bottom=js_round(box.y + box.height))
        return history_el.dim

    def add_select_listener(self, click_listener):
        self.listeners.append(click_listener)

    def find_selectable_element(self, target):
        """Return the selectable entry whose SVG element is (or contains) ``target``."""
        el = target
        while el is not None and getattr(el, 'tag', None) != 'svg' and (not hasattr(el, 'attrs') or 'selectable' not in el.attrs):
            el = el.parent
        if el is not None and hasattr(el, 'attrs') and 'selectable' in el.attrs:
            idx = el.attrs.get('data-index')
            if idx is not None:
                idx = int(idx)
                if 0 <= idx < len(self.selectables):
                    return Obj(index=idx, element=self.selectables[idx])
        return None

    # camelCase aliases
    engraveABC = engrave_abc
    getMeasureWidths = get_measure_widths


def _split_svg_into_lines(renderer, output, title, responsive, scale):
    # Each line is a top level <g> in the svg. To split it into separate
    # svgs iterate through each of those and put them in a new svg. Since
    # they are placed absolutely, the viewBox needs to be manipulated to
    # get the correct vertical positioning.
    if not title:
        title = "Untitled"
    if not isinstance(title, str):
        title = js_str(title)
    source = output.query_selector("svg")
    if responsive == 'resize':
        output.style.paddingBottom = ''
    style = source.query_selector("style")
    if responsive == 'resize':
        vb = (source.get_attribute("viewBox") or "0 0 0 0").split()
        width = vb[2] if len(vb) > 2 else "0"
    else:
        width = source.get_attribute("width")
    sections = [c for c in source.children if c.tag == "g"]  # each section is a line, or the top matter or the bottom matter, or text that has been inserted.
    next_top = 0  # There are often gaps between the elements for spacing, so the actual top and height needs to be inferred.
    svgs = []
    for i in range(len(sections)):
        section = sections[i]
        box = section.get_bbox()
        gap_between_lines = box.y - next_top  # take the margin into account
        height = box.height + gap_between_lines
        wrapper = Element("div")
        div_styles = "overflow: hidden;"
        if responsive != 'resize':
            div_styles += "height:" + js_str(height * scale) + "px;"
        wrapper.set_attribute("style", div_styles)
        svg = _duplicate_svg(source)
        full_title = "Sheet Music for \"" + title + "\" section " + js_str(i + 1)
        svg.set_attribute("aria-label", full_title)
        if responsive != 'resize':
            svg.set_attribute("height", height)
        if responsive == 'resize':
            svg.style.position = ''
        view_box_height = height
        svg.set_attribute("viewBox", "0 " + js_str(next_top) + " " + js_str(width) + " " + js_str(view_box_height))
        if style is not None:
            svg.append_child(style.clone_node(True))
        title_el = Element("title")
        title_el.textContent = full_title
        svg.append_child(title_el)
        svg.append_child(section)

        wrapper.append_child(svg)
        svgs.append(svg)
        output.append_child(wrapper)
        next_top = box.y + box.height
    output.remove_child(source)
    return svgs


def _duplicate_svg(source):
    svg = Element("svg")
    for name, value in source.attrs.items():
        if name != "height" and name != "aria-label":
            svg.set_attribute(name, value)
    return svg
