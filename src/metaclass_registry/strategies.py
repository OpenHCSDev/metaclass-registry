"""Strategy-family mixins for ``AutoRegisterMeta`` registries.

Each mixin derives a family's registry key from one declaration on its concrete
members (an enum member, a nominal value type, or a context predicate plus
inheritance) and selects members from the registry, so callers never keep
dispatch tables beside the family.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Hashable, Iterable, Mapping, MutableMapping
from dataclasses import dataclass, field
from enum import Enum
from functools import cache
from typing import Any, ClassVar, Generic, TypeGuard, TypeVar, cast

from .core import (
    AutoRegisterMeta,
    LazyDiscoveryDict,
    RegistryConfig,
    RegistryFamily,
    RegistryKeyAttribute,
    extract_key_from_class_name,
)

_EnumT = TypeVar("_EnumT", bound=Enum)
_MemberT = TypeVar("_MemberT")
_ContextT = TypeVar("_ContextT")
_StrategyT = TypeVar("_StrategyT", bound="EnumKeyedStrategyMixin[Any]")
_TypeStrategyT = TypeVar("_TypeStrategyT", bound="NominalTypeKeyedStrategyMixin")
_ContextStrategyT = TypeVar(
    "_ContextStrategyT",
    bound="MostDerivedContextStrategyMixin[Any]",
)
ContextStrategyTypes = tuple[type[_ContextStrategyT], ...]


NominalTypeMember = type[Any] | tuple[type[Any], ...]


_FAMILY_PROJECTION_RESETS: list[Callable[[], None]] = []
_ProjectionT = TypeVar("_ProjectionT", bound=Callable[..., Any])


def _family_projection(function: _ProjectionT) -> _ProjectionT:
    """Memoize a registry-derived view until the next family member is declared."""
    projection = cache(function)
    _FAMILY_PROJECTION_RESETS.append(projection.cache_clear)
    return cast(_ProjectionT, projection)


def _invalidate_family_projections() -> None:
    for reset in _FAMILY_PROJECTION_RESETS:
        reset()


class RegisteredStrategyTypesMixin(Generic[_MemberT]):
    """Shared projection of an AutoRegisterMeta registry into concrete classes."""

    __registry__: ClassVar[Mapping[Any, type[Any]]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _invalidate_family_projections()

    @classmethod
    @_family_projection
    def registered_strategy_types(cls) -> tuple[type[_MemberT], ...]:
        """Return registered concrete strategy classes."""
        return tuple(
            dict.fromkeys(cast(type[_MemberT], item) for item in cls.__registry__.values())
        )


def enum_key_from_class(name: str, cls: type[EnumKeyedStrategyMixin[Any]]) -> Hashable | None:
    """Return the enum-value registry key declared directly on one strategy."""
    del name
    member = cls.__dict__.get(cls.__enum_member_attr__)
    if isinstance(member, Enum):
        value: Hashable = member.value
        return value
    return None


class StrategyLabelRegistryMixin:
    """Shared AutoRegister protocol for strategy roots keyed by strategy_label."""

    __registry_key__ = RegistryKeyAttribute.STRATEGY_LABEL.value
    __skip_if_no_key__ = True
    __registry_family__ = RegistryFamily(RegistryKeyAttribute.STRATEGY_LABEL)
    strategy_label: ClassVar[str | None] = None


class EnumKeyedStrategyMixin(Generic[_EnumT]):
    """Mixin for AutoRegisterMeta ABC families keyed by enum member values.

    Concrete strategies declare the enum member they implement. The mixin
    derives the JSON-safe registry key before AutoRegisterMeta registers the
    concrete class, avoiding repeated ``label = enum.value`` boilerplate.
    """

    __registry_key__ = RegistryKeyAttribute.STRATEGY_LABEL.value
    __skip_if_no_key__ = True
    __registry_family__ = RegistryFamily(RegistryKeyAttribute.STRATEGY_LABEL)
    __enum_member_attr__: ClassVar[str] = "strategy_key"
    __registry__: ClassVar[Mapping[Any, type[Any]]]
    __key_extractor__: ClassVar[Any]
    strategy_label: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _invalidate_family_projections()
        if "__key_extractor__" not in cls.__dict__:
            cls.__key_extractor__ = staticmethod(enum_key_from_class)

    @classmethod
    def for_enum_member(cls: type[_StrategyT], member: _EnumT) -> _StrategyT:
        """Instantiate the registered strategy for an enum member."""
        strategy_type = cls.strategy_type_for_enum_member(member)
        return cast(_StrategyT, strategy_type())

    @classmethod
    @_family_projection
    def strategy_type_for_enum_member(
        cls: type[_StrategyT],
        member: _EnumT,
    ) -> type[_StrategyT]:
        """Return the registered strategy class for an enum member."""
        return cast(type[_StrategyT], cls.__registry__[member.value])

    @classmethod
    @_family_projection
    def registered_strategy_types(
        cls: type[_StrategyT],
    ) -> tuple[type[_StrategyT], ...]:
        """Return one registered strategy class per declared enum member.

        Registry cache backends may preserve JSON-safe string forms of non-string
        enum keys alongside the original key. The enum member declared on the
        strategy is the semantic identity, so collapse aliases there.
        """
        strategy_types: dict[tuple[type[Enum], Enum] | int, type[_StrategyT]] = {}
        for strategy_type in cls.__registry__.values():
            member = strategy_type.__dict__.get(cls.__enum_member_attr__)
            key: tuple[type[Enum], Enum] | int
            if isinstance(member, Enum):
                key = (type(member), member)
            else:
                key = id(strategy_type)
            if key not in strategy_types:
                strategy_types[key] = cast(type[_StrategyT], strategy_type)
        return tuple(strategy_types.values())


class NominalTypeKeyedStrategyMixin(RegisteredStrategyTypesMixin[_TypeStrategyT]):
    """Mixin for strategies selected by nominal runtime value types.

    Concrete strategies declare their owning Python type in ``value_type``.
    The mixin derives a JSON-safe registry key from that nominal type, so
    ``AutoRegisterMeta`` never stores raw type objects as registry/cache keys.
    """

    value_type: ClassVar[NominalTypeMember | None] = None
    value_type_label: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        member = cls.value_type
        if not _is_nominal_type_member(member):
            return
        if cls.__dict__.get("value_type_label") is None:
            cls.value_type_label = _nominal_type_key(member)

    @classmethod
    def for_nominal_value(
        cls: type[_TypeStrategyT],
        value: object,
    ) -> _TypeStrategyT | None:
        """Instantiate the most specific registered strategy owning ``value``."""
        strategy_types = cls.strategy_types_for_nominal_value(value)
        return None if not strategy_types else cast(_TypeStrategyT, strategy_types[0]())

    @classmethod
    def require_nominal_value(
        cls: type[_TypeStrategyT],
        value: object,
        *,
        context: str,
    ) -> _TypeStrategyT:
        """Require an explicitly registered strategy for ``value``."""
        strategy = cls.for_nominal_value(value)
        if strategy is None:
            raise TypeError(
                f"{context} has no registered nominal strategy for "
                f"{type(value).__module__}.{type(value).__qualname__}."
            )
        return cast(_TypeStrategyT, strategy)

    @classmethod
    def strategy_types_for_nominal_value(
        cls: type[_TypeStrategyT],
        value: object,
    ) -> tuple[type[_TypeStrategyT], ...]:
        """Return registered strategy classes ordered by runtime MRO specificity."""
        value_type: Any = type(value)
        return cls.strategy_types_for_nominal_type(value_type)

    @classmethod
    @_family_projection
    def strategy_types_for_nominal_type(
        cls: type[_TypeStrategyT],
        value_type: type[Any],
    ) -> tuple[type[_TypeStrategyT], ...]:
        """Return registered strategy classes ordered by type MRO specificity."""
        return cls.order_nominal_strategy_members(
            value_type,
            cls.nominal_strategy_members(),
        )

    @classmethod
    def nominal_strategy_members(
        cls: type[_TypeStrategyT],
    ) -> Iterable[tuple[type[_TypeStrategyT], NominalTypeMember | None]]:
        """Derive nominal members from the existing registered declarations."""
        for strategy_type in cls.registered_strategy_types():
            yield strategy_type, strategy_type.value_type

    @classmethod
    def order_nominal_strategy_members(
        cls: type[_TypeStrategyT],
        value_type: type[Any],
        members: Iterable[tuple[type[_TypeStrategyT], NominalTypeMember | None]],
    ) -> tuple[type[_TypeStrategyT], ...]:
        """Order derived operation members using the family's existing MRO law."""
        value_mro = value_type.mro()
        matches: list[tuple[int, type[_TypeStrategyT]]] = []
        for strategy_type, member in members:
            if _is_nominal_type_member(member) and issubclass(value_type, member):
                distance = cls.nominal_type_distance(value_mro, member)
                matches.append((distance, strategy_type))
        matches.sort(key=lambda item: item[0])
        return tuple(strategy_type for _, strategy_type in matches)

    @staticmethod
    def nominal_type_distance(
        value_mro: list[type[Any]],
        member: NominalTypeMember,
    ) -> int:
        """Return the MRO distance from a runtime value to a registered member."""
        if isinstance(member, tuple):
            return min(
                NominalTypeKeyedStrategyMixin.nominal_type_distance(value_mro, item)
                for item in member
            )
        if member not in value_mro:
            return len(value_mro)
        return value_mro.index(member)


def _is_nominal_type_member(value: object) -> TypeGuard[NominalTypeMember]:
    if isinstance(value, type):
        return True
    return (
        isinstance(value, tuple) and bool(value) and all(isinstance(item, type) for item in value)
    )


def _nominal_type_key(value: NominalTypeMember) -> str:
    if isinstance(value, tuple):
        return "|".join(_nominal_type_key(item) for item in value)
    return f"{value.__module__}.{value.__qualname__}"


class NominalTypeStrategyFamilyMixin(NominalTypeKeyedStrategyMixin):
    """AutoRegisterMeta declaration surface for nominal-type strategy roots."""

    __registry_key__ = RegistryKeyAttribute.VALUE_TYPE_LABEL.value
    __skip_if_no_key__ = True
    __registry_family__ = RegistryFamily(RegistryKeyAttribute.VALUE_TYPE_LABEL)
    value_type: ClassVar[NominalTypeMember | None] = None
    value_type_label: ClassVar[str | None] = None


class MostDerivedContextStrategyMeta(AutoRegisterMeta):
    """Create one registry for each most-derived context strategy family."""

    REGISTRY_KEY = "strategy_key"
    FAMILY_ROOT_MARKER = "__most_derived_context_strategy_template__"

    def __new__(
        mcs: type[MostDerivedContextStrategyMeta],
        name: str,
        bases: tuple[type, ...],
        attrs: dict[str, Any],
        registry_config: RegistryConfig | None = None,
        **class_kwargs: Any,
    ) -> type:
        starts_context_family = any(
            base.__dict__.get(mcs.FAMILY_ROOT_MARKER) is True for base in bases
        )
        if starts_context_family:
            registry_key = attrs.get("__registry_key__", mcs.REGISTRY_KEY)
            key_extractor = attrs.get("__key_extractor__")
            if key_extractor is None:
                key_extractor = next(
                    (
                        getattr(base, "__key_extractor__", None)
                        for base in bases
                        if getattr(base, "__key_extractor__", None) is not None
                    ),
                    None,
                )
            registry = LazyDiscoveryDict()
            attrs["__registry__"] = registry
            attrs["__registry_key__"] = registry_key
            attrs["__skip_if_no_key__"] = True
            attrs["__registry_family__"] = RegistryFamily(registry_key)
            return super().__new__(
                mcs,
                name,
                bases,
                attrs,
                registry_config=RegistryConfig(
                    registry_dict=registry,
                    key_attribute=registry_key,
                    key_extractor=key_extractor,
                    skip_if_no_key=True,
                    registry_name=f"{name} most-derived context strategy",
                ),
                **class_kwargs,
            )
        return super().__new__(
            mcs, name, bases, attrs, registry_config=registry_config, **class_kwargs
        )


class MostDerivedContextStrategyMixin(
    RegisteredStrategyTypesMixin[Any],
    Generic[_ContextT],
    ABC,
    metaclass=MostDerivedContextStrategyMeta,
):
    """Mixin for registry families selected by context and strategy inheritance.

    Concrete strategies implement ``matches`` and express precedence through
    normal Python inheritance. Selection returns the single most-derived
    matching implementation, so callers do not need local if/elif chains,
    priority numbers, or repeated registry scans.
    """

    __registry_key__: ClassVar[str] = "strategy_key"
    __skip_if_no_key__: ClassVar[bool] = True
    __registry_family__ = RegistryFamily("strategy_key")
    __most_derived_context_strategy_template__: ClassVar[bool] = True
    strategy_key: ClassVar[Any | None] = None
    strategy_key_attr: ClassVar[str] = "strategy_key"

    @classmethod
    def for_context(
        cls: type[_ContextStrategyT],
        context: _ContextT,
        *,
        required: bool = True,
        error_subject: str | None = None,
    ) -> _ContextStrategyT | None:
        """Instantiate the single most-derived registered strategy for context."""
        owning_strategy_types = cls.owning_strategy_types(context)
        if not owning_strategy_types:
            if not required:
                return None
            raise ValueError(f"{cls._error_subject(error_subject)} requires a matching strategy.")
        if len(owning_strategy_types) != 1:
            names = tuple(
                cls._strategy_name(strategy_type) for strategy_type in owning_strategy_types
            )
            raise ValueError(
                f"{cls._error_subject(error_subject)} requires exactly one "
                f"most-derived strategy, got {names!r}."
            )
        return owning_strategy_types[0].build_for_context(context)

    @classmethod
    def owning_strategy_types(
        cls: type[_ContextStrategyT],
        context: _ContextT,
    ) -> ContextStrategyTypes[_ContextStrategyT]:
        """Return most-derived registered strategies matching ``context``."""
        matching_strategy_types = tuple(
            strategy_type
            for strategy_type in cls.registered_strategy_types()
            if strategy_type.matches_context(context)
        )
        return tuple(
            candidate_type
            for candidate_type in matching_strategy_types
            if not any(
                other_type is not candidate_type and issubclass(other_type, candidate_type)
                for other_type in matching_strategy_types
            )
        )

    @classmethod
    def _error_subject(cls, explicit_subject: str | None) -> str:
        return explicit_subject or cls.__name__

    @classmethod
    def _strategy_name(cls, strategy_type: type[_ContextStrategyT]) -> object:
        if cls.strategy_key_attr in strategy_type.__dict__:
            return strategy_type.__dict__[cls.strategy_key_attr]
        return strategy_type.__name__

    @classmethod
    def build_for_context(
        cls: type[_ContextStrategyT],
        context: _ContextT,
    ) -> _ContextStrategyT:
        """Instantiate this strategy after context selection."""
        del context
        return cls()

    @classmethod
    def matches_context(
        cls: type[_ContextStrategyT],
        context: _ContextT,
    ) -> bool:
        """Return whether this strategy owns ``context`` without custom construction."""
        return cls().matches(context)

    @abstractmethod
    def matches(self, context: _ContextT) -> bool:
        """Return whether this registered strategy owns ``context``."""


class AlwaysMatchesContextMixin(Generic[_ContextT]):
    """Mixin for terminal context strategies whose match predicate is unconditional."""

    def matches(self, context: _ContextT) -> bool:
        del context
        return True


class RegisteredLeafClassSpec(ABC, metaclass=AutoRegisterMeta):
    """Nominal declaration for generated AutoRegisterMeta leaf classes."""

    __registry_family__ = RegistryFamily("declaration_key")
    __key_extractor__ = staticmethod(extract_key_from_class_name)

    declaration_key: ClassVar[str | None] = None
    class_name: str
    base_type: type[object]

    @abstractmethod
    def class_attributes(self) -> Mapping[str, object]:
        """Return semantic class attributes for the generated leaf."""

    def declare_in(self, namespace: MutableMapping[str, object]) -> type[object]:
        """Materialize the generated leaf in ``namespace`` and return it."""
        class_name = self.class_name
        declared_type = type(
            class_name,
            (self.base_type,),
            {
                "__module__": namespace.get("__name__", self.base_type.__module__),
                **dict(self.class_attributes()),
            },
        )
        namespace[class_name] = declared_type
        return declared_type


def enum_member_with_payload(
    enum_type: type[object],
    value: object,
    *,
    payload_attribute: str,
    payload: object,
) -> object:
    """Construct an enum member while attaching one payload attribute."""
    member: Any = object.__new__(enum_type)
    member._value_ = value
    member.__dict__[payload_attribute] = payload
    return member


def str_enum_member_with_payload(
    enum_type: type[str],
    value: str,
    *,
    payload_attribute: str,
    payload: object,
) -> str:
    """Construct a string enum member while attaching one payload attribute."""
    member = str.__new__(enum_type, value)
    enum_member: Any = member
    enum_member._value_ = value
    enum_member.__dict__[payload_attribute] = payload
    return member


@dataclass(frozen=True, slots=True)
class GeneratedLeafClassSpec(RegisteredLeafClassSpec):
    """Concrete generated-leaf declaration with explicit class and base identity."""

    class_name: str
    base_type: type[object]
    attributes: Mapping[str, object] = field(default_factory=dict, kw_only=True)

    def class_attributes(self) -> Mapping[str, object]:
        """Return the declared class attributes for this generated leaf."""
        return self.attributes
