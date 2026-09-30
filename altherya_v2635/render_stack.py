"""Altherya rendering stack.

Priority:
1. resvg + SVG
2. pyvips + Pango
3. Skia
4. HTML/CSS + Playwright
5. Pillow

Import is lazy: the bot can start even when an optional renderer is not yet
available. Each future interface can explicitly choose the best backend.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Backend:
    key: str
    label: str
    priority: int

BACKENDS = (
    Backend("resvg", "resvg + SVG", 1),
    Backend("vips", "pyvips + Pango", 2),
    Backend("skia", "Skia", 3),
    Backend("playwright", "HTML/CSS + Playwright", 4),
    Backend("pillow", "Pillow", 5),
)

def availability() -> dict[str, bool]:
    out = {}
    for b in BACKENDS:
        try:
            if b.key == "resvg":
                import resvg_py  # noqa
            elif b.key == "vips":
                import pyvips  # noqa
                import pangocffi  # noqa
            elif b.key == "skia":
                import skia  # noqa
            elif b.key == "playwright":
                import playwright  # noqa
            elif b.key == "pillow":
                from PIL import Image  # noqa
            out[b.key] = True
        except Exception:
            out[b.key] = False
    return out

def render_svg(svg: str, output: str | Path) -> Path:
    """Primary renderer: SVG -> PNG through resvg."""
    import resvg_py
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(resvg_py.svg_to_bytes(svg_string=svg))
    return output
