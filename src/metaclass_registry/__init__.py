"""
metaclass-registry: Zero-boilerplate metaclass-driven plugin registry system.

This package provides a generic metaclass infrastructure for automatic plugin
registration with lazy discovery, caching, and zero boilerplate.
"""

__version__ = "0.4.1"

from .cache import RegistryCacheManager
from .core import (
    PRIMARY_KEY,
    REPLACES_REGISTERED_ATTRIBUTE,
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
    is_same_declaration,
    make_suffix_extractor,
    register_once,
)
from .discovery import (
    discover_registry_classes,
    discover_registry_classes_recursive,
    import_module_preserving_root_logging,
)
from .exceptions import (
    CacheError,
    DiscoveryError,
    DuplicateRegistryKeyError,
    RegistryError,
)
from .mro_dispatch import MroDispatch, handles

__all__ = [
    # Core
    "AutoRegisterMeta",
    "RegistryConfig",
    "RegistryFamily",
    "RegistryKeyAttribute",
    "RegisteredEnumMeta",
    "PRIMARY_KEY",
    "REPLACES_REGISTERED_ATTRIBUTE",
    "register_once",
    "is_same_declaration",
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
    # MRO dispatch
    "MroDispatch",
    "handles",
    # Exceptions
    "RegistryError",
    "DuplicateRegistryKeyError",
    "DiscoveryError",
    "CacheError",
]
