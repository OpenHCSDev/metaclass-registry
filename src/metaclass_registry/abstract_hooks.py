"""Abstract methods enforced without ABCMeta."""

from __future__ import annotations

from typing import Any


class AbstractHooksMeta(type):
    """A class whose MRO declares an abstract method it still resolves can't be built.

    ABCMeta does the same but replaces isinstance and issubclass, which doubles their
    cost on every check. This reads the whole MRO once, at class creation, so a plain
    mixin's abstract hooks count as well as a declared base's. Assigning
    __abstractmethods__ sets the flag object.__new__ refuses on.
    """

    def __init__(
        cls, name: str, bases: tuple[type, ...], namespace: dict[str, Any], **kwargs: Any
    ) -> None:
        super().__init__(name, bases, namespace, **kwargs)
        cls.__abstractmethods__ = frozenset(
            member
            for base in cls.__mro__
            for member, value in vars(base).items()
            if getattr(value, "__isabstractmethod__", False)
            and getattr(getattr(cls, member, None), "__isabstractmethod__", False)
        )
