"""
metaclass-registry: Zero-boilerplate metaclass-driven plugin registry system.

This package provides a generic metaclass infrastructure for automatic plugin
registration with lazy discovery, caching, and zero boilerplate.
"""

__version__ = "0.2.0rc1"

from .core import (
    AutoRegisterMeta,
    RegistryConfig,
    RegistryFamily,
    RegistryKeyAttribute,
    RegisteredEnumMeta,
    PRIMARY_KEY,
    SecondaryRegistry,
    LazyDiscoveryDict,
    SecondaryRegistryDict,
    extract_key_from_class_name,
    extract_key_from_handler_suffix,
    extract_key_from_backend_suffix,
    make_suffix_extractor,
)
from .discovery import discover_registry_classes, discover_registry_classes_recursive
from .cache import RegistryCacheManager
from .exceptions import RegistryError, DiscoveryError, CacheError

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
    # Cache
    "RegistryCacheManager",
    # Exceptions
    "RegistryError",
    "DiscoveryError",
    "CacheError",
]
