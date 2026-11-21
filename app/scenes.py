"""Spooky scene selection for the costume image.

Five costumes have a fixed scene. Any other costume gets a random generic
scene that differs from the visitor's previous one (Requirements 5.5-5.7).
"""
from __future__ import annotations

import random

KEYWORD_SCENES: dict[str, str] = {
    "wizard": "a magical library with floating candles",
    "vampire": "a dark castle under a red moon",
    "pumpkin": "a foggy pumpkin patch at night",
    "pirate": "a ghost ship on a stormy sea",
    "ghost": "a misty graveyard with fireflies",
}

GENERIC_SCENES: list[str] = [
    "an abandoned haunted mansion at midnight",
    "a creepy forest with twisted trees and glowing eyes",
    "a candlelit crypt with cobwebs",
    "a moonlit witch's cottage in a swamp",
    "a spooky carnival with a broken ferris wheel",
    "a dusty attic full of old portraits and cobwebs",
    "a cursed bridge over a misty river",
]

# Last scene used per Browser_ID. In memory only, so it resets on restart.
_last_scene: dict[str, str] = {}


def get_last_scene(browser_id: str) -> str | None:
    return _last_scene.get(browser_id)


def set_last_scene(browser_id: str, scene: str) -> None:
    _last_scene[browser_id] = scene


def choose_scene(
    costume_text: str,
    previous: str | None = None,
    rng: random.Random | None = None,
) -> str:
    """Return the scene for a costume. Keywords match case-insensitively."""
    text = costume_text.lower()
    for keyword, scene in KEYWORD_SCENES.items():
        if keyword in text:
            return scene
    rng = rng or random.Random()
    # Exclude the previous scene so the visitor never sees it twice in a row.
    options = [s for s in GENERIC_SCENES if s != previous]
    return rng.choice(options)
