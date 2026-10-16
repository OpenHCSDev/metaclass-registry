"""The registry owns one first build for module and package declarations."""

import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from metaclass_registry import AutoRegisterMeta, DiscoveryError, LazyDiscoveryDict, RegistryConfig
from metaclass_registry import core as registry_core
from metaclass_registry.cache import get_package_file_mtimes


@pytest.fixture(params=["module", "package"])
def scope(tmp_path, monkeypatch, request):
    name = "p54_scope_" + request.param
    support_name = name + "_support"
    registry = LazyDiscoveryDict(enable_cache=False)

    class Root(metaclass=AutoRegisterMeta):
        __registry_config__ = RegistryConfig(
            registry_dict=registry, key_attribute="key", skip_if_no_key=True,
            discovery_package=name, registry_name=name,
            discovery_recursive=request.param == "recursive",
        )
        key = None

    support = type(sys)(support_name)
    support.Root = Root
    monkeypatch.setitem(sys.modules, support_name, support)
    content = f"from {support_name} import Root\nclass Native(Root):\n    key = 'native'\n"
    if request.param == "module":
        source = tmp_path / (name + ".py")
    else:
        package = tmp_path / name
        package.mkdir()
        (package / "__init__.py").write_text("")
        source = package / "native.py"
    source.write_text(content)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    try:
        yield name, registry, source
    finally:
        for loaded in tuple(sys.modules):
            if loaded == name or loaded.startswith(name + "."):
                sys.modules.pop(loaded, None)


def test_scope_first_build_is_shared_by_concurrent_and_repeated_reads(scope, monkeypatch):
    name, registry, source = scope
    imports = []
    acquire = registry_core.import_module_preserving_root_logging

    def counted(module_name):
        imports.append(module_name)
        return acquire(module_name)

    monkeypatch.setattr(registry_core, "import_module_preserving_root_logging", counted)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = [workers.submit(registry.__getitem__, "native") for _ in range(2)]
        first, second = [result.result() for result in results]
    assert first is second
    assert tuple(registry.values()) == (first,)
    assert registry.get("native") is first
    assert imports == [name]
    assert registry._discovered
    inventory = get_package_file_mtimes(name)
    assert str(source) in inventory


@pytest.mark.parametrize("scope", ["module"], indirect=True)
def test_module_inventory_excludes_neighboring_sources(scope):
    name, registry, source = scope
    (source.parent / "neighbor.py").write_text("VALUE = 1\n")
    assert get_package_file_mtimes(name) == {str(source): source.stat().st_mtime}


@pytest.mark.parametrize("error", ["ImportError", "ValueError"])
def test_failed_scope_raises_and_does_not_publish_partial_members_as_complete(scope, error):
    name, registry, source = scope
    source.write_text(source.read_text() + f"raise {error}('broken discovery scope')\n")
    with pytest.raises((ImportError, ValueError), match="broken discovery scope"):
        tuple(registry.values())
    assert not registry._discovered
    # Import may already have registered a class; failure does not erase that fact.
    assert "native" in dict.keys(registry)


@pytest.mark.parametrize("scope", ["recursive"], indirect=True)
def test_recursive_package_initialization_errors_are_not_omitted(scope):
    name, registry, source = scope
    broken = source.parent / "broken"
    broken.mkdir()
    (broken / "__init__.py").write_text("raise ImportError('broken child package')\n")
    with pytest.raises(DiscoveryError, match=name + ".broken") as raised:
        tuple(registry.values())
    assert isinstance(raised.value.__context__, ImportError)
    assert not registry._discovered
