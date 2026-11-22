import random

import pytest

from app import scenes
from app.scenes import GENERIC_SCENES, KEYWORD_SCENES, choose_scene


@pytest.mark.parametrize("keyword,options", list(KEYWORD_SCENES.items()))
def test_keyword_maps_to_one_of_its_scenes_in_any_case(keyword, options):
    assert choose_scene(keyword) in options
    assert choose_scene(keyword.upper()) in options
    assert choose_scene(f"A Tiny {keyword.title()} outfit") in options


@pytest.mark.parametrize("keyword,options", list(KEYWORD_SCENES.items()))
def test_keyword_scene_differs_from_previous(keyword, options):
    rng = random.Random(3)
    for previous in options:
        for _ in range(30):
            assert choose_scene(keyword, previous, rng) != previous


def test_keyword_scenes_match_requirements():
    assert KEYWORD_SCENES == {
        "wizard": [
            "a magical library with floating candles",
            "a starry wizard tower at midnight",
            "a bubbling potion room",
        ],
        "vampire": [
            "a dark castle under a red moon",
            "a candlelit gothic hall",
            "misty cemetery gates",
        ],
        "pumpkin": [
            "a foggy pumpkin patch at night",
            "a harvest barn with jack-o'-lanterns",
            "a moonlit cornfield",
        ],
        "pirate": [
            "a ghost ship on a stormy sea",
            "a haunted pirate cove",
            "a shipwreck under a green moon",
        ],
        "ghost": [
            "a misty graveyard with fireflies",
            "an abandoned haunted hallway",
            "a foggy old church yard",
        ],
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
