import pytest

from core.same_format import ALLOWED_TARGETS, DEFAULT_ROUTES, PRESETS, apply_format_settings, resolve


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


def test_presets_cover_every_routable_format():
    for name, preset in PRESETS.items():
        assert set(preset) == {"PNG", "JPEG XL", "WebP", "AVIF", "JPEG"}, name
        for fmt, settings in preset.items():
            assert isinstance(settings["lossless"], bool), (name, fmt)
            assert 0 <= settings["quality"] <= 100, (name, fmt)


def test_apply_format_settings_overwrites_shared_values():
    params = {
        "quality": 80,
        "lossless": False,
        "same_format_settings": {"WebP": {"lossless": True, "quality": 90}},
    }

    apply_format_settings(params, "WebP")

    assert params["quality"] == 90
    assert params["lossless"] is True


def test_apply_format_settings_noop_without_settings():
    params = {"quality": 80, "lossless": False}

    apply_format_settings(params, "WebP")

    assert params["quality"] == 80
    assert params["lossless"] is False


def test_apply_format_settings_noop_for_unlisted_target():
    params = {
        "quality": 80,
        "lossless": False,
        "same_format_settings": PRESETS["Quality"],
    }

    apply_format_settings(params, "Lossless JPEG Transcoding")

    assert params["quality"] == 80
    assert params["lossless"] is False
