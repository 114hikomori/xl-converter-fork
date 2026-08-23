from data.constants import JPEG_ALIASES

DEFAULT_ROUTES = {
    **{ext: "JPEG" for ext in JPEG_ALIASES},   # JPEG aliases re-encode back to .jpg
    "png": "PNG",
    "webp": "WebP",
    "avif": "AVIF",
    "jxl": "JPEG XL",
}

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
