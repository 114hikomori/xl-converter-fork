import pytest

from core.same_format import ALLOWED_TARGETS, DEFAULT_ROUTES, resolve


@pytest.mark.parametrize("src_ext, expected", [
    ("png", "PNG"),
    ("jpg", "JPEG"),
    ("jpeg", "JPEG"),
    ("jfif", "JPEG"),
    ("jpe", "JPEG"),
    ("webp", "WebP"),
    ("avif", "AVIF"),
    ("jxl", "JPEG XL"),
])
def test_resolve_defaults(src_ext, expected):
    assert resolve(src_ext) == expected


@pytest.mark.parametrize("src_ext", [
    "bmp",
    "tiff",
    "gif",
    "apng",
    "",
])
def test_resolve_unroutable_returns_none(src_ext):
    assert resolve(src_ext) is None


def test_resolve_none_ext():
    assert resolve(None) is None


def test_resolve_route_override_to_transcoding():
    routes = {"jpg": "Lossless JPEG Transcoding"}
    assert resolve("jpg", routes) == "Lossless JPEG Transcoding"


def test_resolve_route_override_applies_to_all_jpeg_aliases():
    routes = {"jpeg": "Lossless JPEG Transcoding"}
    assert resolve("jpeg", routes) == "Lossless JPEG Transcoding"
    assert resolve("jpg", routes) == "JPEG"   # only the overridden alias changes


def test_resolve_ignores_forbidden_targets():
    for bad in ("Same Format", "Smallest Lossless", "JPEG Reconstruction"):
        assert resolve("png", {"png": bad}) == "PNG"


def test_resolve_ignores_unknown_targets():
    assert resolve("png", {"png": "FLIF"}) == "PNG"
    assert resolve("webp", {"avif": "PNG"}) == "WebP"   # unrelated override


def test_all_defaults_are_allowed_targets():
    for target in DEFAULT_ROUTES.values():
        assert target in ALLOWED_TARGETS
