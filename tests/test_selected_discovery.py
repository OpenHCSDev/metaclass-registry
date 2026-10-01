"""Partial selection uses the same import, registration and complete discovery."""

import importlib
import sys

import pytest

from metaclass_registry import AutoRegisterMeta, LazyDiscoveryDict, RegistryConfig


def test_selected_discovery_then_full_discovery_has_one_registration_authority(
    tmp_path, monkeypatch
):
    registry = LazyDiscoveryDict(enable_cache=False)

    class Root(metaclass=AutoRegisterMeta):
        __registry_config__ = RegistryConfig(
            registry_dict=registry, key_attribute="key", skip_if_no_key=True,
            discovery_package="selected_plugins", registry_name="selected plugins",
        )
        key = None

    support = type(sys)("selected_plugins_support")
    support.Root = Root
    monkeypatch.setitem(sys.modules, support.__name__, support)
    package = tmp_path / "selected_plugins"
    package.mkdir()
    (package / "__init__.py").write_text("")
    for name in ("one", "two"):
        (package / f"{name}.py").write_text(
            "from selected_plugins_support import Root\n"
            f"class Plugin(Root):\n    key = '{name}'\n"
        )
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        registry.discover_matching(lambda name: name == "selected_plugins.one")
        selected = importlib.import_module("selected_plugins.one").Plugin
        assert tuple(dict.values(registry)) == (selected,)
        assert not registry._discovered
        assert "selected_plugins.two" not in sys.modules
        assert registry["one"] is selected
        assert registry._discovered
        assert set(registry) == {"one", "two"}
    finally:
        for name in tuple(sys.modules):
            if name == "selected_plugins" or name.startswith("selected_plugins."):
                monkeypatch.delitem(sys.modules, name)


@pytest.mark.parametrize("error", ["ImportError", "ValueError"])
def test_selected_import_failure_is_not_absence(tmp_path, monkeypatch, error):
    registry = LazyDiscoveryDict(enable_cache=False)

    class Root(metaclass=AutoRegisterMeta):
        __registry_config__ = RegistryConfig(
            registry_dict=registry, key_attribute="key", skip_if_no_key=True,
            discovery_package="failed_selection", registry_name="failed selection",
        )
        key = None

    package = tmp_path / "failed_selection"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "broken.py").write_text(f"raise {error}('selected import failed')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        with pytest.raises((ImportError, ValueError), match="selected import failed"):
            registry.discover_matching(lambda name: True)
        assert not registry._discovered
    finally:
        for name in tuple(sys.modules):
            if name == "failed_selection" or name.startswith("failed_selection."):
                monkeypatch.delitem(sys.modules, name)
