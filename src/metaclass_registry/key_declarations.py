"""Key declarations independent of any UI toolkit: which command a key invokes, under which
input mode, with its title and summary. A toolkit projects these into its own bindings."""

from __future__ import annotations

import inspect
import re
from abc import ABC, ABCMeta, abstractmethod
from typing import Callable, ClassVar, Generic, Iterator, TypeVar

NodeT = TypeVar("NodeT", contravariant=True)


class InputMode:
    """Which input mode keys are declared under; a toolkit's editing engine subclasses it."""

    modal = False


class ModalInputMode(InputMode):
    """An input mode whose keys are commands until a key enters text."""

    modal = True


class KeyDeclarationType(ABCMeta):
    """A key-declaring class, including declarations supplied by a metaclass."""

    def permits_key_overlap(cls, other: KeyDeclarationType) -> bool:
        """An explicitly declared alternative may share this declaration's key."""
        return False


class KeyInvocation(ABC):
    """The concrete command a binding invokes, independent of its active mode."""

    @staticmethod
    def qualified(declaration: type | Callable[..., object]) -> str:
        return f"{declaration.__module__}.{declaration.__qualname__}"

    @abstractmethod
    def key_identity(self) -> str: ...

    @abstractmethod
    def key_title(self) -> str: ...

    @abstractmethod
    def key_summary(self) -> str: ...

    @abstractmethod
    def key_system(self) -> bool: ...

    def binding_identity(self, mode: type[InputMode]) -> str:
        return self.in_mode(self.key_identity(), mode)

    @staticmethod
    def in_mode(identity: str, mode: type) -> str:
        return f"{identity}:{KeyInvocation.qualified(mode)}"

    def visible_for_focus(self, focused: bool) -> bool:
        """Local commands follow their declaration's actual prior-focus membership."""
        return focused

    def permits_invocation_overlap(self, other: KeyInvocation) -> bool:
        return False

    def overlaps_declaration(self, other: KeyDeclarationType) -> bool:
        return False


class KeyTitle:
    """Human text derived from the declaration rather than a second title roster."""

    def __get__(self, instance: object, owner: type[KeyDeclaration]) -> str:
        return owner.default_title()


class KeyDeclaration(KeyInvocation, Generic[NodeT], metaclass=KeyDeclarationType):
    """Shared metadata for application actions and native editor commands.

    Each provider retains its existing family registry. This view discovers the
    provider declarations through inheritance; no menu supplies their names.
    """

    title = KeyTitle()
    system: ClassVar[bool] = False
    _declared: ClassVar[list[type[KeyDeclaration]]] = []

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        KeyDeclaration._declared.append(cls)

    @classmethod
    def default_title(cls) -> str:
        return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", cls.__name__).capitalize()

    @classmethod
    def identity(cls) -> str:
        return cls.qualified(cls)

    @classmethod
    def binding_id(cls, mode: type) -> str:
        return cls.binding_id_for(cls, mode)

    @staticmethod
    def binding_id_for(declaration: type | Callable[..., object], mode: type) -> str:
        """Class and native callable declarations use the same mode-qualified identity."""
        return KeyInvocation.in_mode(KeyInvocation.qualified(declaration), mode)

    def key_identity(self) -> str:
        return type(self).identity()

    def key_title(self) -> str:
        return self.title

    def key_summary(self) -> str:
        return self.summary()

    def key_system(self) -> bool:
        return self.system

    def permits_invocation_overlap(self, other: KeyInvocation) -> bool:
        return other.overlaps_declaration(type(self))

    def overlaps_declaration(self, other: KeyDeclarationType) -> bool:
        return type(self).permits_key_overlap(other)

    @abstractmethod
    def __call__(self, node: NodeT) -> object: ...

    @classmethod
    def summary(cls) -> str:
        return inspect.cleandoc(cls.__doc__ or "")

    @classmethod
    def declarations(cls) -> Iterator[type[KeyDeclaration]]:
        """Project each key family from the declaration owner's registry."""
        return (member for member in KeyDeclaration._declared
                if issubclass(member, cls) and not inspect.isabstract(member))
