"""Family-level tests for metaclass_registry.strategies."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import ClassVar

import pytest

from metaclass_registry import AutoRegisterMeta
from metaclass_registry.strategies import (
    AlwaysMatchesContextMixin,
    EnumKeyedStrategyMixin,
    GeneratedLeafClassSpec,
    MostDerivedContextStrategyMixin,
    NominalTypeStrategyFamilyMixin,
    StrategyLabelRegistryMixin,
    enum_member_with_payload,
    str_enum_member_with_payload,
)


class Shape(Enum):
    SQUARE = "square"
    CIRCLE = "circle"


def test_enum_keyed_family_registers_one_member_per_declared_enum_member():
    class ShapeArea(EnumKeyedStrategyMixin[Shape], ABC, metaclass=AutoRegisterMeta):
        __enum_member_attr__ = "shape"
        shape: ClassVar[Shape | None] = None

        @abstractmethod
        def area(self, size: float) -> float: ...

    class SquareArea(ShapeArea):
        shape = Shape.SQUARE

        def area(self, size: float) -> float:
            return size * size

    class CircleArea(ShapeArea):
        shape = Shape.CIRCLE

        def area(self, size: float) -> float:
            return 3.0 * size * size

    class UnkeyedHelper(ShapeArea):
        def area(self, size: float) -> float:
            return 0.0

    assert dict(ShapeArea.__registry__) == {"square": SquareArea, "circle": CircleArea}
    assert SquareArea.strategy_label == "square"
    assert ShapeArea.strategy_type_for_enum_member(Shape.CIRCLE) is CircleArea
    assert ShapeArea.for_enum_member(Shape.SQUARE).area(2.0) == 4.0
    assert ShapeArea.registered_strategy_types() == (SquareArea, CircleArea)
    assert UnkeyedHelper not in ShapeArea.registered_strategy_types()


def test_strategy_label_registry_keys_members_by_declared_label():
    class Formatter(StrategyLabelRegistryMixin, ABC, metaclass=AutoRegisterMeta):
        @abstractmethod
        def render(self) -> str: ...

    class Plain(Formatter):
        strategy_label = "plain"

        def render(self) -> str:
            return "plain"

    assert dict(Formatter.__registry__) == {"plain": Plain}


def test_nominal_type_family_selects_most_specific_registered_type():
    class Describer(NominalTypeStrategyFamilyMixin, ABC, metaclass=AutoRegisterMeta):
        @abstractmethod
        def describe(self, value: object) -> str: ...

    class IntDescriber(Describer):
        value_type = int

        def describe(self, value: object) -> str:
            return "int"

    class BoolDescriber(Describer):
        value_type = bool

        def describe(self, value: object) -> str:
            return "bool"

    class TextDescriber(Describer):
        value_type = (str, bytes)

        def describe(self, value: object) -> str:
            return "text"

    assert IntDescriber.value_type_label == "builtins.int"
    assert TextDescriber.value_type_label == "builtins.str|builtins.bytes"
    assert set(Describer.__registry__) == {
        "builtins.int",
        "builtins.bool",
        "builtins.str|builtins.bytes",
    }
    assert Describer.strategy_types_for_nominal_value(True) == (BoolDescriber, IntDescriber)
    assert Describer.require_nominal_value(3, context="test").describe(3) == "int"
    assert Describer.require_nominal_value(b"x", context="test").describe(b"x") == "text"
    assert Describer.for_nominal_value(1.5) is None
    with pytest.raises(TypeError, match="no registered nominal strategy for builtins.float"):
        Describer.require_nominal_value(1.5, context="describe")


def test_most_derived_context_family_selects_by_inheritance_with_its_own_registry():
    class Route(MostDerivedContextStrategyMixin[int]):
        pass

    class AnyNumber(AlwaysMatchesContextMixin[int], Route):
        strategy_key = "any"

    class EvenNumber(AnyNumber):
        strategy_key = "even"

        def matches(self, context: int) -> bool:
            return context % 2 == 0

    class OtherRoute(MostDerivedContextStrategyMixin[int]):
        pass

    class OtherAny(AlwaysMatchesContextMixin[int], OtherRoute):
        strategy_key = "other-any"

    assert dict(Route.__registry__) == {"any": AnyNumber, "even": EvenNumber}
    assert dict(OtherRoute.__registry__) == {"other-any": OtherAny}
    assert type(Route.for_context(3)) is AnyNumber
    assert type(Route.for_context(4)) is EvenNumber

    class FourOnly(AnyNumber):
        strategy_key = "four"

        def matches(self, context: int) -> bool:
            return context == 4

    with pytest.raises(
        ValueError, match=r"exactly one most-derived strategy, got \('even', 'four'\)"
    ):
        Route.for_context(4)

    class Empty(MostDerivedContextStrategyMixin[int]):
        pass

    assert Empty.for_context(1, required=False) is None
    with pytest.raises(ValueError, match="routing requires a matching strategy"):
        Empty.for_context(1, error_subject="routing")


def test_generated_leaf_spec_declares_registered_leaf_in_namespace():
    class Base:
        greeting: ClassVar[str] = "base"

    namespace: dict[str, object] = {"__name__": "generated.module"}
    spec = GeneratedLeafClassSpec("Hello", Base, attributes={"greeting": "hello"})
    leaf = spec.declare_in(namespace)

    assert namespace["Hello"] is leaf
    assert issubclass(leaf, Base)
    assert leaf.greeting == "hello"
    assert leaf.__module__ == "generated.module"


def test_enum_payload_helpers_attach_one_payload_per_member():
    class Unit(str, Enum):
        def __new__(cls, value: str, scale: float):
            return str_enum_member_with_payload(
                cls, value, payload_attribute="_scale", payload=scale
            )

        METRE = ("m", 1.0)
        KILOMETRE = ("km", 1000.0)

    class Level(Enum):
        def __new__(cls, value: int, label: str):
            return enum_member_with_payload(cls, value, payload_attribute="_label", payload=label)

        LOW = (1, "low")
        HIGH = (2, "high")

    assert Unit("km") is Unit.KILOMETRE
    assert Unit.KILOMETRE == "km"
    assert Unit.KILOMETRE._scale == 1000.0
    assert Level(2) is Level.HIGH
    assert Level.LOW._label == "low"
