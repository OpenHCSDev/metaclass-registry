"""A class reads every base's own declaration along its MRO, skipping bases that state none."""

from metaclass_registry.own_declarations import OwnDeclarations


class Marker:
    pass


class Root(OwnDeclarations):
    keys = ("a",)
    root_marker = Marker()


class Left(Root):
    keys = ("b", "a")


class Right(Root):
    pass


class Both(Left, Right):
    keys = ("c",)
    both_marker = Marker()


def test_own_declarations_follow_the_mro_and_skip_silent_bases() -> None:
    assert [base for base, _ in Both.own_declarations("keys")] == [Both, Left, Root]
    assert tuple(Both.declared_items("keys")) == ("c", "b", "a", "a")
    assert Both.declared_union("keys") == ("c", "b", "a")
    assert Both.declared_union("keys", reversed(Both.__mro__)) == ("a", "b", "c")
    assert Both.declared_union("missing") == ()
    assert list(Both.declared_of(Marker)) == [Both.both_marker, Root.root_marker]
    assert list(Both.declared_of(Marker, reversed(Both.__mro__))) == [Root.root_marker, Both.both_marker]
