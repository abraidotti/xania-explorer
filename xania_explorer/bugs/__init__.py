"""Bug checks: defects in Xania's code, area data and content, re-detected on every build.

Each check is stateless. Code checks look for a specific pattern in the C++ source, so a branch that fixes
the bug shows it as fixed; data and content checks look at the loaded world. Nothing is stored between
builds.

Statuses:
- ``present``: the defect is there and is being triggered (code) or has occurrences (data/content)
- ``latent``: the faulty code is there but no current data triggers it (it will crash when some does)
- ``fixed``: the faulty code pattern is gone
- ``clean``: a data/content check with no occurrences
- ``unknown``: the source file needed for a code check isn't in the checkout
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..areafile.world import World

KINDS = ["code", "data", "content"]
SEVERITIES = ["crash", "wrong-behaviour", "cosmetic"]
SEVERITY_LABEL = {"crash": "crash risk", "wrong-behaviour": "wrong behaviour", "cosmetic": "cosmetic"}
OPEN = {"present", "latent"}


@dataclass
class Occurrence:
    where: str  # human-readable location, e.g. "Midgaard (room #3001)" or "fight.cpp:787"
    detail: str
    area: str = ""  # area short name, when the occurrence belongs to one
    file: str = ""  # source/area file, relative to the Xania checkout
    line: int = 0


@dataclass
class BugCheck:
    id: str  # "<kind>.<name>"
    title: str
    kind: str  # code | data | content
    severity: str  # crash | wrong-behaviour | cosmetic
    explain: str  # Markdown: what goes wrong and why
    remedy: str  # Markdown: how to fix it (code checks include a patch)
    detect: Callable[[World], "Detection"]


@dataclass
class Detection:
    status: str
    occurrences: list[Occurrence] = field(default_factory=list)
    note: str = ""  # e.g. "no data triggers it today"


@dataclass
class BugResult:
    check: BugCheck
    detection: Detection

    @property
    def status(self) -> str:
        return self.detection.status

    @property
    def open(self) -> bool:
        return self.status in OPEN

    @property
    def anchor(self) -> str:
        return "bug-" + self.check.id.replace(".", "-")


def run_checks(world: World) -> list[BugResult]:
    from ..assess import common as C
    from .checks import CHECKS

    def compute(w: World) -> list[BugResult]:
        return [BugResult(c, _detect(c, w)) for c in CHECKS]

    return C.cached(world, "bugs", compute)


def _detect(check: BugCheck, world: World) -> Detection:
    """Run one check in isolation: a check that can't run (missing source, a model failing) is 'unknown'."""
    try:
        return check.detect(world)
    except Exception as e:  # noqa: BLE001
        return Detection("unknown", note=f"couldn't run on this checkout ({type(e).__name__}: {e})")
