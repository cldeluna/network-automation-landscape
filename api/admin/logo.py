"""Logo upload handling: validate and clean an uploaded image before it is
committed (as a binary blob) to ``logos/`` in the PR.

Security posture (these files end up served by GitHub Pages on the project's
own origin, so they are treated as untrusted):

* **SVG** is XML and a real XSS vector (``<script>``, ``on*`` handlers,
  ``<foreignObject>``, external ``href``/``use``, XXE via DOCTYPE/entities). We
  parse with ``defusedxml`` (no DTD/entities/external), keep only an allowlist
  of drawing elements, drop event-handler/external/dangerous attributes, and
  re-serialize. Comments and processing instructions are dropped by the parser.
* **Raster (PNG/JPEG)** can't execute, but we still verify it actually decodes
  as the claimed format (magic bytes, not just extension), cap the dimensions
  (decompression bombs), and re-encode to strip metadata.

This is defence-in-depth; the maintainer PR review is a backstop, not the
primary control.
"""

import io
from xml.etree import ElementTree as ET

import defusedxml.ElementTree as DET
from PIL import Image

MAX_BYTES = 512 * 1024  # 512 KB — logos are small
MAX_DIM = 2000  # px, guards against decompression bombs

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

# Allowlist of SVG elements a logo legitimately needs. Anything else
# (script, foreignObject, animate/set, image, iframe, …) is dropped.
ALLOWED_SVG_TAGS = {
    "svg", "g", "defs", "title", "desc", "path", "rect", "circle", "ellipse",
    "line", "polyline", "polygon", "text", "tspan", "use", "symbol", "marker",
    "linearGradient", "radialGradient", "stop", "clipPath", "mask", "pattern",
    "switch", "metadata",
}


class LogoError(ValueError):
    """Raised when an uploaded logo is invalid or unsafe."""


def _local(tag: str) -> str:
    """Local name of a possibly namespaced tag/attr."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _clean_attrs(el) -> None:
    for name in list(el.attrib):
        local = _local(name).lower()
        val = el.attrib[name]
        low = val.lower()
        # Event handlers (onload, onclick, …).
        if local.startswith("on"):
            del el.attrib[name]
            continue
        # href / xlink:href: only internal fragment refs are safe.
        if local == "href" and not val.strip().startswith("#"):
            del el.attrib[name]
            continue
        # Dangerous values anywhere.
        if "javascript:" in low or "expression(" in low:
            del el.attrib[name]
            continue
        # Inline CSS that could fetch/import.
        if local == "style" and ("url(" in low or "@import" in low):
            del el.attrib[name]
            continue


def _clean(el) -> None:
    _clean_attrs(el)
    for child in list(el):
        if _local(child.tag) not in ALLOWED_SVG_TAGS:
            el.remove(child)
        else:
            _clean(child)


def sanitize_svg(data: bytes) -> bytes:
    """Return a sanitized SVG, or raise LogoError."""
    try:
        # forbid_dtd rejects DOCTYPE outright (kills XXE / entity expansion).
        root = DET.fromstring(data, forbid_dtd=True)
    except Exception as exc:  # noqa: BLE001 — any parse failure is a reject
        raise LogoError(f"Could not parse SVG safely: {exc}") from exc
    if _local(root.tag) != "svg":
        raise LogoError("Uploaded file is not an SVG.")
    _clean(root)
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def validate_raster(data: bytes, expected: str) -> bytes:
    """Verify the bytes decode as the expected raster format, cap size, and
    re-encode to strip metadata. ``expected`` is 'png' or 'jpeg'."""
    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()  # integrity check (leaves the image unusable)
    except Exception as exc:  # noqa: BLE001
        raise LogoError("Uploaded file is not a valid image.") from exc

    img = Image.open(io.BytesIO(data))  # reopen after verify()
    if img.format not in {"PNG", "JPEG"}:
        raise LogoError(f"Unsupported image format: {img.format}.")
    if (img.format == "PNG") != (expected == "png"):
        raise LogoError("Image content does not match its file extension.")
    if img.width > MAX_DIM or img.height > MAX_DIM:
        raise LogoError(f"Image too large ({img.width}x{img.height}); max {MAX_DIM}px.")

    buf = io.BytesIO()
    if expected == "png":
        img.convert("RGBA").save(buf, format="PNG")
    else:
        img.convert("RGB").save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def process_upload(slug: str, filename: str, data: bytes) -> tuple[str, bytes]:
    """Validate/clean an upload. Returns (logo_filename, cleaned_bytes).

    ``logo_filename`` is ``<slug>.<ext>`` (bare filename, as data.yml expects);
    the caller commits the bytes to ``logos/<logo_filename>``.
    """
    if not data:
        raise LogoError("Uploaded logo is empty.")
    if len(data) > MAX_BYTES:
        raise LogoError(f"Logo is too large ({len(data)} bytes); max {MAX_BYTES}.")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "svg":
        return f"{slug}.svg", sanitize_svg(data)
    if ext == "png":
        return f"{slug}.png", validate_raster(data, "png")
    if ext in {"jpg", "jpeg"}:
        return f"{slug}.jpg", validate_raster(data, "jpeg")
    raise LogoError(f"Unsupported logo type '.{ext}'. Use SVG, PNG, or JPG.")
