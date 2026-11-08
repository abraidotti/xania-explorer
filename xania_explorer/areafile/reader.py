"""Character-level reader that mirrors Xania's ``fread_*`` functions.

Each method ports one C++ function from ``xania/src/db.cpp`` (see the docstrings
for line references). The behaviour is deliberately faithful, quirks included,
so that what this parser reads is what the MUD reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

EOF = ""
_WS = " \t\n\r\v\f"


def _isdigit(c: str) -> bool:
    # ASCII only: latin-1 characters such as '²' satisfy str.isdigit().
    return len(c) == 1 and "0" <= c <= "9"


def _isalpha(c: str) -> bool:
    return len(c) == 1 and ("A" <= c <= "Z" or "a" <= c <= "z")


class AreaParseError(Exception):
    """A condition the C++ loader treats as fatal (it calls ``exit(1)``)."""

    def __init__(self, message: str, file: str = "", line: int = 0):
        self.message = message
        self.file = file
        self.line = line
        super().__init__(f"{file}:{line}: {message}" if file else message)


@dataclass(frozen=True)
class Diagnostic:
    """A condition the C++ loader logs via ``logger.bug`` and then carries on."""

    file: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.message}"


def flag_bit(letter: str) -> int:
    """``flag_convert`` (db.cpp:1346): A..Z -> bits 0..25, a..z -> bits 26..51.

    The C++ computes ``1 << n`` in a 32-bit int, so letters beyond ``f`` are
    undefined behaviour there; flags in practice only use up to ``ee``-style
    doubled letters (see StandardBits.hpp: ``aa`` = bit 26 ... ``ee`` = bit 30).
    """
    if "A" <= letter <= "Z":
        return 1 << (ord(letter) - ord("A"))
    if "a" <= letter <= "z":
        return 1 << (26 + ord(letter) - ord("a"))
    raise ValueError(f"illegal flag letter {letter!r}")


class Reader:
    def __init__(self, text: str, filename: str = "<string>"):
        # Area files are LF in the repo; normalise CRLF defensively so a Windows
        # checkout with autocrlf behaves like the Linux server.
        self.text = text.replace("\r\n", "\n")
        self.pos = 0
        self.filename = filename
        self.diagnostics: list[Diagnostic] = []

    @classmethod
    def from_path(cls, path: Path) -> "Reader":
        return cls(path.read_text(encoding="latin-1"), path.name)

    # -- primitives ---------------------------------------------------------
    def getc(self) -> str:
        if self.pos >= len(self.text):
            self.pos = len(self.text) + 1  # so that a following ungetc lands on EOF
            return EOF
        c = self.text[self.pos]
        self.pos += 1
        return c

    def ungetc(self) -> None:
        self.pos -= 1

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < len(self.text) else EOF

    @property
    def line(self) -> int:
        import bisect

        if not hasattr(self, "_newlines"):
            self._newlines = [i for i, ch in enumerate(self.text) if ch == "\n"]
        return bisect.bisect_left(self._newlines, min(self.pos, len(self.text))) + 1

    @property
    def at_eof(self) -> bool:
        return self.pos >= len(self.text)

    def error(self, message: str) -> AreaParseError:
        return AreaParseError(message, self.filename, self.line)

    def bug(self, message: str) -> None:
        self.diagnostics.append(Diagnostic(self.filename, self.line, message))

    def skip_ws(self) -> None:
        """``skip_ws`` (db.cpp:1241)."""
        while self.pos < len(self.text) and self.text[self.pos] in _WS:
            self.pos += 1

    # -- fread_* ports ------------------------------------------------------
    def read_letter(self) -> str:
        """``fread_letter`` (db.cpp:1254): next non-whitespace char."""
        self.skip_ws()
        return self.getc()

    def read_number(self) -> int:
        """``fread_number`` (db.cpp:1267).

        Optional sign, digits required. ``a|b`` adds. Consumes a single
        trailing space; any other terminator is pushed back.
        """
        self.skip_ws()
        c = self.getc()
        sign = False
        if c == "+":
            c = self.getc()
        elif c == "-":
            sign = True
            c = self.getc()
        if not _isdigit(c):
            raise self.error(f"fread_number: bad format (got {c!r})")
        n = 0
        while _isdigit(c):
            n = n * 10 + int(c)
            c = self.getc()
        if sign:
            n = -n
        if c == "|":
            n += self.read_number()
        elif c != " ":
            self.ungetc()
        return n

    def read_flag(self) -> int:
        """``fread_flag`` (db.cpp:1356).

        Letters (each letter one bit, runs of the same letter count once) and/or
        a decimal number; ``|`` adds another flag value.
        """
        self.skip_ws()
        c = self.getc()
        n = 0
        if not _isdigit(c):
            while _isalpha(c):
                last = c
                n += flag_bit(c)
                c = self.getc()
                while c == last:
                    c = self.getc()
        num = 0
        while _isdigit(c):
            num = num * 10 + int(c)
            c = self.getc()
        n += num
        if c == "|":
            n += self.read_flag()
        elif c != " ":
            self.ungetc()
        return n

    def read_string(self) -> str:
        """``fread_string`` (db.cpp:1389): text up to ``~`` (or EOF).

        The C++ turns ``\\n`` into ``\\n\\r`` for telnet; we keep plain ``\\n``.
        """
        self.skip_ws()
        end = self.text.find("~", self.pos)
        if end < 0:
            s, self.pos = self.text[self.pos:], len(self.text)
        else:
            s, self.pos = self.text[self.pos:end], end + 1
        return s.replace("\r", "")

    def read_string_eol(self) -> str:
        """``fread_string_eol`` (db.cpp:1406): rest of line, newline consumed."""
        self.skip_ws()
        end = self.text.find("\n", self.pos)
        if end < 0:
            s, self.pos = self.text[self.pos:], len(self.text)
        else:
            s, self.pos = self.text[self.pos:end], end + 1
        return s

    def read_to_eol(self) -> str:
        """``fread_to_eol`` (db.cpp:1422). Returns the discarded text (stripped),
        which in #RESETS lines is a human comment worth keeping."""
        start = self.pos
        c = self.getc()
        while c not in ("\n", "\r", EOF):
            c = self.getc()
        rest = self.text[start:min(self.pos - 1, len(self.text))]
        c = self.getc()
        while c in ("\n", "\r"):
            c = self.getc()
        self.ungetc()
        return rest.strip()

    def read_word(self) -> str:
        """``try_fread_word`` (db.cpp:1438): whitespace-delimited word, or a
        quoted word if a quote char appears. Raises at EOF (fatal in C++)."""
        self.skip_ws()
        word: list[str] = []
        quote = ""
        while True:
            c = self.getc()
            if c == EOF:
                raise self.error("fread_word: unexpected end of file")
            if not quote and c in ("'", '"'):
                quote = c
                continue
            if (c == quote) if quote else (c in _WS):
                if c in _WS:
                    self.ungetc()
                return "".join(word)
            word.append(c)

    def read_spnumber(self) -> int | str:
        """``try_fread_spnumber`` (db.cpp:1310): a spell slot number, or a
        ``~``-terminated spell name. Names are returned as strings because
        resolving them needs the C++ skill table (resolved later, if at all)."""
        self.skip_ws()
        c = self.getc()
        if not _isdigit(c):
            if c in ("'", '"'):
                raise self.error("fread_spnumber: quoted spell names not allowed, use spellname~ instead")
            self.ungetc()
            return self.read_string()
        n = 0
        while _isdigit(c):
            n = n * 10 + int(c)
            c = self.getc()
        if c not in (" ", "~"):
            self.ungetc()
        return n
