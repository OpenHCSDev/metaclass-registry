"""A class family's members, read from the class graph instead of a hand-kept registry."""

from __future__ import annotations


class Descendants:
    """A class lists itself and every class below it, each once, depth first in the order
    the subclasses were declared."""

    @classmethod
    def descendants(cls) -> tuple[type, ...]:
        pending: list[type] = [cls]
        found: dict[type, None] = {}
        while pending:
            owner = pending.pop()
            if owner not in found:
                found[owner] = None
                pending.extend(reversed(owner.__subclasses__()))
        return tuple(found)
