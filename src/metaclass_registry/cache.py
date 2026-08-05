"""
Generic caching system for plugin registries.

Provides unified caching for both function registries (Pattern B) and
metaclass registries (Pattern A), eliminating code duplication and
ensuring consistent cache behavior across the codebase.

Architecture:
- RegistryCacheManager: Generic cache manager for any registry type
- Supports version validation, age-based invalidation, mtime checking
- JSON-based serialization with custom serializers/deserializers
- XDG-compliant cache locations

Usage:
    # For function registries
    cache_mgr = RegistryCacheManager(
        cache_name="scikit_image_functions",
        version_getter=lambda: skimage.__version__,
        serializer=serialize_function_metadata,
        deserializer=deserialize_function_metadata
    )
    
    # For metaclass registries
    cache_mgr = RegistryCacheManager(
        cache_name="microscope_handlers",
        version_getter=lambda: openhcs.__version__,
        serializer=serialize_plugin_class,
        deserializer=deserialize_plugin_class
    )
"""

import json
import logging
import time
from pathlib import Path
from enum import Enum
from typing import Dict, Any, Optional, Callable, TypeVar, Generic
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def get_cache_file_path(cache_name: str) -> Path:
    """
    Get XDG-compliant cache file path.

    Args:
        cache_name: Name of the cache file

    Returns:
        Path to cache file in XDG cache directory
    """
    from . import _home
    
    # Use XDG_CACHE_HOME if set, otherwise default to ~/.cache
    import os
    cache_home = os.environ.get('XDG_CACHE_HOME')
    if not cache_home:
        cache_home = Path(_home.get_home_dir()) / '.cache'
    else:
        cache_home = Path(cache_home)

    # Create metaclass-registry subdirectory
    cache_dir = cache_home / 'metaclass-registry'
    cache_dir.mkdir(parents=True, exist_ok=True)

    return cache_dir / cache_name

T = TypeVar('T')  # Generic type for cached items


class CacheKeyCodec:
    """JSON-safe, reversible representation for registry keys."""

    PRIMITIVE_KIND = "primitive"
    ENUM_KIND = "enum"
    TUPLE_KIND = "tuple"

    @classmethod
    def encode(cls, key: Any) -> Dict[str, Any]:
        if isinstance(key, (str, int, float, bool)) or key is None:
            return {"kind": cls.PRIMITIVE_KIND, "value": key}
        if isinstance(key, Enum):
            return {
                "kind": cls.ENUM_KIND,
                "module": key.__class__.__module__,
                "class_name": key.__class__.__name__,
                "member_name": key.name,
            }
        if isinstance(key, tuple):
            return {
                "kind": cls.TUPLE_KIND,
                "items": [cls.encode(item) for item in key],
            }
        raise TypeError(f"Unsupported registry cache key type: {type(key)!r}")

    @classmethod
    def decode(cls, payload: Dict[str, Any]) -> Any:
        kind = payload["kind"]
        try:
            decoder = CACHE_KEY_DECODERS[kind]
        except KeyError as exc:
            raise ValueError(f"Unsupported registry cache key kind: {kind!r}") from exc
        return decoder(payload)


def _decode_primitive_cache_key(payload: Dict[str, Any]) -> Any:
    return payload["value"]


def _decode_enum_cache_key(payload: Dict[str, Any]) -> Enum:
    import importlib

    enum_module = importlib.import_module(payload["module"])
    enum_type = vars(enum_module)[payload["class_name"]]
    return enum_type[payload["member_name"]]


def _decode_tuple_cache_key(payload: Dict[str, Any]) -> tuple[Any, ...]:
    return tuple(CacheKeyCodec.decode(item) for item in payload["items"])


CACHE_KEY_DECODERS: Dict[str, Callable[[Dict[str, Any]], Any]] = {
    CacheKeyCodec.PRIMITIVE_KIND: _decode_primitive_cache_key,
    CacheKeyCodec.ENUM_KIND: _decode_enum_cache_key,
    CacheKeyCodec.TUPLE_KIND: _decode_tuple_cache_key,
}


@dataclass
class CacheConfig:
    """Configuration for registry caching behavior."""
    max_age_days: int = 7  # Maximum cache age before invalidation
    check_mtimes: bool = False  # Check file modification times
    cache_version: str = "1.0"  # Cache format version


class RegistryCacheManager(Generic[T]):
    """
    Generic cache manager for plugin registries.
    
    Handles caching, validation, and reconstruction of registry data
    with support for version checking, age-based invalidation, and
    custom serialization.
    
    Type Parameters:
        T: Type of items being cached (e.g., FunctionMetadata, Type[Plugin])
    """
    
    def __init__(
        self,
        cache_name: str,
        version_getter: Callable[[], str],
        serializer: Callable[[T], Dict[str, Any]],
        deserializer: Callable[[Dict[str, Any]], T],
        config: Optional[CacheConfig] = None,
        file_mtimes_getter: Optional[Callable[[], Dict[str, float]]] = None,
    ):
        """
        Initialize cache manager.
        
        Args:
            cache_name: Name for the cache file (e.g., "microscope_handlers")
            version_getter: Function that returns current version string
            serializer: Function to serialize item to JSON-compatible dict
            deserializer: Function to deserialize dict back to item
            config: Optional cache configuration
            file_mtimes_getter: Optional authoritative inventory of source files used by
                discovery. When provided, added files invalidate the cache as well as
                modified and removed files.
        """
        self.cache_name = cache_name
        self.version_getter = version_getter
        self.serializer = serializer
        self.deserializer = deserializer
        self.config = config or CacheConfig()
        self.file_mtimes_getter = file_mtimes_getter
        self._cache_path = get_cache_file_path(f"{cache_name}.json")
    
    def load_cache(self) -> Optional[Dict[str, T]]:
        """
        Load cached items with validation.
        
        Returns:
            Dictionary of cached items, or None if cache is invalid
        """
        if not self._cache_path.exists():
            logger.debug(f"No cache found for {self.cache_name}")
            return None
        
        try:
            with open(self._cache_path, 'r') as f:
                cache_data = json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"Corrupt cache file {self._cache_path}, rebuilding")
            self._cache_path.unlink(missing_ok=True)
            return None
        
        # Validate cache version
        if cache_data.get('cache_version') != self.config.cache_version:
            logger.debug(f"Cache version mismatch for {self.cache_name}")
            return None
        
        # Validate library/package version
        cached_version = cache_data.get('version', 'unknown')
        current_version = self.version_getter()
        if cached_version != current_version:
            logger.info(
                f"{self.cache_name} version changed "
                f"({cached_version} → {current_version}) - cache invalid"
            )
            return None
        
        # Validate cache age
        cache_timestamp = cache_data.get('timestamp', 0)
        cache_age_days = (time.time() - cache_timestamp) / (24 * 3600)
        if cache_age_days > self.config.max_age_days:
            logger.debug(
                f"Cache for {self.cache_name} is {cache_age_days:.1f} days old - rebuilding"
            )
            return None
        
        # Validate file mtimes if configured
        if self.config.check_mtimes and 'file_mtimes' in cache_data:
            current_mtimes = (
                self.file_mtimes_getter()
                if self.file_mtimes_getter is not None
                else None
            )
            if not self._validate_mtimes(
                cache_data['file_mtimes'],
                current_mtimes=current_mtimes,
            ):
                logger.debug(f"File modifications detected for {self.cache_name}")
                return None
        
        # Deserialize items
        items = {}
        item_entries = cache_data.get('item_entries')
        if item_entries is None:
            item_entries = [
                {"key": CacheKeyCodec.encode(key), "item": item_data}
                for key, item_data in cache_data.get('items', {}).items()
            ]
        for entry in item_entries:
            key = CacheKeyCodec.decode(entry['key'])
            item_data = entry['item']
            try:
                items[key] = self.deserializer(item_data)
            except Exception as e:
                logger.warning(f"Failed to deserialize {key} from cache: {e}")
                return None  # Invalidate entire cache on any deserialization error
        
        logger.debug(f"✅ Loaded {len(items)} items from {self.cache_name} cache")
        return items
    
    def save_cache(
        self,
        items: Dict[str, T],
        file_mtimes: Optional[Dict[str, float]] = None
    ) -> None:
        """
        Save items to cache.
        
        Args:
            items: Dictionary of items to cache
            file_mtimes: Optional dict of file paths to modification times
        """
        cache_data = {
            'cache_version': self.config.cache_version,
            'version': self.version_getter(),
            'timestamp': time.time(),
            'item_entries': []
        }
        
        # Add file mtimes if provided
        if file_mtimes:
            cache_data['file_mtimes'] = file_mtimes
        
        # Serialize items
        for key, item in items.items():
            try:
                cache_data['item_entries'].append({
                    'key': CacheKeyCodec.encode(key),
                    'item': self.serializer(item),
                })
            except Exception as e:
                logger.warning(f"Failed to serialize {key} for cache: {e}")
        
        # Save to disk
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)
            logger.debug(f"💾 Saved {len(items)} items to {self.cache_name} cache")
        except Exception as e:
            logger.warning(f"Failed to save {self.cache_name} cache: {e}")
    
    def clear_cache(self) -> None:
        """Clear the cache file."""
        if self._cache_path.exists():
            self._cache_path.unlink()
            logger.info(f"🧹 Cleared {self.cache_name} cache")
    
    def _validate_mtimes(
        self,
        cached_mtimes: Dict[str, float],
        *,
        current_mtimes: Optional[Dict[str, float]] = None,
    ) -> bool:
        """
        Validate that file modification times haven't changed.
        
        Args:
            cached_mtimes: Dictionary of file paths to cached mtimes
            current_mtimes: Optional complete current inventory. When present, its paths
                must exactly match the cached discovery inventory.
            
        Returns:
            True if all mtimes match, False if any file changed
        """
        if current_mtimes is not None and current_mtimes.keys() != cached_mtimes.keys():
            return False

        for file_path, cached_mtime in cached_mtimes.items():
            path = Path(file_path)
            if not path.exists():
                return False  # File was deleted

            current_mtime = (
                current_mtimes[file_path]
                if current_mtimes is not None
                else path.stat().st_mtime
            )
            if abs(current_mtime - cached_mtime) > 1.0:  # 1 second tolerance
                return False  # File was modified
        
        return True


# Serializers for metaclass registries (Pattern A)

def serialize_plugin_class(plugin_class: type) -> Dict[str, Any]:
    """
    Serialize a plugin class to JSON-compatible dict.
    
    Args:
        plugin_class: Plugin class to serialize
        
    Returns:
        Dictionary with module and class name
    """
    return {
        'module': plugin_class.__module__,
        'class_name': plugin_class.__name__,
        'qualname': plugin_class.__qualname__
    }


def deserialize_plugin_class(data: Dict[str, Any]) -> type:
    """
    Deserialize a plugin class from JSON-compatible dict.
    
    Args:
        data: Dictionary with module and class name
        
    Returns:
        Reconstructed plugin class
        
    Raises:
        ImportError: If module cannot be imported
        AttributeError: If class not found in module
    """
    import importlib
    
    declaration: Any = importlib.import_module(data['module'])
    for owner_name in data['qualname'].split('.'):
        if owner_name == '<locals>':
            raise AttributeError(
                "Function-local classes cannot be restored from a registry cache"
            )
        declaration = getattr(declaration, owner_name)
    if not isinstance(declaration, type):
        raise TypeError(
            f"Cached plugin declaration {data['qualname']!r} is not a class"
        )
    return declaration


def get_package_file_mtimes(
    package_path: str,
    *,
    recursive: bool = True,
) -> Dict[str, float]:
    """
    Get modification times for all Python files in a package.
    
    Args:
        package_path: Package path (e.g., "openhcs.microscopes")
        recursive: Whether nested package files participate in discovery.
        
    Returns:
        Dictionary mapping file paths to modification times
    """
    import importlib
    import importlib.util
    from pathlib import Path
    
    try:
        importlib.import_module(package_path)
        spec = importlib.util.find_spec(package_path)
        if spec is None:
            return {}
        if spec.submodule_search_locations:
            package_dirs = [
                Path(location)
                for location in spec.submodule_search_locations
            ]
        elif spec.origin is not None:
            package_dirs = [Path(spec.origin).parent]
        else:
            return {}

        mtimes = {}
        for package_dir in package_dirs:
            source_files = (
                package_dir.rglob("*.py")
                if recursive
                else package_dir.glob("*.py")
            )
            for py_file in source_files:
                mtimes[str(py_file)] = py_file.stat().st_mtime
        
        return mtimes
    except Exception as e:
        logger.warning(f"Failed to get mtimes for {package_path}: {e}")
        return {}
