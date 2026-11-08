import pytest

from xania_utils.areafile.reader import AreaParseError, Reader


def test_number_sign_and_pipe_addition():
    r = Reader("  -12 +3 4|8|16 ")
    assert [r.read_number(), r.read_number(), r.read_number()] == [-12, 3, 28]


def test_number_consumes_one_trailing_space_only():
    r = Reader("5 x")
    assert r.read_number() == 5
    assert r.peek() == "x"


def test_number_pushes_back_other_terminators():
    r = Reader("1d6+2")
    assert r.read_number() == 1
    assert r.read_letter() == "d"


def test_number_bad_format_is_fatal():
    with pytest.raises(AreaParseError):
        Reader("abc").read_number()


def test_number_ignores_latin1_digits():
    # '\xb2' (superscript two) satisfies str.isdigit() but not C isdigit().
    with pytest.raises(AreaParseError):
        Reader("\xb2").read_number()


def test_flag_letters_and_doubled_letters():
    r = Reader("ABQ a 0 12 C|D")
    assert r.read_flag() == (1 << 0) | (1 << 1) | (1 << 16)
    assert r.read_flag() == 1 << 26  # 'a' in a file (written 'aa' in StandardBits.hpp) = bit 26
    assert r.read_flag() == 0
    assert r.read_flag() == 12
    assert r.read_flag() == (1 << 2) | (1 << 3)


def test_flag_repeated_letter_counts_once():
    # fread_flag skips runs of the same letter ("bug fix for Ozydoc crap").
    assert Reader("AAB").read_flag() == 0b11


def test_string_to_tilde_keeps_newlines():
    r = Reader("  hello\nworld~ next~")
    assert r.read_string() == "hello\nworld"
    assert r.read_string() == "next"


def test_word_plain_and_quoted():
    r = Reader("stand 'two words' \"x y\" end\n")
    assert [r.read_word() for _ in range(4)] == ["stand", "two words", "x y", "end"]


def test_word_running_into_eof_is_fatal():
    # try_fread_word only returns a word once it sees a terminator; EOF straight
    # after the word yields nullopt, which fread_word treats as fatal.
    with pytest.raises(AreaParseError):
        Reader("end").read_word()


def test_word_at_eof_is_fatal():
    with pytest.raises(AreaParseError):
        Reader("   ").read_word()


def test_spnumber_slot_or_name():
    r = Reader("70 cure light~ 0")
    assert r.read_spnumber() == 70
    assert r.read_spnumber() == "cure light"
    assert r.read_spnumber() == 0


def test_spnumber_rejects_quoted_names():
    with pytest.raises(AreaParseError):
        Reader("'armor'").read_spnumber()


def test_to_eol_returns_comment_and_skips_blank_lines():
    r = Reader(" Concordius\n\n\nM")
    assert r.read_to_eol() == "Concordius"
    assert r.read_letter() == "M"


def test_crlf_is_normalised():
    r = Reader("abc~\r\n12\r\n")
    assert r.read_string() == "abc"
    assert r.read_number() == 12


def test_line_numbers():
    r = Reader("a\nb\nc")
    r.read_word()
    r.read_word()
    assert r.line == 2
