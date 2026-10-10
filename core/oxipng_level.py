"""Optimization level for lossless PNG (oxipng).

Levels 0-6 are oxipng's own presets (`-o N`). Levels 7-9 keep preset 6 and add
Zopfli, with the same Zopfli settings as the "PNG Optimization" mode. Zopfli is
much slower than the presets, so these levels trade time for file size.
"""

DEFAULT_OXIPNG_LEVEL = 2    # oxipng's own default preset
MAX_OXIPNG_LEVEL = 9

_ZOPFLI_ARGS = {
    7: ["--zi", "15"],
    8: ["--zi", "100", "--ziwi", "15"],
    9: ["--zi", "255", "--ziwi", "30"],
}


def oxipngLevelArgs(level: int) -> list[str]:
    """Returns the oxipng option tokens for a level. Out-of-range levels are clamped."""
    level = max(0, min(int(level), MAX_OXIPNG_LEVEL))
    if level <= 6:
        return ["-o", str(level)]
    return ["-o", "6", "--fast", "--zopfli", *_ZOPFLI_ARGS[level]]
