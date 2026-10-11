from pathlib import Path

import pytest

from core.path_limits import findProblems


def params(fmt, out_dir="D:\\out", keep=False, routes=None):
    settings = {
        "format": fmt,
        "custom_output_dir": True,
        "custom_output_dir_path": out_dir,
        "keep_dir_struct": keep,
    }
    if routes is not None:
        settings["same_format_routes"] = routes
    return settings


def source_of_length(length, folder="D:\\src"):
    """Returns a source path string of exactly `length` characters."""
    name = "a.jpg"
    return f"{folder}\\" + "x" * (length - len(folder) - 1 - len(name)) + name


def out_dir_of_length(length):
    return "D:\\" + "o" * (length - 3)


@pytest.mark.parametrize("fmt", ["JPEG", "JPEG XL", "WebP"])
def test_source_path_limit_259_ok_260_fails(fmt):
    anchor = Path("D:\\src")
    assert findProblems([(source_of_length(259), anchor)], params(fmt)) == []
    problems = findProblems([(source_of_length(260), anchor)], params(fmt))
    assert [p.index for p in problems] == [0]
    assert "source path" in problems[0].reason


@pytest.mark.parametrize("fmt, ok_len, fail_len", [("JPEG", 242, 243), ("JPEG XL", 242, 243), ("WebP", 241, 242)])
def test_output_folder_limit(fmt, ok_len, fail_len):
    anchor = Path("D:\\src")
    short_src = [("D:\\src\\a.jpg", anchor)]
    assert findProblems(short_src, params(fmt, out_dir_of_length(ok_len))) == []
    problems = findProblems(short_src, params(fmt, out_dir_of_length(fail_len)))
    assert [p.index for p in problems] == [0]
    assert "output folder" in problems[0].reason


@pytest.mark.parametrize("fmt, stem_ok, stem_fail", [("PNG", 251, 252), ("AVIF", 250, 251)])
def test_output_name_limit(fmt, stem_ok, stem_fail):
    ext = {"PNG": "png", "AVIF": "avif"}[fmt]
    anchor = Path("D:\\src")
    ok = [(f"D:\\src\\{'s' * stem_ok}.{'jpg'}", anchor)]
    fail = [(f"D:\\src\\{'s' * stem_fail}.{'jpg'}", anchor)]
    assert findProblems(ok, params(fmt)) == []
    problems = findProblems(fail, params(fmt))
    assert [p.index for p in problems] == [0]
    assert "output name" in problems[0].reason


@pytest.mark.parametrize("fmt, stem, failing_indexes", [
    ("PNG", 246, []),
    ("PNG", 247, [10, 11]),
    ("PNG", 248, list(range(1, 12))),
    ("AVIF", 245, []),
    ("AVIF", 246, [10, 11]),
    ("AVIF", 247, list(range(1, 12))),
])
def test_same_name_files_are_numbered_in_list_order(fmt, stem, failing_indexes):
    anchor = Path("D:\\src")
    items = [(f"D:\\src\\d{i:02d}\\{'s' * stem}.jpg", anchor) for i in range(12)]
    problems = findProblems(items, params(fmt))
    assert [p.index for p in problems] == failing_indexes


def test_untracked_and_unlimited_cases_are_not_checked():
    anchor = Path("D:\\src")
    long_src = [("D:\\" + "f" * 590 + "\\a.png", anchor)]
    assert findProblems(long_src, params("PNG")) == []
    assert findProblems(long_src, params("AVIF")) == []
    assert findProblems(long_src, params("Smallest Lossless")) == []


def test_same_format_routes_png_source_without_limits():
    anchor = Path("D:\\src")
    long_png = [("D:\\" + "f" * 590 + "\\a.png", anchor)]
    assert findProblems(long_png, params("Same Format", routes={"png": "PNG"})) == []
