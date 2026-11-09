"""The stable interface for other programs (e.g. xania-sim). Import from here, not from the modules behind it:
these names and signatures are pinned by tests/test_api.py, while everything else may change.

    from xania_explorer import api
    world = api.load_world("../xania")
    api.path(world, 3001, 3054)                    # [Step(... command="north"), ...]
    api.predict_fight(world, "knight", 10, 3062)   # FightPrediction(rounds=..., deadly=...)
"""

from __future__ import annotations

from .areafile.graph import Step, distances, entrances, path, reachable, rooms_in, steps_from
from .areafile.world import World, load_world
from .assess.difficulty import AreaProfile
from .assess.predict import FightPrediction, SpellPrediction, area_profile, predict_fight, predict_spell
from .source.names import AbilityInfo, abilities, classes, directions, pc_races

RECALL_ROOM = 3001  # VnumRooms.hpp MidgaardTemple

__all__ = [
    "RECALL_ROOM", "World", "load_world",
    "Step", "steps_from", "path", "distances", "reachable", "rooms_in", "entrances",
    "FightPrediction", "SpellPrediction", "AreaProfile", "predict_fight", "predict_spell", "area_profile",
    "AbilityInfo", "classes", "pc_races", "abilities", "directions",
]
