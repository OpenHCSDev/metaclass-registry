"""A class lists its whole family from the class graph, each member once, in declaration order."""

from metaclass_registry.descendants import Descendants


class Root(Descendants):
    pass


class Left(Root):
    pass


class Right(Root):
    pass


class Both(Left, Right):
    pass


class LeftLeaf(Left):
    pass


def test_descendants_walk_depth_first_in_declaration_order_without_repeats() -> None:
    assert Root.descendants() == (Root, Left, Both, LeftLeaf, Right)
    assert Right.descendants() == (Right, Both)
    assert LeftLeaf.descendants() == (LeftLeaf,)
