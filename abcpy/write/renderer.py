"""API to render the engraved structure to SVG (port of ``renderer.js``)."""

from ..jsutil import Obj
from .helpers import spacing
from .svg import Svg


class Renderer:
    def __init__(self, paper):
        self.paper = Svg(paper)
        self.controller = None
        self.space = 3 * spacing.SPACE
        self.padding = Obj()  # renderer's padding is managed by the controller
        self.paddingOverride = Obj()
        self.firefox = False
        self.showDebug = None
        self.foregroundColor = "currentColor"
        self.ariaLabel = None
        self.minPadding = 0
        self.staffbottom = None
        self.reset()

    def reset(self):
        self.paper.clear()
        self.y = 0
        self.abctune = None
        self.path = None
        self.isPrint = False
        self.lineThickness = 0
        self.init_vertical_space()

    def new_tune(self, abc_tune):
        self.abctune = abc_tune  # TODO-PER: this is just to get the font info.
        self.set_vertical_space(abc_tune.formatting)
        self.isPrint = abc_tune.media == 'print'
        self.set_padding(abc_tune)

    def set_line_thickness(self, line_thickness):
        self.lineThickness = line_thickness

    def set_padding_override(self, params):
        self.paddingOverride = Obj(top=params.get('paddingtop'), bottom=params.get('paddingbottom'),
                                   right=params.get('paddingright'), left=params.get('paddingleft'))

    def set_padding(self, abctune):
        # If the padding is set in the tune, then use that.
        # Otherwise, if the padding is set in the override, use that.
        # Otherwise, use the defaults (there are a different set of defaults for screen and print.)
        def set_padding_variable(padding_key, formatting_key, print_default, screen_default):
            if abctune.formatting.get(formatting_key) is not None:
                self.padding[padding_key] = abctune.formatting[formatting_key]
            elif self.paddingOverride.get(padding_key) is not None:
                self.padding[padding_key] = self.paddingOverride[padding_key]
            elif self.isPrint:
                self.padding[padding_key] = print_default
            else:
                self.padding[padding_key] = screen_default
        # 1cm x 0.393701in/cm x 72pt/in x 1.33px/pt = 38px
        # 1.8cm x 0.393701in/cm x 72pt/in x 1.33px/pt = 68px
        set_padding_variable('top', 'topmargin', 38, 15)
        set_padding_variable('bottom', 'botmargin', 38, 15)
        set_padding_variable('left', 'leftmargin', 68, 15)
        set_padding_variable('right', 'rightmargin', 68, 15)

    def adjust_non_scaled_items(self, scale):
        # Some of the items on the page are not scaled, so adjust them in the opposite direction of scaling to cancel out the scaling.
        self.padding.top /= scale
        self.padding.bottom /= scale
        self.padding.left /= scale
        self.padding.right /= scale
        self.abctune.formatting.headerfont.size /= scale
        self.abctune.formatting.footerfont.size /= scale

    def init_vertical_space(self):
        # conversion: 37.7953 = conversion factor for cm to px.
        # All of the following values are in px.
        self.spacing = Obj(
            composer=7.56,  # Set the vertical space above the composer.
            graceBefore=8.67,  # Define the space before, inside and after the grace notes.
            graceInside=10.67,
            graceAfter=16,
            info=0,  # Set the vertical space above the infoline.
            lineSkipFactor=1.1,  # Set the factor for spacing between lines of text. (multiply this by the font size)
            music=7.56,  # Set the vertical space above the first staff.
            paragraphSkipFactor=0.4,  # Set the factor for spacing between text paragraphs. (multiply this by the font size)
            parts=11.33,  # Set the vertical space above a new part.
            slurHeight=1.0,  # Set the slur height factor.
            staffSeparation=61.33,  # Do not put a staff system closer than <unit> from the previous system.
            staffTopMargin=0,
            stemHeight=26.67 + 10,  # Set the stem height.
            subtitle=3.78,  # Set the vertical space above the subtitle.
            systemStaffSeparation=48,  # Do not place the staves closer than <unit> inside a system.
            text=18.9,  # Set the vertical space above the history.
            title=7.56,  # Set the vertical space above the title.
            top=30.24,  # Set the vertical space above the tunes and on the top of the continuation pages.
            vocal=0,  # Set the vertical space above the lyrics under the staves.
            words=0,  # Set the vertical space above the lyrics at the end of the tune.
        )

    def set_vertical_space(self, formatting):
        # conversion from pts to px 4/3
        mapping = (('staffsep', 'staffSeparation'), ('composerspace', 'composer'), ('partsspace', 'parts'),
                   ('textspace', 'text'), ('musicspace', 'music'), ('titlespace', 'title'),
                   ('sysstaffsep', 'systemStaffSeparation'), ('stafftopmargin', 'staffTopMargin'),
                   ('subtitlespace', 'subtitle'), ('topspace', 'top'), ('vocalspace', 'vocal'), ('wordsspace', 'words'))
        for fkey, skey in mapping:
            if formatting.get(fkey) is not None:
                self.spacing[skey] = formatting[fkey] * 4 / 3

    def calc_y(self, ofs):
        """Calculates the y for a given pitch value (relative to the stave the renderer is currently printing)."""
        if ofs is None:
            return float('nan')
        return self.y - ofs * spacing.STEP

    def y_to_pitch(self, ofs):
        return ofs / spacing.STEP

    def move_y(self, em, num_lines=None):
        if num_lines is None:
            num_lines = 1
        self.y += em * num_lines

    def absolutemove_y(self, y):
        self.y = y
