import pytest

from core.oxipng_level import DEFAULT_OXIPNG_LEVEL, MAX_OXIPNG_LEVEL, oxipngLevelArgs


def test_defaults():
    assert DEFAULT_OXIPNG_LEVEL == 2
    assert MAX_OXIPNG_LEVEL == 9
    assert oxipngLevelArgs(DEFAULT_OXIPNG_LEVEL) == ["-o", "2"]


@pytest.mark.parametrize("level, expected", [
    (0, ["-o", "0"]),
    (5, ["-o", "5"]),
    (6, ["-o", "6"]),
    (7, ["-o", "6", "--fast", "--zopfli", "--zi", "15"]),
    (8, ["-o", "6", "--fast", "--zopfli", "--zi", "100", "--ziwi", "15"]),
    (9, ["-o", "6", "--fast", "--zopfli", "--zi", "255", "--ziwi", "30"]),
])
def test_level_args(level, expected):
    assert oxipngLevelArgs(level) == expected


def test_out_of_range_levels_are_clamped():
    assert oxipngLevelArgs(-3) == ["-o", "0"]
    assert oxipngLevelArgs(42) == oxipngLevelArgs(MAX_OXIPNG_LEVEL)
