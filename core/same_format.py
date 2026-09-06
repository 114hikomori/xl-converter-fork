from data.constants import JPEG_ALIASES

DEFAULT_ROUTES = {
    **{ext: "JPEG" for ext in JPEG_ALIASES},   # JPEG aliases re-encode back to .jpg
    "png": "PNG",
    "webp": "WebP",
    "avif": "AVIF",
    "jxl": "JPEG XL",
}

# Simple presets for "Same Format" mode: per-format encoder settings for
# each need. Values are anchored to the measured quality-vs-size runs in
# _infographics_for_preset/ - "Quality" keeps every format in its
# lossless/visually-lossless band (AVIF has no lossless mode, so its best
# measured setting is used), "Balanced" targets the shareable-copy role,
# and "Small" targets the smallest-good-quality role. "quality" is ignored
# when "lossless" is True (PNG, JPEG XL, WebP) and for formats without a
# lossless option (AVIF, JPEG).
PRESETS = {
    "Quality": {
        "PNG": {"lossless": True, "quality": 90},
        "JPEG XL": {"lossless": True, "quality": 90},
        "WebP": {"lossless": True, "quality": 90},
        "AVIF": {"lossless": False, "quality": 90},
        "JPEG": {"lossless": False, "quality": 90},
    },
    "Balanced": {
        "PNG": {"lossless": False, "quality": 90},
        "JPEG XL": {"lossless": False, "quality": 90},
        "WebP": {"lossless": False, "quality": 90},
        "AVIF": {"lossless": False, "quality": 80},
        "JPEG": {"lossless": False, "quality": 80},
    },
    "Small": {
        "PNG": {"lossless": False, "quality": 80},
        "JPEG XL": {"lossless": False, "quality": 80},
        "WebP": {"lossless": False, "quality": 80},
        "AVIF": {"lossless": False, "quality": 70},
        "JPEG": {"lossless": False, "quality": 70},
    },
}

PRESET_NAMES = ("Quality", "Balanced", "Small", "Custom")

# Targets a route may point at. Mirrors the regular "Format / Mode" entries;
# worker-handled special modes are deliberately excluded.
ALLOWED_TARGETS = (
    "PNG",
    "JPEG",
    "WebP",
    "AVIF",
    "JPEG XL",
    "Lossless JPEG Transcoding",
)


def resolve(src_ext: str, routes: dict | None = None) -> str | None:
    """Resolve a source extension into a concrete conversion pipeline.

    Used by the "Same Format" mode: each file is re-encoded by the pipeline
    assigned to its extension, so the result keeps the source format unless
    a route intentionally points elsewhere (e.g. JPEG -> Lossless JPEG
    Transcoding produces .jxl).

    Args:
        src_ext - source extension, lowercase, without a leading dot
        routes - optional user overrides ({extension: target}); unknown or
                 disallowed targets are ignored and fall back to the default

    Returns:
        A "Format / Mode" entry, or None when the source cannot be routed
        (the caller is expected to skip such files).
    """
    ext = src_ext.lower() if src_ext else ""
    target = None

    if routes:
        candidate = routes.get(ext)
        if candidate in ALLOWED_TARGETS:
            target = candidate

    if target is None:
        target = DEFAULT_ROUTES.get(ext)

    return target

def apply_format_settings(params: dict, target: str) -> None:
    """Overwrite the shared quality/lossless params with the per-format
    values resolved for "Same Format" mode.

    No-op when the settings are absent (e.g. an older config) or when the
    target carries none (e.g. "Lossless JPEG Transcoding", which ignores
    both values).
    """
    settings = params.get("same_format_settings")
    if not settings:
        return

    fmt = settings.get(target)
    if not fmt:
        return

    params["quality"] = fmt["quality"]
    params["lossless"] = fmt["lossless"]
