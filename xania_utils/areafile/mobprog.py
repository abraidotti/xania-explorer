"""Parser for MOBprogram ``.prg`` files (``MProg::read_program``, MProgLoader.cpp:76).

Format: one or more ``>trigger_prog args~`` + ``script~`` blocks, ended by ``|``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .reader import Reader

# MProgLoader.cpp name_to_type
TRIGGERS = [
    "in_file_prog", "act_prog", "speech_prog", "rand_prog", "fight_prog", "hitprcnt_prog",
    "death_prog", "entry_prog", "greet_prog", "all_greet_prog", "give_prog", "bribe_prog",
]


@dataclass
class MobProg:
    trigger: str
    args: str
    lines: list[str]


def parse_prg(r: Reader) -> list[MobProg]:
    progs: list[MobProg] = []
    while True:
        c = r.read_letter()
        if c == ">":
            trigger = r.read_word().lower()
            if trigger not in TRIGGERS:
                raise r.error(f"mobprog type error {trigger!r}")
            if trigger == "in_file_prog":
                raise r.error("mobprog contains a call to file which is not supported yet.")
            args = r.read_string()
            script = r.read_string()
            lines = [ln for ln in script.split("\n") if ln.strip()]
            if not lines:
                raise r.error("mobprog contains no script!")
            progs.append(MobProg(trigger, args, lines))
        elif c == "|":
            if not progs:
                raise r.error("mobprog empty file.")
            return progs
        else:
            raise r.error("mobprog syntax error.")


def parse_prg_file(path: Path) -> list[MobProg]:
    return parse_prg(Reader.from_path(path))
