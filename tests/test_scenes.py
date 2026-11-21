import random

import pytest

from app import scenes
from app.scenes import GENERIC_SCENES, KEYWORD_SCENES, choose_scene


@pytest.mark.parametrize("keyword,scene", list(KEYWORD_SCENES.items()))
def test_keyword_maps_to_scene_in_any_case(keyword, scene):
    assert choose_scene(keyword) == scene
    assert choose_scene(keyword.upper()) == scene
    assert choose_scene(f"A Tiny {keyword.title()} outfit") == scene


def test_keyword_scenes_match_requirements():
    assert KEYWORD_SCENES == {
        "wizard": "a magical library with floating candles",
        "vampire": "a dark castle under a red moon",
        "pumpkin": "a foggy pumpkin patch at night",
        "pirate": "a ghost ship on a stormy sea",
        "ghost": "a misty graveyard with fireflies",
    }


def test_generic_list_has_enough_entries():
    assert len(GENERIC_SCENES) >= 6
    assert len(set(GENERIC_SCENES)) == len(GENERIC_SCENES)


def test_generic_text_never_repeats_previous():
    rng = random.Random(1)
    for previous in GENERIC_SCENES:
        for _ in range(50):
            assert choose_scene("a cowboy", previous, rng) != previous


def test_generic_text_without_previous_returns_generic_scene():
    assert choose_scene("a cowboy", None, random.Random(2)) in GENERIC_SCENES


def test_last_scene_store_is_per_browser():
    assert scenes.get_last_scene("browser-x") is None
    scenes.set_last_scene("browser-x", GENERIC_SCENES[0])
    scenes.set_last_scene("browser-y", GENERIC_SCENES[1])
    assert scenes.get_last_scene("browser-x") == GENERIC_SCENES[0]
    assert scenes.get_last_scene("browser-y") == GENERIC_SCENES[1]
