"""
```bash
ruff analyze graph src | python -m ruff_analyze_tree --zero --stat -q 99.9
```
"""

import json
import posixpath
import statistics
import sys
from collections import Counter, deque
from functools import cache
from itertools import chain

from rich.color import Color, blend_rgb
from rich.console import Console
from rich.style import Style
from rich.tree import Tree

USAGE = """
Add ruff output to script:
ruff analyze graph src | python -m ruff_analyze_tree --zero --stat -q 99.9
""".strip()

CONSOLE = Console()

GREEN = Color.parse("green")
BLUE = Color.parse("blue")
RED = Color.parse("red")

RGB_COLORS_COUNT = 256 * 256

QUANTILE_FACTOR = 100


def main() -> None:
    if sys.stdin.isatty():
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    print_zero = "--zero" in sys.argv
    print_stat = "--stat" in sys.argv

    quantile_param = (
        float(sys.argv[sys.argv.index("-q") + 1]) if "-q" in sys.argv else 95
    )
    assert 0 <= quantile_param <= 100
    quantile = quantile_param * QUANTILE_FACTOR

    data, root_module = convert(json.load(sys.stdin))
    modules_names = list(data)
    if not modules_names:
        print(USAGE, file=sys.stderr)
        sys.exit(1)
        return

    relations = Counter(chain.from_iterable(data.values()))
    relations_counters = tuple(relations.values())
    quantiles = statistics.quantiles(relations_counters, n=100 * QUANTILE_FACTOR + 1)
    top_result = int(quantiles[max(int(quantile) - 1, 0)])

    root = Tree(f"✨✨✨ [b green]{root_module} modules ✨✨✨", highlight=True)

    stack: deque[tuple[Tree, str]] = deque([(root, "")])

    for full_name in modules_names:
        package, name, is_init_module = split_package(full_name)
        relations_count = relations[full_name]
        if not (relations_count or print_zero or is_init_module):
            continue

        while True:
            node, node_full_name = stack[-1]
            if node_full_name and package != node_full_name:
                node, node_full_name = stack.pop()
                continue

            break

        next_node = node.add(
            f"{name} ({relations_count})", style=get_color(relations_count, top_result)
        )
        stack.append((next_node, join_package(package, name)))

    print()
    CONSOLE.print(root)

    if print_stat:
        CONSOLE.print()
        CONSOLE.print("Dependencies statistics:")
        CONSOLE.print(f"Arithmetic mean: {statistics.mean(relations_counters)}")
        CONSOLE.print(f"Median (middle value): {statistics.median(relations_counters)}")
        CONSOLE.print(f"Quantile ({quantile_param}%): {top_result}")


def get_color(value: int, max_value: int) -> Style:
    cross_fade = value / max_value if max_value else 0
    return _get_color(min(int(cross_fade * RGB_COLORS_COUNT), RGB_COLORS_COUNT))


@cache
def _get_color(cross_fade: int) -> Style:
    # With x0.8 red starts from 80% (0.9=70%, 0.7=90%)
    return Style(color=blend_colors(GREEN, RED, cross_fade / RGB_COLORS_COUNT * 0.8))


def blend_colors(color1: Color, color2: Color, cross_fade: float) -> Color:
    return Color.from_triplet(
        blend_rgb(color1.get_truecolor(), color2.get_truecolor(), cross_fade=cross_fade)
    )


def join_package(package: str, name: str) -> str:
    assert name, name
    if package:
        return f"{package}.{name}"

    return name


def split_package(module: str) -> tuple[str, str, bool]:
    return _split_package(module)


def _split_package(module: str, is_init_module: bool = False) -> tuple[str, str, bool]:
    chunks = module.rsplit(".", 1)
    if len(chunks) == 1:
        return "", chunks[0], is_init_module

    if chunks[-1] == "__init__":
        return _split_package(chunks[0], True)

    return chunks[0], chunks[1], is_init_module


def convert(data: dict[str, list[str]]) -> tuple[dict[str, list[str]], str]:
    files = sorted(data)
    root = posixpath.commonpath(files[:1] + files[-1:]) if len(files) > 1 else ""

    modules_map = {
        convert_module_filepath_to_package_name(root, name): [
            convert_module_filepath_to_package_name(root, dep) for dep in data[name]
        ]
        for name in sorted(files)
    }
    return modules_map, convert_module_filepath_to_package_name(
        "", posixpath.split(root)[1] or root
    )


def convert_module_filepath_to_package_name(root: str, filepath: str) -> str:
    path, _ = posixpath.splitext(filepath)
    return path.removeprefix(root).lstrip("/").replace("/", ".")


if __name__ == "__main__":
    main()
