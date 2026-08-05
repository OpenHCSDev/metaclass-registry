"""Tests for metaclass_registry.cache module."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from metaclass_registry.cache import (
    CacheConfig,
    RegistryCacheManager,
    get_cache_file_path,
    serialize_plugin_class,
    deserialize_plugin_class,
    get_package_file_mtimes,
)


class NestedPluginOwner:
    class NestedPlugin:
        pass


class RoundtripPlugin:
    pass


class TestGetCacheFilePath:
    """Test get_cache_file_path function."""

    def test_default_cache_path(self):
        """Test default cache path creation."""
        import os
        # Only patch XDG_CACHE_HOME to ensure it's not set, without clearing all env vars
        with patch.dict('os.environ', {'XDG_CACHE_HOME': ''}, clear=False):
            del os.environ['XDG_CACHE_HOME']

            cache_path = get_cache_file_path('test.json')
            assert cache_path.name == 'test.json'
            assert 'metaclass-registry' in str(cache_path)
            assert '.cache' in str(cache_path)

    def test_xdg_cache_home(self, tmp_path):
        """Test using XDG_CACHE_HOME environment variable."""
        import os
        xdg_cache = tmp_path / 'cache'
        xdg_cache.mkdir()

        with patch.dict('os.environ', {'XDG_CACHE_HOME': str(xdg_cache)}):
            cache_path = get_cache_file_path('test.json')
            assert str(xdg_cache) in str(cache_path)
            assert cache_path.name == 'test.json'

    def test_cache_dir_created(self, tmp_path):
        """Test that cache directory is created if it doesn't exist."""
        import os
        xdg_cache = tmp_path / 'new_cache'

        with patch.dict('os.environ', {'XDG_CACHE_HOME': str(xdg_cache)}):
            cache_path = get_cache_file_path('test.json')
            # Directory should be created
            assert cache_path.parent.exists()


class TestCacheConfig:
    """Test CacheConfig dataclass."""

    def test_default_config(self):
        """Test default CacheConfig values."""
        config = CacheConfig()
        assert config.max_age_days == 7
        assert config.check_mtimes is False
        assert config.cache_version == "1.0"

    def test_custom_config(self):
        """Test custom CacheConfig values."""
        config = CacheConfig(
            max_age_days=30,
            check_mtimes=True,
            cache_version="2.0",
        )
        assert config.max_age_days == 30
        assert config.check_mtimes is True
        assert config.cache_version == "2.0"


class TestSerializeDeserializePluginClass:
    """Test plugin class serialization and deserialization."""

    def test_serialize_simple_class(self):
        """Test serializing a simple class."""

        class TestPlugin:
            pass

        data = serialize_plugin_class(TestPlugin)
        assert data['module'] == __name__
        assert data['class_name'] == 'TestPlugin'
        assert data['qualname'] == 'TestSerializeDeserializePluginClass.test_serialize_simple_class.<locals>.TestPlugin'

    def test_deserialize_builtin_class(self):
        """Test deserializing a built-in class."""
        data = {
            'module': 'builtins',
            'class_name': 'dict',
            'qualname': 'dict',
        }
        result = deserialize_plugin_class(data)
        assert result is dict

    def test_deserialize_nested_class_uses_qualified_name(self):
        """Nested registered classes restore through their declaration owner."""
        data = serialize_plugin_class(NestedPluginOwner.NestedPlugin)

        assert data["class_name"] == "NestedPlugin"
        assert data["qualname"] == "NestedPluginOwner.NestedPlugin"
        assert deserialize_plugin_class(data) is NestedPluginOwner.NestedPlugin

    def test_serialize_deserialize_roundtrip(self):
        """Test serializing and deserializing a class."""
        data = serialize_plugin_class(RoundtripPlugin)
        result = deserialize_plugin_class(data)
        assert result is RoundtripPlugin


class TestGetPackageFileMtimes:
    """Test get_package_file_mtimes function."""

    def test_get_mtimes_for_package(self, tmp_path):
        """Test getting modification times for package files."""
        import sys
        import importlib

        # Create a test package
        pkg_dir = tmp_path / 'test_mtime_pkg'
        pkg_dir.mkdir()
        (pkg_dir / '__init__.py').write_text('# init')
        (pkg_dir / 'module.py').write_text('# module')

        sys.path.insert(0, str(tmp_path))
        try:
            # Import package
            importlib.import_module('test_mtime_pkg')

            # Get mtimes
            mtimes = get_package_file_mtimes('test_mtime_pkg')

            # Should have files (may include __init__.py, module.py)
            assert len(mtimes) >= 1

            # All values should be floats (timestamps)
            for path, mtime in mtimes.items():
                assert isinstance(mtime, float)
                assert mtime > 0

        finally:
            sys.path.remove(str(tmp_path))
            if 'test_mtime_pkg' in sys.modules:
                del sys.modules['test_mtime_pkg']

    def test_get_mtimes_invalid_package(self):
        """Test getting mtimes for non-existent package."""
        mtimes = get_package_file_mtimes('nonexistent.package')
        assert mtimes == {}

    def test_nonrecursive_inventory_excludes_nested_sources(self, tmp_path):
        """Cache inventory follows the discovery recursion declared by its owner."""

        import importlib
        import sys

        package_dir = tmp_path / "test_nonrecursive_mtime_pkg"
        nested_dir = package_dir / "nested"
        nested_dir.mkdir(parents=True)
        (package_dir / "__init__.py").write_text("# init")
        (package_dir / "plugin.py").write_text("# plugin")
        (nested_dir / "__init__.py").write_text("# nested init")
        nested_source = nested_dir / "nested_plugin.py"
        nested_source.write_text("# nested plugin")

        sys.path.insert(0, str(tmp_path))
        try:
            importlib.import_module("test_nonrecursive_mtime_pkg")

            nonrecursive = get_package_file_mtimes(
                "test_nonrecursive_mtime_pkg",
                recursive=False,
            )
            recursive = get_package_file_mtimes(
                "test_nonrecursive_mtime_pkg",
                recursive=True,
            )

            assert str(package_dir / "plugin.py") in nonrecursive
            assert str(nested_source) not in nonrecursive
            assert str(nested_source) in recursive
        finally:
            sys.path.remove(str(tmp_path))
            sys.modules.pop("test_nonrecursive_mtime_pkg", None)


class TestRegistryCacheManager:
    """Test RegistryCacheManager class."""

    def test_init(self, tmp_path):
        """Test RegistryCacheManager initialization."""
        import os

        with patch.dict('os.environ', {'XDG_CACHE_HOME': str(tmp_path)}):
            manager = RegistryCacheManager(
                cache_name='test_cache',
                version_getter=lambda: '1.0',
                serializer=lambda x: {'value': x},
                deserializer=lambda x: x['value'],
            )

            assert manager.cache_name == 'test_cache'
            assert manager.version_getter() == '1.0'

    def test_save_and_load_cache(self, tmp_path):
        """Test saving and loading cache."""
        import os

        with patch.dict('os.environ', {'XDG_CACHE_HOME': str(tmp_path)}):
            manager = RegistryCacheManager(
                cache_name='test_cache',
                version_getter=lambda: '1.0',
                serializer=lambda x: {'value': x},
                deserializer=lambda x: x['value'],
            )

            # Save cache
            items = {'key1': 'value1', 'key2': 'value2'}
            manager.save_cache(items)

            # Load cache
            loaded = manager.load_cache()
            assert loaded == items

    def test_cache_version_mismatch(self, tmp_path):
        """Test that cache is invalidated on version change."""
        import os

        version = ['1.0']

        with patch.dict('os.environ', {'XDG_CACHE_HOME': str(tmp_path)}):
            manager = RegistryCacheManager(
                cache_name='test_version',
                version_getter=lambda: version[0],
                serializer=lambda x: {'value': x},
                deserializer=lambda x: x['value'],
            )

            # Save cache with version 1.0
            items = {'key': 'value'}
            manager.save_cache(items)

            # Change version
            version[0] = '2.0'

            # Try to load cache - should be None due to version mismatch
            loaded = manager.load_cache()
            assert loaded is None

    def test_cache_age_invalidation(self, tmp_path):
        """Test that cache is invalidated when too old."""
        import os

        with patch.dict('os.environ', {'XDG_CACHE_HOME': str(tmp_path)}):
            config = CacheConfig(max_age_days=7)
            manager = RegistryCacheManager(
                cache_name='test_age',
                version_getter=lambda: '1.0',
                serializer=lambda x: {'value': x},
                deserializer=lambda x: x['value'],
                config=config,
            )

            # Save cache
            items = {'key': 'value'}
            manager.save_cache(items)

            # Modify cache timestamp to be old
            cache_path = manager._cache_path
            with open(cache_path, 'r') as f:
                data = json.load(f)

            # Set timestamp to 8 days ago
            data['timestamp'] = time.time() - (8 * 24 * 3600)

            with open(cache_path, 'w') as f:
                json.dump(data, f)

            # Try to load - should be None due to age
            loaded = manager.load_cache()
            assert loaded is None

    def test_cache_mtime_validation(self, tmp_path):
        """Test cache invalidation based on file mtimes."""
        import os

        test_file = tmp_path / 'test_file.py'
        test_file.write_text('# original')

        with patch.dict('os.environ', {'XDG_CACHE_HOME': str(tmp_path / 'cache')}):
            config = CacheConfig(check_mtimes=True)
            manager = RegistryCacheManager(
                cache_name='test_mtime',
                version_getter=lambda: '1.0',
                serializer=lambda x: {'value': x},
                deserializer=lambda x: x['value'],
                config=config,
            )

            # Save cache with file mtimes
            items = {'key': 'value'}
            file_mtimes = {str(test_file): test_file.stat().st_mtime}
            manager.save_cache(items, file_mtimes=file_mtimes)

            # Should load successfully
            loaded = manager.load_cache()
            assert loaded == items

            # Modify file with enough delay to ensure mtime changes
            time.sleep(1.1)  # Ensure mtime changes (tolerance is 1.0 second)
            test_file.write_text('# modified')

            # Try to load - should be None due to mtime mismatch
            loaded = manager.load_cache()
            assert loaded is None

    def test_cache_source_inventory_invalidates_when_file_is_added(self, tmp_path):
        """A newly discoverable source file invalidates a persistent registry cache."""

        source_dir = tmp_path / "sources"
        source_dir.mkdir()
        existing_source = source_dir / "existing.py"
        existing_source.write_text("# existing")

        def current_inventory():
            return {
                str(source_file): source_file.stat().st_mtime
                for source_file in source_dir.glob("*.py")
            }

        with patch.dict('os.environ', {'XDG_CACHE_HOME': str(tmp_path / 'cache')}):
            manager = RegistryCacheManager(
                cache_name='test_source_inventory',
                version_getter=lambda: '1.0',
                serializer=lambda x: {'value': x},
                deserializer=lambda x: x['value'],
                config=CacheConfig(check_mtimes=True),
                file_mtimes_getter=current_inventory,
            )
            manager.save_cache(
                {'key': 'value'},
                file_mtimes=current_inventory(),
            )
            assert manager.load_cache() == {'key': 'value'}

            (source_dir / "new_plugin.py").write_text("# newly discoverable")

            assert manager.load_cache() is None

    def test_clear_cache(self, tmp_path):
        """Test clearing the cache."""
        import os

        with patch.dict('os.environ', {'XDG_CACHE_HOME': str(tmp_path)}):
            manager = RegistryCacheManager(
                cache_name='test_clear',
                version_getter=lambda: '1.0',
                serializer=lambda x: {'value': x},
                deserializer=lambda x: x['value'],
            )

            # Save cache
            items = {'key': 'value'}
            manager.save_cache(items)
            assert manager._cache_path.exists()

            # Clear cache
            manager.clear_cache()
            assert not manager._cache_path.exists()

    def test_corrupt_cache_handling(self, tmp_path):
        """Test handling of corrupted cache file."""
        import os

        with patch.dict('os.environ', {'XDG_CACHE_HOME': str(tmp_path)}):
            manager = RegistryCacheManager(
                cache_name='test_corrupt',
                version_getter=lambda: '1.0',
                serializer=lambda x: {'value': x},
                deserializer=lambda x: x['value'],
            )

            # Create corrupt cache file
            manager._cache_path.parent.mkdir(parents=True, exist_ok=True)
            manager._cache_path.write_text('not valid json{{{')

            # Should return None and delete corrupt file
            loaded = manager.load_cache()
            assert loaded is None
            assert not manager._cache_path.exists()

    def test_serialization_error_handling(self, tmp_path):
        """Test handling of serialization errors."""
        import os

        def bad_serializer(x):
            raise ValueError("Serialization failed")

        with patch.dict('os.environ', {'XDG_CACHE_HOME': str(tmp_path)}):
            manager = RegistryCacheManager(
                cache_name='test_ser_error',
                version_getter=lambda: '1.0',
                serializer=bad_serializer,
                deserializer=lambda x: x['value'],
            )

            # Save should handle error gracefully
            items = {'key': 'value'}
            manager.save_cache(items)  # Should not raise

            # Cache file should not be created or be incomplete
            if manager._cache_path.exists():
                with open(manager._cache_path, 'r') as f:
                    data = json.load(f)
                    # Item entries should be empty due to serialization failures
                    assert len(data['item_entries']) == 0

    def test_deserialization_error_handling(self, tmp_path):
        """Test handling of deserialization errors."""
        import os

        def bad_deserializer(x):
            raise ValueError("Deserialization failed")

        with patch.dict('os.environ', {'XDG_CACHE_HOME': str(tmp_path)}):
            manager = RegistryCacheManager(
                cache_name='test_deser_error',
                version_getter=lambda: '1.0',
                serializer=lambda x: {'value': x},
                deserializer=bad_deserializer,
            )

            # Save cache
            items = {'key': 'value'}
            manager.save_cache(items)

            # Load should return None on deserialization error
            loaded = manager.load_cache()
            assert loaded is None


# Import os for tests that need it
import os
