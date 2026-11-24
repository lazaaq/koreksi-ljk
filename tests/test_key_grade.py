"""Kunci jawaban & penilaian."""
import pytest

from koreksi_ljk import omr


@pytest.mark.parametrize("text,expect", [
    ("ABCDE", "ABCDE"),
    ("abcde", "ABCDE"),
    ("A B C\nD,E", "ABCDE"),
    ("ABCDE ABCDE", "ABCDEABCDE"),
    ("  ", ""),
    ("", ""),
    ("KUNCI: ABCD", "ABCD"),               # kata judul tidak ikut terbaca
    ("Kunci jawaban try out\nACBD", "ACBD"),
])
def test_parse_key_sequential(text, expect):
    k = omr.parse_key(text)
    assert "".join(k[q] for q in sorted(k)) == expect
    assert sorted(k) == list(range(1, len(expect) + 1))


@pytest.mark.parametrize("text", [
    "1.A 2.B 3.C", "1. A  2. B  3. C", "1) a 2) b 3) c", "1-A\n2-B\n3-C", "1 A 2 B 3 C", "1=A, 2=B, 3=C", "1:A 2:B 3:C",
])
def test_parse_key_numbered(text):
    assert omr.parse_key(text) == {1: "A", 2: "B", 3: "C"}


def test_parse_key_numbered_with_header_line():
    # isi kunci_perkiraan.txt ditempel utuh, termasuk baris judulnya
    text = "Kunci PERKIRAAN (jawaban terbanyak siswa, bukan kunci resmi):\n1. C   2. C   3. D   4. A"
    assert omr.parse_key(text) == {1: "C", 2: "C", 3: "D", 4: "A"}


def test_parse_key_numbered_out_of_order_and_gaps():
    assert omr.parse_key("10.B 2.A 7.D") == {10: "B", 2: "A", 7: "D"}
    assert omr.parse_key("0.A 1.B 2.C 3.D") == {1: "B", 2: "C", 3: "D"}  # nomor 0 diabaikan


def test_parse_key_follows_template_numbers():
    assert omr.parse_key("ABC", questions=[11, 12, 13, 14]) == {11: "A", 12: "B", 13: "C"}


def test_parse_key_letters_outside_a_to_j_ignored():
    assert omr.parse_key("A B Z C") == {1: "A", 2: "B", 3: "C"}


def test_invalid_key(tpl):
    assert omr.invalid_key({1: "A", 2: "E"}, tpl) == []
    four = omr.Template(name="x", ref_path="")
    four.blocks.append(omr.Block("soal", [0, 0, 1, 1], 2, 4, "rows", start=1, labels="ABCD",
                                 centers=[[[0, 0]] * 4] * 2))
    assert omr.invalid_key({1: "E", 2: "D"}, four) == [1]


def test_grade_basic():
    key = {1: "A", 2: "B", 3: "C", 4: "D"}
    g = omr.grade({1: "A", 2: "C", 3: "", 4: "*"}, key)
    assert (g["benar"], g["salah"], g["kosong"]) == (1, 2, 1)   # ganda dihitung salah
    assert g["skor"] == 1 and g["nilai"] == 25.0


def test_grade_points_minus_and_missing_answers():
    key = {1: "A", 2: "B", 3: "C", 4: "D"}
    g = omr.grade({1: "A", 2: "A"}, key, pts=(4, -1, 0))        # soal 3 & 4 tidak ada → kosong
    assert (g["benar"], g["salah"], g["kosong"]) == (1, 1, 2)
    assert g["skor"] == 3 and g["nilai"] == round(3 / 16 * 100, 2)


def test_grade_extra_answers_not_in_key_ignored():
    g = omr.grade({1: "A", 2: "B", 99: "C"}, {1: "A"})
    assert g["benar"] == 1 and g["salah"] == 0 and g["kosong"] == 0 and g["nilai"] == 100.0


def test_grade_empty_key_and_zero_points():
    assert omr.grade({1: "A"}, {})["nilai"] == 0.0
    assert omr.grade({1: "A"}, {1: "A"}, pts=(0, 0, 0))["nilai"] == 0.0  # tidak membagi nol
