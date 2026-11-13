"""Class-owned handlers, composed along the value's C3 MRO."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from typing import Any, ClassVar, TypeVar

Handler = TypeVar("Handler", bound=Callable[..., Any])
Value = TypeVar("Value")


def handles(*classes: type) -> Callable[[Handler], Handler]:
    """Declare the nominal cases handled by a consumer method."""

    def decorate(handler: Handler) -> Handler:
        handler.__handled_classes__ = classes  # type: ignore[attr-defined]
        return handler

    return decorate


class MroDispatch:
    """Invoke specific handlers before base handlers; consumer overrides win.

    The method declarations are the authority. No global registry, registration
    order, or event-name roster participates in dispatch. A diamond ancestor is
    visited once by Python's MRO. A returned replacement flows to later handlers;
    ``DISCARD`` ends the pipeline without returning a value to its caller.
    """

    _handler_declarations: ClassVar[tuple[tuple[str, tuple[type, ...]], ...]] = ()
    _handler_names: ClassVar[dict[type, tuple[str, ...]]] = {}
    DISCARD: ClassVar[object] = object()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Select effective declarations once, including unannotated overrides
        # which suppress an inherited handler. Keep names rather than bound
        # methods: each invocation still borrows its own instance's behavior.
        methods: dict[str, Any] = {}
        for owner in cls.__mro__:
            for name, method in vars(owner).items():
                methods.setdefault(name, method)
        cls._handler_declarations = tuple(
            (name, classes)
            for name, method in methods.items()
            if (classes := getattr(method, "__handled_classes__", ()))
        )
        cls._handler_names = {}

    @classmethod
    def handler_names_for(cls, value_type: type) -> Iterator[str]:
        """Resolve a declaration directly; instance dispatch uses the same lookup."""
        return iter(cls.resolved_handler_names(value_type))

    @classmethod
    def resolved_handler_names(cls, value_type: type) -> tuple[str, ...]:
        """The handlers this consumer declares for a value type, most specific first.

        The consumer's declarations and the value type's MRO are both fixed when their
        classes are created, so the pair is resolved once and every dispatch reads it.
        """
        try:
            return cls._handler_names[value_type]
        except KeyError:
            names = cls._handler_names[value_type] = tuple(
                name
                for capability in value_type.__mro__
                for name, classes in cls._handler_declarations
                if capability in classes
            )
            return names

    @classmethod
    def handler_for(cls, value_type: type) -> Callable[..., Any]:
        """The most specific class-level handler declared for ``value_type``."""
        handler: Callable[..., Any] = getattr(cls, next(cls.handler_names_for(value_type)))
        return handler

    def handlers_for(self, value: Any) -> Iterator[Callable[..., Any]]:
        for name in self.handler_names_for(type(value)):
            yield getattr(self, name)

    async def dispatch(self, value: Value, *args: Any, **kwargs: Any) -> Value | None:
        handlers = tuple(self.handlers_for(value))
        if not handlers:
            return value
        return await self.consume_handlers(value, handlers, *args, **kwargs)

    async def consume_handlers(
        self,
        value: Value,
        handlers: Iterable[Handler],
        *args: Any,
        **kwargs: Any,
    ) -> Value | None:
        """Consume the selected declarations inside the consumer's resource lifetime."""
        for handler in handlers:
            replacement = await handler(value, *args, **kwargs)
            if replacement is self.DISCARD:
                return None
            value = self.replace_value(value, replacement)
        return value

    def dispatch_sync(self, value: Value, *args: Any, **kwargs: Any) -> Value | None:
        """Consume saved presentation facts without introducing an event loop."""
        return self.consume_handlers_sync(value, self.handlers_for(value), *args, **kwargs)

    def consume_handlers_sync(
        self,
        value: Value,
        handlers: Iterable[Handler],
        *args: Any,
        **kwargs: Any,
    ) -> Value | None:
        for handler in handlers:
            replacement = handler(value, *args, **kwargs)
            if replacement is self.DISCARD:
                return None
            value = self.replace_value(value, replacement)
        return value

    @staticmethod
    def replace_value(value: Value, replacement: Value | None) -> Value:
        if replacement is None:
            return value
        if type(replacement) is not type(value):
            raise TypeError("A dispatch replacement must preserve event identity")
        return replacement
