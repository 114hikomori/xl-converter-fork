"""Pre-conversion checks for path and file name lengths.

The limits were measured on Windows with LongPathsEnabled=1:
- JPEG (cjpegli), JPEG XL (cjxl) and WebP: the source path can be at most 259 characters.
- JPEG, JPEG XL and WebP: the output folder can be at most 242 characters (WebP: 241).
- Every format: the output file name can be at most 255 characters (NTFS limit).
AVIF (avifenc) and PNG (oxipng) showed no path-length limit in the tests.
Routes that are not listed in RULES are not checked, and neither is a settings dict without a format.
"""

from dataclasses import dataclass
from pathlib import Path

from core import same_format
from core.pathing import getOutputDir

NAME_MAX = 255

# target -> (output extension, source path max, output folder max); None means no limit was measured
RULES = {
    "PNG": ("png", None, None),
    "AVIF": ("avif", None, None),
    "JPEG": ("jpg", 259, 242),
    "JPEG XL": ("jxl", 259, 242),
    "WebP": ("webp", 259, 241),
    "Lossless JPEG Transcoding": ("jxl", 259, 242),
    "JPEG Reconstruction": ("jpg", 259, 242),
}


@dataclass(frozen=True)
class Problem:
    index: int
    path: str
    reason: str


def _target(params: dict, src_ext: str):
    if params.get("format") == "Same Format":
        return same_format.resolve(src_ext, params.get("same_format_routes"))
    return params.get("format")


def findProblems(items, params: dict) -> list[Problem]:
    """Returns the items that would fail with the current settings, in list order.

    items: (absolute path, anchor path) tuples, as InputTab.getItems() returns them.
    Duplicate output names are counted in list order the way Rename numbers them ("name (1).ext").
    Files already in the output folder are not counted.
    """
    if params.get("format") is None:
        return []

    problems = []
    claimed = {}
    for index, (abs_path, anchor_path) in enumerate(items):
        src = Path(abs_path)
        target = _target(params, src.suffix[1:].lower())
        if target not in RULES:
            continue
        ext, input_max, dir_max = RULES[target]

        src_len = len(str(src))
        if input_max is not None and src_len > input_max:
            problems.append(Problem(index, str(src), f"source path is {src_len} characters ({target} reads at most {input_max})"))
            continue

        anchor = Path(anchor_path) if anchor_path else src.parent
        out_dir = Path(getOutputDir(
            src.parent,
            anchor,
            params.get("custom_output_dir", False),
            params.get("custom_output_dir_path", ""),
            params.get("keep_dir_struct", False),
        ))
        dir_len = len(str(out_dir))
        if dir_max is not None and dir_len > dir_max:
            problems.append(Problem(index, str(src), f"output folder is {dir_len} characters ({target} writes at most {dir_max})"))
            continue

        key = (str(out_dir).lower(), src.stem.lower(), ext)
        number = claimed.get(key, 0)
        name = f"{src.stem}.{ext}" if number == 0 else f"{src.stem} ({number}).{ext}"
        if len(name) > NAME_MAX:
            problems.append(Problem(index, str(src), f"output name is {len(name)} characters (limit {NAME_MAX})"))
            continue
        claimed[key] = number + 1

    return problems
