"""Tests of the public API."""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import abcpy  # noqa: E402
from abcpy import Obj  # noqa: E402

TUNE = """X:1
T:Speed the Plough
C:Trad.
M:4/4
L:1/8
Q:1/4=120
K:G
|:GABc dedB|dedB dedB|c2ec B2dB|c2A2 A2BA|
  GABc dedB|dedB dedB|c2ec B2dB|"D7"A2F2 G4:|
w: la la la la
"""

BOOK = """%%titlefont Times 20

X:1
T:First
K:C
CDEF|

X:2
T:Second
K:D
DEFG|
"""


def test_parse_basics():
    tunes = abcpy.parse_only(TUNE)
    assert len(tunes) == 1
    tune = tunes[0]
    assert tune.metaText["title"] == "Speed the Plough"
    assert tune.metaText.composer == "Trad."
    assert tune.get_meter_fraction() == {"num": 4, "den": 4}
    assert tune.get_key_signature().root == "G"
    assert tune.get_bpm() == 120
    assert tune.get_bar_length() == 1
    assert tune.get_beat_length() == 0.25
    voice = tune.lines[0].staff[0].voices[0]
    notes = [el for el in voice if el.el_type == "note"]
    assert notes[0].pitches[0].name == "G"
    assert notes[0].duration == 0.125
    assert notes[0].lyric is None  # the w: line belongs to the second line of music
    second = [el for el in tune.lines[1].staff[0].voices[0] if el.el_type == "note"]
    assert second[0].lyric[0].syllable == "la"
    assert any(el.chord for el in second)
    bars = [el for el in voice if el.el_type == "bar"]
    assert bars[0].type == "bar_left_repeat"
    assert [el for el in tune.lines[1].staff[0].voices[0] if el.el_type == "bar"][-1].type == "bar_right_repeat"


def test_obj_semantics():
    o = Obj(a=1)
    assert o.a == 1 and o["a"] == 1
    assert o.missing is None and o["missing"] is None
    assert bool(Obj()) is True
    o.b = 2
    assert o == {"a": 1, "b": 2}
    del o.a
    assert o == {"b": 2}


def test_json_round_trip():
    tune = abcpy.parse_only(TUNE)[0]
    data = json.loads(tune.to_json())
    assert data["metaText"]["title"] == "Speed the Plough"
    assert data["lines"][0]["staff"][0]["key"]["root"] == "G"


def test_warnings():
    tune = abcpy.parse_only("X:1\nK:C\nabc ¿ |\n")[0]
    assert tune.warnings
    assert "Unknown character" in tune.warnings[0]


def test_tune_book():
    assert abcpy.number_of_tunes(BOOK) == 3
    book = abcpy.TuneBook(BOOK)
    assert [t.title for t in book.tunes] == ["First", "Second"]
    assert book.get_tune_by_id(2).title == "Second"
    assert book.get_tune_by_title("First").id == "1"
    assert book.header == "%%titlefont Times 20\n"
    tunes = abcpy.parse_only(BOOK)
    assert len(tunes) == 2
    assert tunes[1].formatting.titlefont.size == 20


def test_extract_measures():
    m = abcpy.extract_measures(TUNE)
    assert len(m) == 1
    assert m[0].header.startswith("X:1")
    assert m[0].measures[0].abc.strip() == "|:GABc dedB|"
    assert m[0].hasPickup is False


def test_transpose_text():
    up = abcpy.transpose(TUNE, 2)
    assert "K:A" in up
    assert "|:ABcd efec|" in up
    assert '"E7"' in up
    assert abcpy.transpose(up, -2).replace(" ", "") == TUNE.replace(" ", "")


def test_visual_transpose():
    tune = abcpy.parse_only(TUNE, {"visualTranspose": 2})[0]
    assert tune.lines[0].staff[0].key.root == "A"
    assert tune.visualTranspose == 2


def test_deline_and_line_breaks():
    tune = abcpy.parse_only(TUNE)[0]
    assert len(tune.lines) == 2
    lines = tune.deline()
    assert len(lines) == 1
    lines = tune.deline({"lineBreaks": True})
    assert any(el.el_type == "break" for el in lines[0].staff[0].voices[0])
    wrapped = abcpy.parse_only(TUNE, {"lineBreaks": [[1, 3, 5]]})[0]
    assert len(wrapped.lines) == 4


def test_element_from_char():
    tune = abcpy.parse_only(TUNE)[0]
    pos = TUNE.index("dedB")
    el = tune.get_element_from_char(pos)
    assert el.el_type == "note" and el.pitches[0].name == "d"


def test_audio_and_midi():
    tune = abcpy.parse_only(TUNE)[0]
    audio = tune.set_up_audio()
    assert audio.tempo == 120
    assert len(audio.tracks) == 2  # melody and chords
    notes = [ev for ev in audio.tracks[0] if ev.cmd == "note"]
    assert notes[0].pitch == 67  # G above middle C
    midi = abcpy.get_midi_file(TUNE)[0]
    assert isinstance(midi, bytes) and midi.startswith(b"MThd")
    encoded = abcpy.get_midi_file(TUNE, {"midiOutputType": "encoded"})[0]
    assert encoded.startswith("data:audio/midi,MThd")
    link = abcpy.get_midi_file(TUNE, {"midiOutputType": "link"})[0]
    assert 'download="speed_the_plough.midi"' in link


def test_svg():
    svg = abcpy.render_svg(TUNE)[0]
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert "Speed the Plough" in svg
    assert 'data-name="clefs.G"' in svg
    classes = abcpy.render_svg(TUNE, {"add_classes": True})[0]
    assert "abcjs-note" in classes
    lines = abcpy.render_svg(TUNE, {"oneSvgPerLine": True})[0]
    assert len(lines) == 3  # title and two music lines


def test_write_files(tmp_path):
    out = abcpy.write_svg(BOOK, str(tmp_path / "tune-{n}.svg"))
    assert len(out) == 2 and all(os.path.exists(p) for p in out)
    p = abcpy.write_midi_file(TUNE, str(tmp_path / "t.mid"))
    assert open(p, "rb").read(4) == b"MThd"


def test_render_abc_with_engraver_data():
    tunes = abcpy.render_abc("*", TUNE)
    tune = tunes[0]
    assert tune.engraver.staffgroups
    timings = tune.set_timing()
    assert timings[-1].type == "end"
    assert tune.get_total_time() > 0
    note = tune.lines[0].staff[0].voices[0][1]
    assert note.abselem is not None and note.abselem.x > 0


def test_tablature_and_chord_grid():
    svg = abcpy.render_svg(TUNE, {"tablature": [{"instrument": "guitar"}]})[0]
    assert "abcjs-tab-number" in svg or "tab-number" in svg or 'data-name="tab.big"' in svg
    tune = abcpy.parse_only(TUNE, {"chordGrid": "withMusic"})[0]
    assert tune.chordGrid[0].type == "part"


def test_wrap():
    long_tune = "X:1\nT:Wrap\nM:4/4\nL:1/8\nK:C\n" + "|".join(["cdef gabc'"] * 16) + "|]\n"
    # (like abcjs, wrapping is not done when rendering to "*")
    tunes = abcpy.render_abc(abcpy.Element("div"), long_tune, {"staffwidth": 400, "wrap": {"minSpacing": 1.8, "maxSpacing": 2.7, "preferredMeasuresPerLine": 4}})
    assert tunes[0].lineBreaks
    assert len([l for l in tunes[0].lines if l.staff]) > 1


def test_tune_metrics():
    m = abcpy.tune_metrics(TUNE)
    assert len(m[0].sections[0].measureWidths) == 9  # the opening repeat bar counts too


def test_cli(tmp_path):
    src = tmp_path / "t.abc"
    src.write_text(TUNE, encoding="utf-8")
    subprocess.run([sys.executable, "-m", "abcpy", str(src), "--svg", str(tmp_path / "t.svg"),
                    "--midi", str(tmp_path / "t.mid"), "--json", str(tmp_path / "t.json"),
                    "--transpose", "2", "--abc", str(tmp_path / "t2.abc")],
                   check=True, cwd=os.path.dirname(HERE))
    assert (tmp_path / "t.svg").read_text(encoding="utf-8").startswith("<?xml")
    assert (tmp_path / "t.mid").read_bytes().startswith(b"MThd")
    assert json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))[0]["lines"][0]["staff"][0]["key"]["root"] == "A"
    assert "K:A" in (tmp_path / "t2.abc").read_text(encoding="utf-8")


def test_parse_file(tmp_path):
    src = tmp_path / "book.abc"
    src.write_text(BOOK, encoding="utf-8")
    assert [t.metaText.title for t in abcpy.parse_file(str(src))] == ["First", "Second"]
