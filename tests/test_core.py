"""Tests for metaclass_registry.core module."""

from abc import abstractmethod
import pytest
from enum import Enum
from metaclass_registry import (
    AutoRegisterMeta,
    RegistryConfig,
    RegistryFamily,
    RegistryKeyAttribute,
    RegisteredEnumMeta,
    LazyDiscoveryDict,
    SecondaryRegistryDict,
    SecondaryRegistry,
    PRIMARY_KEY,
    DuplicateRegistryKeyError,
    is_same_declaration,
    extract_key_from_class_name,
    extract_key_from_handler_suffix,
    extract_key_from_backend_suffix,
    make_suffix_extractor,
)


class TestLazyDiscoveryDict:
    """Test LazyDiscoveryDict functionality."""

    def test_init(self):
        """Test LazyDiscoveryDict initialization."""
        registry = LazyDiscoveryDict()
        assert not registry._discovered
        assert registry._enable_cache is True
        assert len(registry) == 0

    def test_init_without_cache(self):
        """Test LazyDiscoveryDict initialization with caching disabled."""
        registry = LazyDiscoveryDict(enable_cache=False)
        assert not registry._enable_cache

    def test_basic_dict_operations(self):
        """Test basic dictionary operations."""
        registry = LazyDiscoveryDict(enable_cache=False)

        # Add items directly
        registry['test'] = object
        assert 'test' in registry
        assert len(registry) == 1
        assert registry['test'] is object

    def test_get_with_default(self):
        """Test get() method with default value."""
        registry = LazyDiscoveryDict(enable_cache=False)
        result = registry.get('nonexistent', 'default')
        assert result == 'default'


class TestSecondaryRegistryDict:
    """Test SecondaryRegistryDict functionality."""

    def test_init(self):
        """Test SecondaryRegistryDict initialization."""
        primary = LazyDiscoveryDict()
        secondary = SecondaryRegistryDict(primary)
        assert secondary._primary_registry is primary

    def test_auto_discovery_trigger(self):
        """Test that accessing secondary registry triggers primary discovery."""
        primary = LazyDiscoveryDict(enable_cache=False)
        primary._discovered = False
        secondary = SecondaryRegistryDict(primary)

        # Mock _discover method
        discover_called = []

        def mock_discover():
            discover_called.append(True)
            primary._discovered = True

        primary._discover = mock_discover

        # Access secondary registry - should trigger discovery
        _ = len(secondary)
        assert len(discover_called) == 1


class TestRegistryConfig:
    """Test RegistryConfig dataclass."""

    def test_minimal_config(self):
        """Test RegistryConfig with minimal required fields."""
        registry_dict = {}
        config = RegistryConfig(
            registry_dict=registry_dict,
            key_attribute='_key',
        )
        assert config.registry_dict is registry_dict
        assert config.key_attribute == '_key'
        assert config.skip_if_no_key is False
        assert config.log_registration is True
        assert config.registry_name == "plugin"

    def test_full_config(self):
        """Test RegistryConfig with all fields."""
        registry_dict = {}
        secondary = SecondaryRegistry(
            registry_dict={},
            key_source=PRIMARY_KEY,
            attr_name='_handler',
        )

        def key_extractor(name, cls):
            return name.lower()

        config = RegistryConfig(
            registry_dict=registry_dict,
            key_attribute='_key',
            key_extractor=key_extractor,
            skip_if_no_key=True,
            secondary_registries=[secondary],
            log_registration=False,
            registry_name='test plugin',
            discovery_package='test.package',
            discovery_recursive=True,
        )

        assert config.skip_if_no_key is True
        assert config.log_registration is False
        assert config.registry_name == 'test plugin'
        assert config.discovery_package == 'test.package'
        assert config.discovery_recursive is True


class TestAutoRegisterMeta:
    """Test AutoRegisterMeta metaclass."""

    def test_simple_registration(self):
        """Test simple class registration with explicit key."""

        # Create a plugin system with auto-registration
        class Plugin(metaclass=AutoRegisterMeta):
            __registry_key__ = 'plugin_name'
            plugin_name = None

        # Plugin should have auto-created registry
        assert hasattr(Plugin, '__registry__')
        assert isinstance(Plugin.__registry__, LazyDiscoveryDict)

        # Create a concrete plugin
        class MyPlugin(Plugin):
            plugin_name = 'my_plugin'

        # Should be registered
        assert 'my_plugin' in Plugin.__registry__
        assert Plugin.__registry__['my_plugin'] is MyPlugin

    def test_skip_abstract_class(self):
        """Test that abstract classes are not registered."""
        from abc import abstractmethod

        class AbstractPlugin(metaclass=AutoRegisterMeta):
            __registry_key__ = 'name'
            name = None

            @abstractmethod
            def run(self):
                pass

        # Abstract class should not be in registry
        assert len(AbstractPlugin.__registry__) == 0

    def test_skip_base_class(self):
        """Test that base class without key is not registered."""

        class BasePlugin(metaclass=AutoRegisterMeta):
            __registry_key__ = 'name'
            name = None

        # Base class with name=None should not be registered
        assert len(BasePlugin.__registry__) == 0

    def test_registry_inheritance(self):
        """Test that child classes inherit parent registry."""

        class BasePlugin(metaclass=AutoRegisterMeta):
            __registry_key__ = 'name'
            name = None

        class ChildPlugin(BasePlugin):
            pass

        # Child should inherit parent's registry
        assert hasattr(BasePlugin, '__registry__')
        # ChildPlugin should be able to access the registry through the parent
        assert BasePlugin.__registry__ is not None

    def test_secondary_registry(self):
        """Test secondary registry registration."""
        HANDLERS = {}

        class Plugin(metaclass=AutoRegisterMeta):
            __registry_key__ = 'name'
            __secondary_registries__ = [
                SecondaryRegistry(
                    registry_dict=HANDLERS,
                    key_source=PRIMARY_KEY,
                    attr_name='handler_class',
                )
            ]
            name = None
            handler_class = None

        class DummyHandler:
            pass

        class MyPlugin(Plugin):
            name = 'my_plugin'
            handler_class = DummyHandler

        # Primary registration
        assert 'my_plugin' in Plugin.__registry__

        # Secondary registration
        assert 'my_plugin' in HANDLERS
        assert HANDLERS['my_plugin'] is DummyHandler

    def test_key_extractor(self):
        """Test custom key extraction function."""

        def extract_key(name, cls):
            """Extract 'foo' from 'FooPlugin'."""
            if name.endswith('Plugin'):
                return name[:-6].lower()
            return None

        class Plugin(metaclass=AutoRegisterMeta):
            __registry_key__ = 'name'
            __key_extractor__ = extract_key
            name = None

        class MyPlugin(Plugin):
            pass  # name=None, should use extractor

        # Should be registered with extracted key
        assert 'my' in Plugin.__registry__
        assert Plugin.__registry__['my'] is MyPlugin

    def test_skip_if_no_key(self):
        """Test skip_if_no_key behavior."""

        class Plugin(metaclass=AutoRegisterMeta):
            __registry_key__ = 'name'
            __skip_if_no_key__ = True
            name = None

        class PluginWithoutName(Plugin):
            pass  # name=None

        # Should not be registered (skipped)
        assert len(Plugin.__registry__) == 0

    def test_require_key(self):
        """Test that missing key raises error when skip_if_no_key=False."""

        with pytest.raises(ValueError, match="must have name attribute"):

            class Plugin(metaclass=AutoRegisterMeta):
                __registry_key__ = 'name'
                __skip_if_no_key__ = False
                name = None

            class PluginWithoutName(Plugin):
                pass  # This should raise


class TestSuffixExtractors:
    """Test suffix extraction helper functions."""

    def test_extract_key_from_class_name(self):
        """Test class-name key extractor."""

        class DummyClass:
            pass

        result = extract_key_from_class_name('ImageXpressHandler', DummyClass)
        assert result == 'ImageXpressHandler'

    def test_extract_handler_suffix(self):
        """Test extract_key_from_handler_suffix."""

        class DummyClass:
            pass

        result = extract_key_from_handler_suffix('ImageXpressHandler', DummyClass)
        assert result == 'imagexpress'

        result = extract_key_from_handler_suffix('FooBarHandler', DummyClass)
        assert result == 'foobar'

        result = extract_key_from_handler_suffix('NoSuffix', DummyClass)
        assert result == 'nosuffix'

    def test_extract_backend_suffix(self):
        """Test extract_key_from_backend_suffix."""

        class DummyClass:
            pass

        result = extract_key_from_backend_suffix('DiskStorageBackend', DummyClass)
        assert result == 'diskstorage'

        result = extract_key_from_backend_suffix('MemoryBackend', DummyClass)
        assert result == 'memory'

    def test_make_suffix_extractor(self):
        """Test make_suffix_extractor factory function."""

        class DummyClass:
            pass

        extractor = make_suffix_extractor('Manager')
        result = extractor('FileManager', DummyClass)
        assert result == 'file'

        result = extractor('DatabaseManager', DummyClass)
        assert result == 'database'

        result = extractor('NoSuffix', DummyClass)
        assert result == 'nosuffix'


class TestAutoConfiguration:
    """Test automatic registry configuration."""

    def test_auto_registry_name_derivation(self):
        """Test automatic derivation of registry name from class name."""

        class StorageBackend(metaclass=AutoRegisterMeta):
            __registry_key__ = 'backend_type'
            backend_type = None

        class DiskStorage(StorageBackend):
            backend_type = 'disk'

        # Registry name should be auto-derived from class name
        # "StorageBackend" -> "storage backend"
        # This is tested indirectly through the logging/config system

    def test_auto_registry_creation(self):
        """Test that __registry__ is automatically created."""

        class MyPlugin(metaclass=AutoRegisterMeta):
            __registry_key__ = 'name'
            name = None

        # Registry should be auto-created and attached to class
        assert hasattr(MyPlugin, '__registry__')
        assert isinstance(MyPlugin.__registry__, LazyDiscoveryDict)

    def test_implicit_registry_does_not_infer_package_discovery(self, monkeypatch):
        """In-module roots never scan a package without an owner declaration."""

        def unexpected_discovery(*args, **kwargs):
            raise AssertionError("implicit registry attempted package discovery")

        monkeypatch.setattr(
            "metaclass_registry.discovery.discover_registry_classes",
            unexpected_discovery,
        )

        class Plugin(metaclass=AutoRegisterMeta):
            __registry_family__ = RegistryFamily("name")
            name = None

        class ImportedPlugin(Plugin):
            name = "imported"

        assert Plugin.__registry__._config.discovery_package is None
        assert Plugin.__registry__["imported"] is ImportedPlugin

    def test_nominal_registry_config_owns_root_and_exact_class_identity(self):
        """A root-owned config supplies registration and discovery semantics once."""

        registry = LazyDiscoveryDict(enable_cache=False)
        config = RegistryConfig(
            registry_dict=registry,
            key_attribute="name",
            skip_if_no_key=True,
            registry_name="configured plugin",
        )

        class Plugin(metaclass=AutoRegisterMeta):
            __registry_config__ = config
            name = None

        class ConfiguredPlugin(Plugin):
            name = "configured"

        assert Plugin.__registry_config__ is config
        assert Plugin.__registry__ is registry
        assert "__registry_key__" not in Plugin.__dict__
        assert ConfiguredPlugin.__registry_config__ is config
        assert Plugin.__registry__["configured"] is ConfiguredPlugin

    def test_nominal_registry_config_compares_registry_authority_by_identity(self):
        """Equal registry mappings are not interchangeable semantic authorities."""

        configured_registry = LazyDiscoveryDict(enable_cache=False)
        config = RegistryConfig(
            registry_dict=configured_registry,
            key_attribute="name",
        )

        with pytest.raises(ValueError, match="must be the registry owned"):

            class Plugin(metaclass=AutoRegisterMeta):
                __registry_config__ = config
                __registry__ = LazyDiscoveryDict(enable_cache=False)

    def test_nominal_registry_config_rejects_ambiguous_multiple_inheritance(self):
        """One class cannot inherit two unrelated registry ownership roots."""

        class Left(metaclass=AutoRegisterMeta):
            __registry_config__ = RegistryConfig(
                registry_dict=LazyDiscoveryDict(enable_cache=False),
                key_attribute="left_name",
                skip_if_no_key=True,
            )

        class Right(metaclass=AutoRegisterMeta):
            __registry_config__ = RegistryConfig(
                registry_dict=LazyDiscoveryDict(enable_cache=False),
                key_attribute="right_name",
                skip_if_no_key=True,
            )

        with pytest.raises(TypeError, match="multiple registry configuration"):

            class Ambiguous(Left, Right):
                pass

    def test_registered_enum_meta_registers_enum_leaves(self):
        """Test enum families can also use AutoRegisterMeta registration."""

        class BaseVariant(str, Enum, metaclass=RegisteredEnumMeta):
            __registry_key__ = "__name__"

        class ConcreteVariant(BaseVariant):
            ALPHA = "alpha"

        assert "ConcreteVariant" in BaseVariant.__registry__
        assert BaseVariant.__registry__["ConcreteVariant"] is ConcreteVariant

    def test_registry_family_declares_root_configuration(self):
        """Test nominal registry family declaration without legacy boilerplate."""

        class Plugin(metaclass=AutoRegisterMeta):
            __registry_family__ = RegistryFamily(
                RegistryKeyAttribute.STRATEGY_LABEL,
                registry_name='test strategy',
            )
            strategy_label = None

        class MyPlugin(Plugin):
            strategy_label = 'mine'

        assert Plugin.__registry_key__ == 'strategy_label'
        assert Plugin.__skip_if_no_key__ is True
        assert Plugin.__registry_name__ == 'test strategy'
        assert 'mine' in Plugin.__registry__
        assert Plugin.__registry__['mine'] is MyPlugin

    def test_registry_family_respects_legacy_overrides(self):
        """Test explicit legacy attributes override family defaults."""

        with pytest.raises(ValueError, match="must have strategy_label attribute"):

            class Plugin(metaclass=AutoRegisterMeta):
                __registry_family__ = RegistryFamily(
                    RegistryKeyAttribute.STRATEGY_LABEL
                )
                __skip_if_no_key__ = False
                strategy_label = None

            class MissingKeyPlugin(Plugin):
                pass

    def test_autoregister_root_inherits_protocol_config_from_mixin(self):
        """Test roots can inherit registry protocol config without copying fields."""

        class RegisteredMethodStrategy:
            __registry_key__ = 'method'
            __skip_if_no_key__ = True
            method = None

        class MethodStrategy(RegisteredMethodStrategy, metaclass=AutoRegisterMeta):
            pass

        class MeanStrategy(MethodStrategy):
            method = 'mean'

        assert hasattr(MethodStrategy, '__registry__')
        assert MethodStrategy.__registry_key__ == 'method'
        assert MethodStrategy.__skip_if_no_key__ is True
        assert 'mean' in MethodStrategy.__registry__
        assert MethodStrategy.__registry__['mean'] is MeanStrategy

    def test_inherited_protocol_config_creates_distinct_root_registries(self):
        """Test one protocol mixin can seed multiple independent registry roots."""

        class RegisteredMethodStrategy:
            __registry_key__ = 'method'
            __skip_if_no_key__ = True
            method = None

        class SpatialStrategy(RegisteredMethodStrategy, metaclass=AutoRegisterMeta):
            pass

        class ProjectionStrategy(RegisteredMethodStrategy, metaclass=AutoRegisterMeta):
            pass

        class MeanSpatialStrategy(SpatialStrategy):
            method = 'mean'

        class MaxProjectionStrategy(ProjectionStrategy):
            method = 'max_projection'

        assert SpatialStrategy.__registry__ is not ProjectionStrategy.__registry__
        assert SpatialStrategy.__registry__ == {'mean': MeanSpatialStrategy}
        assert ProjectionStrategy.__registry__ == {
            'max_projection': MaxProjectionStrategy
        }


class TestComplexScenarios:
    """Test complex real-world scenarios."""

    def test_multi_level_inheritance(self):
        """Test multi-level class inheritance."""

        class BasePlugin(metaclass=AutoRegisterMeta):
            __registry_key__ = 'name'
            name = None

        class MiddlePlugin(BasePlugin):
            name = None  # Explicitly set to None

        class ConcretePlugin(MiddlePlugin):
            name = 'concrete'

        # All should share same registry
        assert hasattr(BasePlugin, '__registry__')
        assert 'concrete' in BasePlugin.__registry__

    def test_multiple_plugins(self):
        """Test registering multiple plugins."""

        class Plugin(metaclass=AutoRegisterMeta):
            __registry_key__ = 'name'
            name = None

        class PluginA(Plugin):
            name = 'a'

        class PluginB(Plugin):
            name = 'b'

        class PluginC(Plugin):
            name = 'c'

        # All should be registered
        assert len(Plugin.__registry__) == 3
        assert set(Plugin.__registry__.keys()) == {'a', 'b', 'c'}

    def test_secondary_registry_without_attr(self):
        """Test secondary registry when class doesn't have the attribute."""
        HANDLERS = {}

        class Plugin(metaclass=AutoRegisterMeta):
            __registry_key__ = 'name'
            __secondary_registries__ = [
                SecondaryRegistry(
                    registry_dict=HANDLERS,
                    key_source=PRIMARY_KEY,
                    attr_name='handler_class',
                )
            ]
            name = None
            handler_class = None

        class MyPlugin(Plugin):
            name = 'my_plugin'
            # handler_class not set (None)

        # Primary registration should succeed
        assert 'my_plugin' in Plugin.__registry__

        # Secondary registration should be skipped (handler_class is None)
        assert 'my_plugin' not in HANDLERS


def _plugin_family():
    class Plugin(metaclass=AutoRegisterMeta):
        __registry_key__ = "name"
        name = None

    return Plugin


class TestOneClassPerKey:
    """A registry key names one class; it never silently changes hands."""

    def test_different_class_on_occupied_key_raises_naming_both(self):
        Plugin = _plugin_family()

        class PluginA(Plugin):
            name = "same"

        with pytest.raises(DuplicateRegistryKeyError) as error:

            class PluginB(Plugin):
                name = "same"

        message = str(error.value)
        assert "'same'" in message
        assert "PluginA" in message and "PluginB" in message
        assert "plugin" in message
        assert Plugin.__registry__["same"] is PluginA

    def test_subclass_inheriting_a_declared_key_raises(self):
        Plugin = _plugin_family()

        class PluginA(Plugin):
            name = "a"

        with pytest.raises(DuplicateRegistryKeyError):

            class PluginChild(PluginA):
                pass

        assert Plugin.__registry__["a"] is PluginA

    def test_same_class_object_registers_again_without_error(self):
        Plugin = _plugin_family()

        class PluginA(Plugin):
            name = "a"

        config = RegistryConfig(
            registry_dict=Plugin.__registry__, key_attribute="name", registry_name="plugin"
        )
        assert AutoRegisterMeta._register_class(PluginA, "a", config) is None
        assert Plugin.__registry__ == {"a": PluginA}

    def test_same_declaration_created_again_takes_the_key(self):
        """A reload or a second run of one class statement re-creates the class."""
        Plugin = _plugin_family()

        def declare():
            class PluginA(Plugin):
                name = "a"

            return PluginA

        first = declare()
        second = declare()

        assert first is not second
        assert is_same_declaration(first, second)
        assert Plugin.__registry__ == {"a": second}

    def test_reloaded_module_takes_its_keys_back(self, tmp_path, monkeypatch):
        import importlib
        import sys

        (tmp_path / "test_pkg_reloaded.py").write_text(
            "from metaclass_registry import AutoRegisterMeta\n"
            "class Plugin(metaclass=AutoRegisterMeta):\n"
            "    __registry_key__ = 'name'\n"
            "    __registry__ = REGISTRY\n"
            "    name = None\n"
            "class PluginA(Plugin):\n"
            "    name = 'a'\n"
        )
        monkeypatch.syspath_prepend(str(tmp_path))
        import builtins

        registry = {}
        monkeypatch.setattr(builtins, "REGISTRY", registry, raising=False)
        module = importlib.import_module("test_pkg_reloaded")
        first = module.PluginA
        module = importlib.reload(module)

        assert module.PluginA is not first
        assert registry == {"a": module.PluginA}
        sys.modules.pop("test_pkg_reloaded", None)

    def test_slots_dataclass_registers_its_final_class(self):
        from dataclasses import dataclass

        Plugin = _plugin_family()

        @dataclass(frozen=True, slots=True)
        class PluginA(Plugin):
            name = "a"
            value: int = 0

        assert Plugin.__registry__ == {"a": PluginA}
        assert PluginA.__slots__ == ("value",)

    def test_same_name_in_another_scope_is_a_different_declaration(self):
        Plugin = _plugin_family()

        def declare_one():
            class PluginA(Plugin):
                name = "a"

            return PluginA

        def declare_other():
            class PluginA(Plugin):
                name = "a"

            return PluginA

        declare_one()
        with pytest.raises(DuplicateRegistryKeyError):
            declare_other()

    def test_declared_replacement_takes_the_key(self):
        Plugin = _plugin_family()

        class PluginA(Plugin):
            name = "a"

        class PluginB(PluginA):
            __replaces_registered__ = PluginA

        assert Plugin.__registry__ == {"a": PluginB}

    def test_declared_replacement_is_not_inherited(self):
        Plugin = _plugin_family()

        class PluginA(Plugin):
            name = "a"

        class PluginB(PluginA):
            __replaces_registered__ = PluginA

        with pytest.raises(DuplicateRegistryKeyError):

            class PluginC(PluginB):
                pass

        assert Plugin.__registry__ == {"a": PluginB}

    def test_declared_replacement_must_name_the_registered_class(self):
        Plugin = _plugin_family()

        class PluginA(Plugin):
            name = "a"

        class PluginB(Plugin):
            name = "b"

        with pytest.raises(DuplicateRegistryKeyError, match="is registered to"):

            class PluginC(Plugin):
                name = "a"
                __replaces_registered__ = PluginB

        with pytest.raises(DuplicateRegistryKeyError, match="is not registered"):

            class PluginD(Plugin):
                name = "d"
                __replaces_registered__ = PluginA

        assert Plugin.__registry__ == {"a": PluginA, "b": PluginB}

    def test_declared_replacement_on_a_class_that_does_not_register_raises(self):
        Plugin = _plugin_family()

        class PluginA(Plugin):
            name = "a"

        with pytest.raises(DuplicateRegistryKeyError, match="is abstract"):

            class AbstractPlugin(Plugin):
                __replaces_registered__ = PluginA

                @abstractmethod
                def run(self): ...

        assert Plugin.__registry__ == {"a": PluginA}

    def test_declared_replacement_must_be_a_class(self):
        Plugin = _plugin_family()

        class PluginA(Plugin):
            name = "a"

        with pytest.raises(TypeError, match="must be the registered class"):

            class PluginB(Plugin):
                name = "a"
                __replaces_registered__ = "PluginA"

        assert Plugin.__registry__ == {"a": PluginA}

    def test_subclass_of_a_derived_key_class_derives_its_own_key(self):
        """The key stamped on a registered class is not its subclasses' key."""

        class Plugin(metaclass=AutoRegisterMeta):
            __registry_key__ = "label"
            __key_extractor__ = staticmethod(lambda name, cls: cls.mode)
            label = None
            mode = None

        class MaskPlugin(Plugin):
            mode = "mask"

        class ObjectPlugin(MaskPlugin):
            mode = "objects"

        assert Plugin.__registry__ == {"mask": MaskPlugin, "objects": ObjectPlugin}
        assert ObjectPlugin.label == "objects"

    def test_slots_dataclass_subclass_of_a_derived_key_class_derives_its_own_key(self):
        from dataclasses import dataclass

        class Plugin(metaclass=AutoRegisterMeta):
            __registry_key__ = "label"
            __key_extractor__ = staticmethod(lambda name, cls: cls.mode)
            label = None
            mode = None

        @dataclass(frozen=True, slots=True)
        class MaskPlugin(Plugin):
            mode = "mask"

        @dataclass(frozen=True, slots=True)
        class ObjectPlugin(MaskPlugin):
            mode = "objects"

        assert Plugin.__registry__ == {"mask": MaskPlugin, "objects": ObjectPlugin}

    def test_error_names_the_family_not_the_member(self):
        class StorageBackend(metaclass=AutoRegisterMeta):
            __registry_key__ = "name"
            name = None

        class DiskBackend(StorageBackend):
            name = "disk"

        with pytest.raises(DuplicateRegistryKeyError, match="^storage backend key 'disk'"):

            class OtherDiskBackend(StorageBackend):
                name = "disk"


class TestOneValuePerSecondaryKey:
    def _family(self, handlers, key_source=PRIMARY_KEY):
        class Plugin(metaclass=AutoRegisterMeta):
            __registry_key__ = "name"
            __secondary_registries__ = [
                SecondaryRegistry(
                    registry_dict=handlers, key_source=key_source, attr_name="handler_class"
                )
            ]
            name = None
            handler_key = None
            handler_class = None

        return Plugin

    def test_different_value_on_occupied_secondary_key_raises(self):
        handlers = {}
        Plugin = self._family(handlers, key_source="handler_key")

        class HandlerA:
            pass

        class HandlerB:
            pass

        class PluginA(Plugin):
            name = "a"
            handler_key = "shared"
            handler_class = HandlerA

        with pytest.raises(DuplicateRegistryKeyError, match="handler_class"):

            class PluginB(Plugin):
                name = "b"
                handler_key = "shared"
                handler_class = HandlerB

        assert handlers == {"shared": HandlerA}

    def test_same_value_on_a_secondary_key_is_accepted(self):
        handlers = {}
        Plugin = self._family(handlers, key_source="handler_key")

        class Handler:
            pass

        class PluginA(Plugin):
            name = "a"
            handler_key = "shared"
            handler_class = Handler

        class PluginB(Plugin):
            name = "b"
            handler_key = "shared"
            handler_class = Handler

        assert handlers == {"shared": Handler}

    def test_replacing_class_takes_the_secondary_entry_with_it(self):
        handlers = {}
        Plugin = self._family(handlers)

        class HandlerA:
            pass

        class HandlerB:
            pass

        class PluginA(Plugin):
            name = "a"
            handler_class = HandlerA

        class PluginB(PluginA):
            __replaces_registered__ = PluginA
            handler_class = HandlerB

        assert Plugin.__registry__ == {"a": PluginB}
        assert handlers == {"a": HandlerB}


class TestDiscoveryReportsDuplicateKeys:
    def test_duplicate_key_in_a_discovered_package_propagates(self, tmp_path, monkeypatch):
        import sys

        package = tmp_path / "test_pkg_duplicates"
        package.mkdir()
        (package / "__init__.py").write_text(
            "from metaclass_registry import AutoRegisterMeta, LazyDiscoveryDict, RegistryConfig\n"
            "REGISTRY = LazyDiscoveryDict(enable_cache=False)\n"
            "class Plugin(metaclass=AutoRegisterMeta):\n"
            "    __registry_config__ = RegistryConfig(\n"
            "        registry_dict=REGISTRY, key_attribute='name',\n"
            "        discovery_package='test_pkg_duplicates', registry_name='plugin')\n"
            "    name = None\n"
        )
        for module_name in ("first", "second"):
            (package / f"{module_name}.py").write_text(
                "from test_pkg_duplicates import Plugin\n"
                f"class {module_name.title()}Plugin(Plugin):\n"
                "    name = 'same'\n"
            )
        monkeypatch.syspath_prepend(str(tmp_path))
        import test_pkg_duplicates

        with pytest.raises(DuplicateRegistryKeyError, match="'same'"):
            len(test_pkg_duplicates.REGISTRY)
        # A failed discovery is not recorded as complete.
        with pytest.raises(DuplicateRegistryKeyError, match="'same'"):
            len(test_pkg_duplicates.REGISTRY)
        for name in [name for name in sys.modules if name.startswith("test_pkg_duplicates")]:
            del sys.modules[name]


class TestRestoredRegistry:
    def test_stand_in_takes_a_released_key_and_the_registry_comes_back(self):
        from metaclass_registry.testing import restored_registry

        Plugin = _plugin_family()

        class PluginA(Plugin):
            name = "a"

        with restored_registry(Plugin, released=("a",)):

            class StandIn(PluginA):
                pass

            class Extra(Plugin):
                name = "extra"

            assert Plugin.__registry__ == {"a": StandIn, "extra": Extra}

        assert Plugin.__registry__ == {"a": PluginA}

    def test_keys_that_were_not_released_still_reject_a_second_class(self):
        from metaclass_registry.testing import restored_registry

        Plugin = _plugin_family()

        class PluginA(Plugin):
            name = "a"

        with restored_registry(Plugin), pytest.raises(DuplicateRegistryKeyError):

            class StandIn(PluginA):
                pass

        assert Plugin.__registry__ == {"a": PluginA}
