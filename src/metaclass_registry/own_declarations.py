"""Declarations each class states in its own body, read along the class's MRO."""

from __future__ import annotations

from collections.abc import Iterable, Iterator


class OwnDeclarations:
    """A class reads what each of its bases declared for itself under one attribute name.

    Inheritance answers "the nearest declaration"; these answer "every class's own
    declaration", the question a capability composed through several parents asks.
    """

    @classmethod
    def own_declarations(cls, name: str, bases: Iterable[type] | None = None) -> Iterator[tuple[type, object]]:
        """Each base, in MRO order unless ``bases`` gives another order or scope, with the
        value it declares in its own body; bases that declare nothing are skipped."""
        for base in cls.__mro__ if bases is None else bases:
            if name in base.__dict__:
                yield base, base.__dict__[name]

    @classmethod
    def declared_items(cls, name: str, bases: Iterable[type] | None = None) -> Iterator[object]:
        """Every item of every base's own declared collection, in that order."""
        for _, declared in cls.own_declarations(name, bases):
            yield from declared

    @classmethod
    def declared_of[Kind](cls, kind: type[Kind], bases: Iterable[type] | None = None) -> Iterator[Kind]:
        """Every value of ``kind`` each base declares in its own body, in that order."""
        for base in cls.__mro__ if bases is None else bases:
            for value in base.__dict__.values():
                if isinstance(value, kind):
                    yield value

    @classmethod
    def declared_union(cls, name: str, bases: Iterable[type] | None = None) -> tuple[object, ...]:
        """The declared items, each once, nearest declaration first."""
        return tuple(dict.fromkeys(cls.declared_items(name, bases)))
