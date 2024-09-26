from collections.abc import Iterable
from typing import Hashable, TypeVar

H = TypeVar("H", bound=Hashable)


def unique(objects: Iterable[H], *, visited: set[H] | None = None) -> Iterable[H]:
    if visited is None:
        visited = set()

    return (visited.add(obj) or obj for obj in objects if obj not in visited)
