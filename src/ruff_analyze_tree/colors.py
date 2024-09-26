from functools import cache

from rich.color import Color, blend_rgb
from rich.style import Style

from ruff_analyze_tree.models import User

DEEP_SKY_BLUE = Color.parse("deep_sky_blue4")
GREEN = Color.parse("green")
RED = Color.parse("red")

RGB_COLORS_COUNT = 256 * 256


def get_color(value: int, max_value: int) -> Style:
    assert User is not None
    if not value:
        return get_gray()

    cross_fade = value / max_value if max_value else 0
    return _get_color(min(int(cross_fade * RGB_COLORS_COUNT), RGB_COLORS_COUNT))


@cache
def get_gray() -> Style:
    return Style(color=DEEP_SKY_BLUE)


@cache
def _get_color(cross_fade: int) -> Style:
    # With x0.8 red starts from 80% (0.9=70%, 0.7=90%)
    return Style(color=blend_colors(GREEN, RED, cross_fade / RGB_COLORS_COUNT * 0.8))


def blend_colors(color1: Color, color2: Color, cross_fade: float) -> Color:
    return Color.from_triplet(
        blend_rgb(color1.get_truecolor(), color2.get_truecolor(), cross_fade=cross_fade)
    )
