"""A class whose MRO still leaves an abstract hook unresolved cannot be built; a mixin's
hooks count as well as a declared base's."""

from abc import abstractmethod

import pytest

from metaclass_registry import AbstractHooksMeta


class Hook:
    @abstractmethod
    def answer(self) -> int: ...


class Contract(Hook, metaclass=AbstractHooksMeta):
    pass


class Answered(Contract):
    def answer(self) -> int:
        return 1


def test_an_unresolved_mixin_hook_refuses_construction() -> None:
    assert Contract.__abstractmethods__ == frozenset({"answer"})
    with pytest.raises(TypeError):
        Contract()


def test_a_resolved_hook_builds_and_isinstance_stays_plain() -> None:
    assert Answered().answer() == 1
    assert type(Contract) is AbstractHooksMeta
    assert isinstance(Answered(), Hook)
