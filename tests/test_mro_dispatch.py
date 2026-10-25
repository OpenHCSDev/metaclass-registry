"""Behaviour of class-owned handlers composed along the value's MRO."""

import ast
import asyncio
from typing import Any

from metaclass_registry.mro_dispatch import MroDispatch, handles


class NodeKinds(MroDispatch):
    """Records which handlers ran, most specific first."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    @handles(ast.AST)
    def any_node(self, node: ast.AST) -> None:
        self.seen.append("AST")

    @handles(ast.stmt)
    def statement(self, node: ast.stmt) -> None:
        self.seen.append("stmt")

    @handles(ast.Return)
    def return_(self, node: ast.Return) -> None:
        self.seen.append("Return")


def test_handlers_run_in_mro_order_most_specific_first() -> None:
    kinds = NodeKinds()
    node = ast.Return(value=None)

    assert kinds.dispatch_sync(node) is node
    assert kinds.seen == ["Return", "stmt", "AST"]
    assert NodeKinds.handler_for(ast.Return) is NodeKinds.return_


def test_base_class_registration_catches_subclass_nodes() -> None:
    kinds = NodeKinds()

    kinds.dispatch_sync(ast.Pass())

    assert kinds.seen == ["stmt", "AST"]
    assert list(NodeKinds.handler_names_for(ast.If)) == ["statement", "any_node"]


def test_value_without_a_declared_handler_passes_through() -> None:
    kinds = NodeKinds()
    value = object()

    assert kinds.dispatch_sync(value) is value
    assert asyncio.run(kinds.dispatch(value)) is value
    assert kinds.seen == []


class Gate(MroDispatch):
    def __init__(self) -> None:
        self.reached_base = False

    @handles(ast.Name)
    def drop_private(self, node: ast.Name) -> Any:
        return self.DISCARD if node.id.startswith("_") else None

    @handles(ast.expr)
    def base(self, node: ast.expr) -> None:
        self.reached_base = True


def test_discard_ends_the_pipeline_and_returns_none() -> None:
    gate = Gate()

    assert gate.dispatch_sync(ast.Name(id="_hidden")) is None
    assert gate.reached_base is False


def test_none_keeps_the_value_and_later_handlers_still_run() -> None:
    gate = Gate()
    node = ast.Name(id="visible")

    assert gate.dispatch_sync(node) is node
    assert gate.reached_base is True


class AsyncGate(MroDispatch):
    @handles(ast.Name)
    async def drop(self, node: ast.Name) -> Any:
        return self.DISCARD


def test_async_dispatch_honours_discard() -> None:
    assert asyncio.run(AsyncGate().dispatch(ast.Name(id="x"))) is None


class Renamer(MroDispatch):
    @handles(ast.Name)
    def rename(self, node: ast.Name) -> ast.Name:
        return ast.Name(id=node.id.upper())

    @handles(ast.expr)
    def observe(self, node: ast.expr) -> None:
        assert isinstance(node, ast.Name) and node.id == "X"


def test_replacement_flows_to_later_handlers() -> None:
    result = Renamer().dispatch_sync(ast.Name(id="x"))

    assert isinstance(result, ast.Name) and result.id == "X"


class BadReplacement(MroDispatch):
    @handles(ast.Name)
    def swap(self, node: ast.Name) -> Any:
        return ast.Constant(value=1)


def test_replacement_must_preserve_the_value_type() -> None:
    try:
        BadReplacement().dispatch_sync(ast.Name(id="x"))
    except TypeError:
        return
    raise AssertionError("type-changing replacement was accepted")


class QuietStatements(NodeKinds):
    def statement(self, node: ast.stmt) -> None:  # unannotated override suppresses
        self.seen.append("never")


def test_unannotated_override_suppresses_inherited_handler() -> None:
    kinds = QuietStatements()

    kinds.dispatch_sync(ast.Pass())

    assert kinds.seen == ["AST"]
