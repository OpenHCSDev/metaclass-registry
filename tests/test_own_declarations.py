"""A class reads every base's own declaration along its MRO, skipping bases that state none."""

from metaclass_registry.own_declarations import OwnDeclarations


class Root(OwnDeclarations):
    keys = ("a",)


class Left(Root):
    keys = ("b", "a")


class Right(Root):
    pass


class Both(Left, Right):
    keys = ("c",)


def test_own_declarations_follow_the_mro_and_skip_silent_bases() -> None:
    assert [base for base, _ in Both.own_declarations("keys")] == [Both, Left, Root]
    assert tuple(Both.declared_items("keys")) == ("c", "b", "a", "a")
    assert Both.declared_union("keys") == ("c", "b", "a")
    assert Both.declared_union("keys", reversed(Both.__mro__)) == ("a", "b", "c")
    assert Both.declared_union("missing") == ()
