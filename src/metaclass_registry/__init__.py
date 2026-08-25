"""
metaclass-registry: Zero-boilerplate metaclass-driven plugin registry system.

This package provides a generic metaclass infrastructure for automatic plugin
registration with lazy discovery, caching, and zero boilerplate.
"""

__version__ = "0.2.1"

from .cache import RegistryCacheManager
from .core import (
    PRIMARY_KEY,
    AutoRegisterMeta,
    LazyDiscoveryDict,
    RegisteredEnumMeta,
    RegistryConfig,
    RegistryFamily,
    RegistryKeyAttribute,
    SecondaryRegistry,
    SecondaryRegistryDict,
    extract_key_from_backend_suffix,
    extract_key_from_class_name,
    extract_key_from_handler_suffix,
    make_suffix_extractor,
)
from .discovery import (
    discover_registry_classes,
    discover_registry_classes_recursive,
    import_module_preserving_root_logging,
)
from .exceptions import CacheError, DiscoveryError, RegistryError

__all__ = [
    # Core
    "AutoRegisterMeta",
    "RegistryConfig",
    "RegistryFamily",
    "RegistryKeyAttribute",
    "RegisteredEnumMeta",
    "PRIMARY_KEY",
    "SecondaryRegistry",
    "LazyDiscoveryDict",
    "SecondaryRegistryDict",
    "extract_key_from_class_name",
    "extract_key_from_handler_suffix",
    "extract_key_from_backend_suffix",
    "make_suffix_extractor",
    # Discovery
    "discover_registry_classes",
    "discover_registry_classes_recursive",
    "import_module_preserving_root_logging",
    # Cache
    "RegistryCacheManager",
    # Exceptions
    "RegistryError",
    "DiscoveryError",
    "CacheError",
]
