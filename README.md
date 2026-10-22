# abcpy

A Python port of [abcjs](https://github.com/paulrosen/abcjs) (version 6.7.2) for reading,
parsing, manipulating and engraving music written in [ABC notation](https://abcnotation.com/).

* **Parse** abc text into the same tune structure that abcjs produces (`tune.lines`,
  `tune.metaText`, ...), including warnings, line wrapping, chord grids and visual transposition.
* **Manipulate**: transpose the abc text (`transpose`, a port of `strTranspose`), split books into
  tunes, extract measures, "deline" a tune, get the meter, key, tempo, pickup, timing...
* **Engrave** to SVG files (no browser needed), including tablature for string instruments.
* **MIDI**: the abcjs sequencer/flattener and its MIDI file writer (no web audio).

The port is pure Python with no dependencies. It was verified by running abcjs in Node next to
abcpy and comparing the results: on the ~2400 tunes used by the abcjs test-suite, 3000 tunes from
thesession.org and thousands of randomly mutated (fuzzed) tunes, the parsed tunes, the MIDI
events, the MIDI files, the transposed abc text, the timing events and the SVG files are
identical to what abcjs produces (see [Testing](#testing)).

## Installation

```
pip install .
```

Python 3.8 or later.

## Quick start

```python
import abcpy

abc = """X:1
T:Speed the Plough
M:4/4
L:1/8
K:G
|:GABc dedB|dedB dedB|c2ec B2dB|c2A2 A2BA|
  GABc dedB|dedB dedB|c2ec B2dB|A2F2 G4:|
"""

tune = abcpy.parse_only(abc)[0]
print(tune.metaText["title"])            # Speed the Plough
print(tune.get_meter_fraction())         # {'num': 4, 'den': 4}
print(tune.get_key_signature()["root"])  # G
for el in tune.lines[0]["staff"][0]["voices"][0][:3]:
    print(el["el_type"], el.get("pitches"), el.get("duration"))
# bar None None
# note [{'pitch': 4, 'name': 'G', 'verticalPos': 4}] 0.125
# note [{'pitch': 5, 'name': 'A', 'verticalPos': 5}] 0.125

print(abcpy.transpose(abc, 2))           # the same tune in A
abcpy.write_svg(abc, "plough.svg")       # sheet music
open("plough.mid", "wb").write(abcpy.get_midi_file(abc)[0])
```

## The tune object

`parse_only()` returns a list of `abcpy.Tune` objects (one per tune in the string). The data
attributes have the same names as in abcjs (`lines`, `metaText`, `metaTextInfo`, `formatting`,
`media`, `version`, `warnings`, `lineBreaks`, `chordGrid`, ...) so the
[abcjs documentation of the tune object](https://paulrosen.github.io/abcjs/visual/render-abc-result.html)
applies directly.

All the dictionaries in the structure are `abcpy.Obj` instances: ordinary `dict`s that also allow
attribute access, where a missing key reads as `None` (like `undefined` in JavaScript):

```python
note = tune.lines[0].staff[0].voices[0][4]
note["pitches"][0]["name"]   # 'c'
note.pitches[0].name         # the same
note.chord                   # None when there is no chord
```

Like a JavaScript object, an `Obj` is always truthy, even when empty. `tune.to_dict()` returns
the plain structure and `tune.to_json()` serializes it.

Useful methods (abcjs camelCase names are available as aliases):

| abcpy | abcjs |
| --- | --- |
| `tune.get_meter()`, `tune.get_meter_fraction()` | `getMeter()`, `getMeterFraction()` |
| `tune.get_key_signature()` | `getKeySignature()` |
| `tune.get_bar_length()`, `tune.get_beat_length()`, `tune.get_beats_per_measure()` | `getBarLength()`, ... |
| `tune.get_pickup_length()` | `getPickupLength()` |
| `tune.get_bpm()`, `tune.milliseconds_per_measure()` | `getBpm()`, `millisecondsPerMeasure()` |
| `tune.get_element_from_char(i)` | `getElementFromChar(i)` |
| `tune.deline(options)` | `deline(options)` |
| `tune.set_up_audio(options)` | `setUpAudio(options)` |
| `tune.set_timing(bpm, measures_of_delay)` (after rendering) | `setTiming()` |

## Module functions

| abcpy | abcjs | notes |
| --- | --- | --- |
| `parse_only(abc, params)` | `parseOnly` | returns a list of `Tune` |
| `parse_file(path, params)`, `read_file(path)` | | parse / read an `.abc` file |
| `number_of_tunes(abc)` | `numberOfTunes` | |
| `TuneBook(abc)` | `TuneBook` | `.header`, `.tunes`, `get_tune_by_id()`, `get_tune_by_title()` |
| `extract_measures(abc)` | `extractMeasures` | |
| `str_transpose(abc, tunes, steps)`, `transpose(abc, steps)` | `strTranspose` | |
| `render_abc(output, abc, params)` | `renderAbc` | `output` is an `abcpy.Element` (or list), or `"*"` |
| `render_svg(abc, params)` | | one SVG document (string) per tune |
| `write_svg(abc, path, params)` | | `{n}` in `path` is replaced by the tune number |
| `tune_metrics(abc, params)` | `tuneMetrics` | |
| `get_midi_file(abc_or_tune, options)` | `synth.getMidiFile` | default `midiOutputType` is `"binary"` (bytes); `"encoded"` and `"link"` also work |
| `write_midi_file(abc, path, options)` | | |
| `sequence(tune, options)`, `flatten(...)` | `synth.sequence`, ... | the MIDI events |
| `set_glyph(name, path)` | `setGlyph` | |
| `Parse()` | `test.Parse` | the parser itself |

All the parser and engraver parameters of abcjs work (`visualTranspose`, `lineBreaks`,
`wrap` + `staffwidth`, `chordGrid`, `tablature`, `format`, `add_classes`, `responsive`,
`oneSvgPerLine`, `scale`, `foregroundColor`, `paddingtop`..., `jazzchords`, `germanAlphabet`,
`initialClef`, `timeBasedLayout`, ...). Pass them as a dict:

```python
svg = abcpy.render_svg(abc, {"staffwidth": 500, "wrap": {"minSpacing": 1.8, "maxSpacing": 2.7,
                                                          "preferredMeasuresPerLine": 4},
                             "tablature": [{"instrument": "guitar"}],
                             "add_classes": True})[0]
```

## SVG and text sizes

abcjs measures text with the browser. abcpy uses font metrics instead: the widths of the
Liberation fonts, which are metric-compatible with Arial/Helvetica, Times New Roman and Courier
New (the font families in the abc file are mapped to the closest of the three). The layout is
therefore the same as abcjs in a browser that uses those fonts, and very close otherwise.

## Command line

```
python -m abcpy tune.abc --svg tune.svg --midi tune.mid
python -m abcpy book.abc --list
python -m abcpy tune.abc --transpose -2 --abc tune-in-F.abc --json tune.json
```

## What is not ported

* Web audio playback (`synth.CreateSynth`, `SynthController`, sound fonts), the editor
  (`Editor`, `EditArea`), mouse/keyboard interaction and `TimingCallbacks` (all need a browser).
  Everything that produces data is ported: MIDI events, MIDI files, timing events, selectable
  elements and the SVG.

## Differences from abcjs

* Character positions (`startChar`/`endChar`) index Python strings, so they count code points;
  JavaScript counts UTF-16 code units, which differs only for characters outside the Basic
  Multilingual Plane (e.g. emoji).
* Inputs that make abcjs throw a JavaScript `TypeError` are handled more gracefully where it was
  simple to do so (the result is then what abcjs would have produced without the crash), and
  `%%beginps` no longer loops forever. Where abcjs leaked internal error texts into warnings,
  abcpy gives a regular message.
* Each parsed tune is independent (abcjs reuses some parser state between tunes).

## Testing

```
python -m pytest tests
```

The regression tests compare fingerprints of abcpy's output with fingerprints of abcjs's output
that are stored in `tests/fixtures`. With Node and an abcjs checkout available, the differential
test scripts in `tests/` compare directly against abcjs:

```
ABCJS_ROOT=/path/to/abcjs python3 tests/diff_parse.py       # parser
python3 tests/diff_transpose.py                              # strTranspose
python3 tests/diff_audio.py                                  # setUpAudio and MIDI files
python3 tests/diff_svg.py                                    # SVG (abcjs runs on tests/js/fakedom.js)
python3 tests/diff_timing.py                                 # setTiming
```

`tests/js/collect_abc.js` extracts the abc strings that the abcjs test-suite uses and
`tests/make_fuzz.py` makes randomly mutated variants of them.

## License

MIT, like abcjs (see LICENSE.md). The font metric tables are derived from the Liberation fonts
(SIL Open Font License).
