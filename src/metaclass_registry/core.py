"""
Generic metaclass infrastructure for automatic plugin registration.

This module provides reusable metaclass infrastructure for Pattern A registry systems
(1:1 class-to-plugin mapping with automatic discovery). It eliminates code duplication
across MicroscopeHandlerMeta, StorageBackendMeta, and ContextProviderMeta.

Pattern Selection Guide:
-----------------------
Use AutoRegisterMeta (Pattern A) when:
- You have a 1:1 mapping between classes and plugins
- Plugins should be automatically discovered and registered
- Registration happens at class definition time
- Simple metadata (just a key and maybe one secondary registry)

Use Service Pattern (Pattern B) when:
- You have many-to-one mapping (multiple items per plugin)
- Complex metadata (FunctionMetadata with 8+ fields)
- Need aggregation across multiple sources
- Examples: Function registry, Format registry

Use Functional Registry (Pattern C) when:
- Simple type-to-handler mappings
- No state needed
- Functional programming style preferred
- Examples: Widget creation registries

Use Manual Registration (Pattern D) when:
- Complex initialization logic required
- Explicit control over registration timing needed
- Very few plugins (< 3)
- Examples: ZMQ servers, Pipeline steps

Architecture:
------------
AutoRegisterMeta uses a configuration-driven approach:
1. RegistryConfig defines registration behavior
2. The nominal registry root owns that configuration as ``__registry_config__``
3. AutoRegisterMeta applies the configuration during class creation

This keeps domain semantics on their nominal owner while eliminating duplicated
metaclass wrappers and caller-side discovery inference.
"""

import logging
import threading
from abc import ABCMeta
from collections.abc import Callable, Hashable, Iterable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from enum import Enum, EnumMeta
from typing import Any, cast

from .cache import (
    CacheConfig,
    RegistryCacheManager,
    deserialize_plugin_class,
    get_package_file_mtimes,
    serialize_plugin_class,
)
from .discovery import (
    discover_registry_classes,
    discover_registry_classes_recursive,
    import_module_preserving_root_logging,
)
from .exceptions import DiscoveryError, DuplicateRegistryKeyError

logger = logging.getLogger(__name__)

# Type aliases for clarity
RegistryKey = Hashable
RegistryDict = dict[RegistryKey, Any]
KeyExtractor = Callable[[str, type], RegistryKey]

# Constants for key sources
PRIMARY_KEY = "primary"

# Declared in a class body: the registered class this class takes the key from.
REPLACES_REGISTERED_ATTRIBUTE = "__replaces_registered__"

# Set on a class whose key came from the family's key extractor, so that a
# subclass derives its own key instead of inheriting the stamped one.
_DERIVED_KEY_MARKER = "__registry_key_derived__"

# Set on a class when it registers. A class rebuilt from a copy of the
# registered class's namespace (``dataclass(slots=True)`` does this) carries
# the same token in its own namespace; a subclass or an unrelated class does not.
_DECLARATION_TOKEN = "__registry_declaration__"

_ABSENT: Any = object()


def _describe(value: object) -> str:
    """Name a registered value by module and qualified name when it has them."""
    module = getattr(value, "__module__", None)
    qualname = getattr(value, "__qualname__", None)
    if module is None or qualname is None:
        return repr(value)
    return f"{module}.{qualname}"


def is_same_declaration(registered: object, candidate: object) -> bool:
    """Whether two class objects come from one class statement.

    ``importlib.reload``, a re-import and a second run of the same function
    body build a new class object for a declaration that already registered:
    the module and qualified name are the declaration's identity, the object
    is not. ``dataclass(slots=True)`` rebuilds the class by calling the
    metaclass with a copy of its namespace, before the qualified name is
    restored: that class has the same module and name and carries the
    registered class's declaration token in its own namespace.
    """
    if not isinstance(registered, type) or not isinstance(candidate, type):
        return False
    if registered.__module__ != candidate.__module__:
        return False
    if registered.__qualname__ == candidate.__qualname__:
        return True
    token = vars(registered).get(_DECLARATION_TOKEN)
    return (
        token is not None
        and vars(candidate).get(_DECLARATION_TOKEN) is token
        and registered.__name__ == candidate.__name__
    )


def register_once(
    registry_dict: "RegistryDict",
    key: RegistryKey,
    value: Any,
    *,
    registry_name: str,
    replaces: object = None,
    superseded_values: tuple[object, ...] = (),
) -> Any:
    """Store ``value`` under ``key``; a key never silently changes hands.

    Returns the value that ``value`` took the key from, or ``None``.

    - The same object again is a no-op.
    - A class from the same declaration (see ``is_same_declaration``) takes
      the key from its earlier object.
    - ``replaces`` names the registered value this one is declared to take
      the key from; the key must hold exactly that value.
    - ``superseded_values`` are values registered by a class that the
      registering class has just taken over from (secondary registries).
    - Anything else raises ``DuplicateRegistryKeyError``.
    """
    existing = dict.get(registry_dict, key, _ABSENT)
    if existing is value:
        return None
    if existing is _ABSENT:
        if replaces is not None:
            raise DuplicateRegistryKeyError(
                f"{_describe(value)} declares {REPLACES_REGISTERED_ATTRIBUTE} = "
                f"{_describe(replaces)}, but {registry_name} key {key!r} is not registered."
            )
        registry_dict[key] = value
        return None
    if (
        is_same_declaration(existing, value)
        or existing is replaces
        or any(existing is superseded for superseded in superseded_values)
    ):
        registry_dict[key] = value
        return existing
    if replaces is not None:
        raise DuplicateRegistryKeyError(
            f"{_describe(value)} declares {REPLACES_REGISTERED_ATTRIBUTE} = "
            f"{_describe(replaces)}, but {registry_name} key {key!r} is registered to "
            f"{_describe(existing)}."
        )
    raise DuplicateRegistryKeyError(
        f"{registry_name} key {key!r} is already registered to {_describe(existing)}; "
        f"{_describe(value)} cannot register under the same key. Give it its own key, or "
        f"declare {REPLACES_REGISTERED_ATTRIBUTE} = {getattr(existing, '__name__', 'TheOther')} "
        f"in its class body if it is meant to take the key over."
    )


class RegistryKeyAttribute(str, Enum):
    """Common class-attribute names used as registry keys."""

    REGISTRY_KEY = "registry_key"
    STRATEGY_KEY = "strategy_key"
    STRATEGY_LABEL = "strategy_label"
    VALUE_TYPE_LABEL = "value_type_label"
    LAYOUT_KEY = "layout_key"


class SecondaryRegistryDict(dict[RegistryKey, Any]):
    """
    Dict for secondary registries that auto-triggers primary registry discovery.

    When accessed, this dict triggers discovery of the primary registry,
    which populates both the primary and secondary registries.
    """

    def __init__(self, primary_registry: "LazyDiscoveryDict") -> None:
        super().__init__()
        self._primary_registry = primary_registry

    def _ensure_discovered(self) -> None:
        """Trigger discovery of primary registry (which populates this secondary registry)."""
        if hasattr(self._primary_registry, "_discover"):
            self._primary_registry._discover()

    def __getitem__(self, key: RegistryKey) -> Any:
        self._ensure_discovered()
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        self._ensure_discovered()
        return super().__contains__(key)

    def __iter__(self) -> Iterator[RegistryKey]:
        self._ensure_discovered()
        return super().__iter__()

    def __len__(self) -> int:
        self._ensure_discovered()
        return super().__len__()

    def keys(self) -> Any:
        self._ensure_discovered()
        return super().keys()

    def values(self) -> Any:
        self._ensure_discovered()
        return super().values()

    def items(self) -> Any:
        self._ensure_discovered()
        return super().items()

    def get(self, key: RegistryKey, default: Any = None) -> Any:
        self._ensure_discovered()
        return super().get(key, default)


class LazyDiscoveryDict(dict[RegistryKey, Any]):
    """
    Dict that auto-discovers plugins on first access with optional caching.

    Supports caching discovered plugins to speed up subsequent application starts.
    Cache is validated against package version and file modification times.

    Thread-safe: Uses locking to ensure discovery happens only once
    even when accessed from multiple threads simultaneously.
    """

    def __init__(self, enable_cache: bool = True) -> None:
        """
        Initialize lazy discovery dict.

        Args:
            enable_cache: If True, use caching to speed up discovery
        """
        super().__init__()
        self._base_class: type | None = None
        self._config: RegistryConfig | None = None
        self._discovered = False
        self._enable_cache = enable_cache
        self._cache_manager: RegistryCacheManager[type] | None = None
        self._discovery_lock = threading.RLock()  # Reentrant lock for same-thread re-entry
        self._discovery_package: str | None = None  # Store for pickling support

    def _set_config(self, base_class: type, config: "RegistryConfig") -> None:
        self._base_class = base_class
        self._config = config
        self._discovery_package = config.discovery_package  # Store for pickling support

        # Initialize cache manager if caching is enabled
        if self._enable_cache and config.discovery_package:
            try:
                self._cache_manager = RegistryCacheManager(
                    cache_name=f"{config.registry_name.replace(' ', '_')}_registry",
                    version_getter=self._get_version,
                    serializer=serialize_plugin_class,
                    deserializer=deserialize_plugin_class,
                    config=CacheConfig(
                        max_age_days=7, check_mtimes=True  # Validate file modifications
                    ),
                    file_mtimes_getter=self._get_discovery_file_mtimes,
                )
            except Exception as e:
                logger.debug(f"Failed to initialize cache manager: {e}")
                self._cache_manager = None

    def _get_version(self) -> str:
        """
        Get version from the discovery package for cache validation.

        Returns:
            Version string or 'unknown' if unable to determine
        """
        try:
            # Try to get version from the root package
            if self._discovery_package:
                root_package = self._discovery_package.split(".")[0]
                mod = __import__(root_package)
                return getattr(mod, "__version__", "unknown")
        except Exception:
            return "unknown"
        return "unknown"

    def _get_discovery_file_mtimes(self) -> dict[str, float]:
        """Return the complete source inventory for this discovery package."""

        if not self._discovery_package or self._config is None:
            return {}
        return get_package_file_mtimes(
            self._discovery_package,
            recursive=self._config.discovery_recursive,
        )

    def _has_discovery_configuration(self) -> bool:
        """Own the shared configuration/root admission for both discovery scopes."""
        if not self._config or not self._config.discovery_package:
            return False
        if self._base_class is None:
            raise RuntimeError("Discovery configuration has no nominal registry root")
        return True

    def _scope_paths(self) -> Iterable[str] | None:
        """Import the declared scope; a plain module has no child modules to scan."""
        config = cast(RegistryConfig, self._config)
        module = import_module_preserving_root_logging(cast(str, config.discovery_package))
        spec = module.__spec__
        if spec is None:
            raise DiscoveryError(f"Discovery scope has no module spec: {module.__name__}")
        return spec.submodule_search_locations

    def _discovery_failed(self) -> None:
        self._discovered = False

    def _discover(self) -> None:
        """Build members once under the registry lock; failed builds remain incomplete."""
        if not self._has_discovery_configuration():
            return
        with self._discovery_lock:
            if self._discovered:
                return
            with ExitStack() as failure:
                failure.callback(self._discovery_failed)
                # Same-thread imports may read the registry while declarations register.
                self._discovered = True
                config = cast(RegistryConfig, self._config)
                if self._cache_manager:
                    cached_plugins = self._cache_manager.load_cache()
                    if cached_plugins is not None:
                        for key, plugin in cached_plugins.items():
                            register_once(self, key, plugin, registry_name=config.registry_name)
                        failure.pop_all()
                        return

                paths = self._scope_paths()
                if paths is not None:
                    discover = config.discovery_function or (
                        discover_registry_classes_recursive
                        if config.discovery_recursive
                        else discover_registry_classes
                    )
                    discover(paths, f"{config.discovery_package}.", cast(type, self._base_class))
                if self._cache_manager:
                    self._cache_manager.save_cache(dict(self), self._get_discovery_file_mtimes())
                failure.pop_all()

    def discover_matching(self, module_filter: Callable[[str], bool]) -> None:
        """Admit selected modules through the original discovery/import owner.

        Selection is not full discovery and never publishes a complete cache.
        Domain declarations supply eligibility; their ordinary metaclass still
        owns registration. Selected import errors propagate rather than turning
        an incomplete selection into apparent absence.
        """
        if not self._has_discovery_configuration():
            return
        config = cast(RegistryConfig, self._config)
        if config.discovery_recursive or config.discovery_function:
            raise ValueError("Selected discovery requires the flat discovery owner")
        with self._discovery_lock:
            if self._discovered:
                return
            paths = self._scope_paths()
            if paths is None:
                return
            discover_registry_classes(
                paths,
                f"{config.discovery_package}.",
                cast(type, self._base_class),
                module_filter=module_filter,
            )

    def __getitem__(self, key: RegistryKey) -> Any:
        with self._discovery_lock:
            self._discover()
            return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        with self._discovery_lock:
            self._discover()
            return super().__contains__(key)

    def __iter__(self) -> Iterator[RegistryKey]:
        with self._discovery_lock:
            self._discover()
            return super().__iter__()

    def __len__(self) -> int:
        with self._discovery_lock:
            self._discover()
            return super().__len__()

    def keys(self) -> Any:
        with self._discovery_lock:
            self._discover()
            return super().keys()

    def values(self) -> Any:
        with self._discovery_lock:
            self._discover()
            return super().values()

    def items(self) -> Any:
        with self._discovery_lock:
            self._discover()
            return super().items()

    def get(self, key: RegistryKey, default: Any = None) -> Any:
        with self._discovery_lock:
            self._discover()
            return super().get(key, default)

    def __getstate__(self) -> dict[RegistryKey, Any]:
        """
        Return state for pickling, excluding non-picklable objects.

        The _discovery_lock and _cache_manager are excluded since they contain
        non-picklable objects (RLock and potentially closures).
        """
        state = dict(self)  # Copy the dict contents
        state.update(
            {
                "_base_class": self._base_class,
                "_config": self._config,
                "_discovered": self._discovered,
                "_enable_cache": self._enable_cache,
                "_discovery_package": self._discovery_package,
                # Exclude: _discovery_lock, _cache_manager
            }
        )
        return state

    def __setstate__(self, state: dict[RegistryKey, Any]) -> None:
        """
        Restore state from pickle, recreating non-picklable objects.

        The _discovery_lock is recreated as a new RLock.
        The _cache_manager is set to None and will be reinitialized if needed.
        """
        # Restore dict contents
        for key, value in state.items():
            if isinstance(key, str) and key.startswith("_"):
                setattr(self, key, value)
            else:
                self[key] = value
        # Recreate non-picklable objects
        self._discovery_lock = threading.RLock()
        self._cache_manager = None  # Will be reinitialized if needed


@dataclass(frozen=True)
class SecondaryRegistry:
    """Configuration for a secondary registry (e.g., metadata handlers)."""

    registry_dict: RegistryDict
    key_source: str  # 'primary' or attribute name
    attr_name: str  # Attribute to check on the class


@dataclass(frozen=True)
class RegistryFamily:
    """Declarative registry-family configuration for ``AutoRegisterMeta`` roots.

    ``AutoRegisterMeta`` historically used low-level class attributes such as
    ``__registry_key__`` and ``__skip_if_no_key__``.  Those attributes remain
    the compatibility surface, but registry roots can now declare one nominal
    family object and let the metaclass install the legacy attributes.
    """

    key_attribute: str | RegistryKeyAttribute
    skip_if_no_key: bool = True
    registry_name: str | None = None

    @property
    def key_attribute_name(self) -> str:
        """Return the string attribute name consumed by ``AutoRegisterMeta``."""
        if isinstance(self.key_attribute, RegistryKeyAttribute):
            return self.key_attribute.value
        return self.key_attribute

    def apply_to_class(self, cls: type, explicit_attrs: dict) -> None:
        """Install legacy metaclass attributes for compatibility/introspection."""
        if "__registry_key__" not in explicit_attrs:
            setattr(cls, "__registry_key__", self.key_attribute_name)
        if "__skip_if_no_key__" not in explicit_attrs:
            setattr(cls, "__skip_if_no_key__", self.skip_if_no_key)
        if self.registry_name is not None and "__registry_name__" not in explicit_attrs:
            setattr(cls, "__registry_name__", self.registry_name)


@dataclass(frozen=True)
class RegistryConfig:
    """
    Configuration for automatic class registration behavior.

    This dataclass encapsulates all the configuration needed for metaclass
    registration, making the pattern explicit and easy to understand.

    Attributes:
        registry_dict: Dictionary to register classes into (e.g., MICROSCOPE_HANDLERS)
        key_attribute: Name of class attribute containing the registration key
                      (e.g., '_microscope_type', '_backend_type', '_context_type')
        key_extractor: Optional function to derive key from class name if key_attribute
                      is not set. Signature: (class_name: str, cls: Type) -> str
        skip_if_no_key: If True, skip registration when key_attribute is None.
                       If False, require either key_attribute or key_extractor.
        secondary_registries: Optional list of secondary registry configurations
        log_registration: If True, log debug message when class is registered
        registry_name: Human-readable name for logging (e.g., 'microscope handler')
        discovery_package: Explicit package name to auto-discover (e.g.,
                           'openhcs.microscopes'). ``None`` keeps registration local to
                           declarations imported by the application.
        discovery_recursive: If True, use recursive discovery (default: False)

    Examples:
        # Microscope handlers with name-based key extraction and secondary registry
        RegistryConfig(
            registry_dict=MICROSCOPE_HANDLERS,
            key_attribute='_microscope_type',
            key_extractor=extract_key_from_handler_suffix,
            skip_if_no_key=False,
            secondary_registries=[
                SecondaryRegistry(
                    registry_dict=METADATA_HANDLERS,
                    key_source=PRIMARY_KEY,
                    attr_name='_metadata_handler_class'
                )
            ],
            log_registration=True,
            registry_name='microscope handler'
        )

        # Storage backends with explicit key and skip-if-none behavior
        RegistryConfig(
            registry_dict=STORAGE_BACKENDS,
            key_attribute='_backend_type',
            skip_if_no_key=True,
            registry_name='storage backend'
        )

        # Context providers with simple explicit key
        RegistryConfig(
            registry_dict=CONTEXT_PROVIDERS,
            key_attribute='_context_type',
            skip_if_no_key=True,
            registry_name='context provider'
        )
    """

    registry_dict: RegistryDict
    key_attribute: str
    key_extractor: KeyExtractor | None = None
    skip_if_no_key: bool = False
    secondary_registries: list[SecondaryRegistry] | None = None
    log_registration: bool = True
    registry_name: str = "plugin"
    discovery_package: str | None = None
    discovery_recursive: bool = False
    discovery_function: Callable[..., Any] | None = None  # Custom discovery function


class AutoRegisterMeta(ABCMeta):
    """
    Generic metaclass for automatic plugin registration (Pattern A).

    This metaclass automatically registers concrete classes in a global registry
    when they are defined, eliminating the need for manual registration calls.

    Features:
    - Skips abstract classes (checks __abstractmethods__)
    - Supports explicit keys via class attributes
    - Supports derived keys via key extraction functions
    - Supports secondary registries (e.g., metadata handlers)
    - Configurable skip-if-no-key behavior
    - Debug logging for registration events

    Usage:
        # Create domain-specific metaclass
        class MicroscopeHandlerMeta(AutoRegisterMeta):
            def __new__(mcs, name, bases, attrs):
                return super().__new__(mcs, name, bases, attrs,
                                      registry_config=_MICROSCOPE_REGISTRY_CONFIG)

        # Use in class definition
        class ImageXpressHandler(MicroscopeHandler, metaclass=MicroscopeHandlerMeta):
            _microscope_type = 'imagexpress'  # Optional if key_extractor is provided
            _metadata_handler_class = ImageXpressMetadata  # Optional secondary registration

    Design Principles:
    - Explicit configuration over magic behavior
    - Preserve all domain-specific features
    - Zero breaking changes to existing code
    - Easy to understand and debug
    """

    def __new__(
        mcs: type["AutoRegisterMeta"],
        name: str,
        bases: tuple[type, ...],
        attrs: dict[str, Any],
        registry_config: RegistryConfig | None = None,
        **class_kwargs: Any,
    ) -> type:
        """
        Create a new class and register it if appropriate.

        Args:
            name: Name of the class being created
            bases: Base classes
            attrs: Class attributes dictionary
            registry_config: Configuration for registration behavior.
                           If None, auto-configures from class attributes or skips registration.
            class_kwargs: Class keywords, passed on to ``__init_subclass__``.

        Returns:
            The newly created class
        """
        registry_family = attrs.get("__registry_family__")
        declared_registry_config = attrs.get("__registry_config__")
        if declared_registry_config is not None:
            if not isinstance(declared_registry_config, RegistryConfig):
                raise TypeError("__registry_config__ must be a RegistryConfig")
            if registry_config is not None and registry_config is not declared_registry_config:
                raise ValueError("Registry configuration must have one authoritative declaration")
            registry_config = declared_registry_config
        elif registry_config is None:
            inherited_registry_configs: list[RegistryConfig] = []
            for base in bases:
                inherited_registry_config = getattr(
                    base,
                    "__registry_config__",
                    None,
                )
                if not isinstance(inherited_registry_config, RegistryConfig):
                    continue
                if all(
                    inherited_registry_config is not existing_config
                    for existing_config in inherited_registry_configs
                ):
                    inherited_registry_configs.append(inherited_registry_config)
            if len(inherited_registry_configs) > 1:
                raise TypeError(f"{name} inherits multiple registry configuration authorities")
            registry_config = inherited_registry_configs[0] if inherited_registry_configs else None

        # Create the class using ABCMeta
        new_class: type = super().__new__(mcs, name, bases, attrs, **class_kwargs)
        if isinstance(registry_family, RegistryFamily):
            registry_family.apply_to_class(new_class, attrs)
        if declared_registry_config is not None:
            declared_registry = attrs.get("__registry__")
            if (
                "__registry__" in attrs
                and declared_registry is not declared_registry_config.registry_dict
            ):
                raise ValueError(
                    f"{name}.__registry__ must be the registry owned by " "its __registry_config__"
                )
            setattr(new_class, "__registry__", declared_registry_config.registry_dict)

        # Auto-configure registry if not provided but class has __registry__ attributes
        if registry_config is None:
            registry_config = mcs._auto_configure_registry(new_class, attrs)
            if registry_config is None:
                # No config and no auto-config possible
                mcs._reject_replacement_without_registration(
                    new_class, attrs, "it belongs to no registry"
                )
                return new_class

        # Set up lazy discovery if registry dict supports it (only once for base class)
        if (
            isinstance(registry_config.registry_dict, LazyDiscoveryDict)
            and not registry_config.registry_dict._config
        ):
            config = registry_config

            # Auto-wrap secondary registries with SecondaryRegistryDict
            if config.secondary_registries:
                import sys
                from dataclasses import replace

                wrapped_secondaries: list[SecondaryRegistry] = []
                module = sys.modules.get(new_class.__module__)

                for sec_reg in config.secondary_registries:
                    # Check if secondary registry needs wrapping
                    if isinstance(sec_reg.registry_dict, dict) and not isinstance(
                        sec_reg.registry_dict, SecondaryRegistryDict
                    ):
                        # Create a new SecondaryRegistryDict wrapping the primary registry
                        wrapped_dict = SecondaryRegistryDict(registry_config.registry_dict)
                        # Copy any existing entries from the old dict
                        wrapped_dict.update(sec_reg.registry_dict)

                        # Find and update the module global variable
                        if module:
                            for var_name, var_value in vars(module).items():
                                if var_value is sec_reg.registry_dict:
                                    setattr(module, var_name, wrapped_dict)
                                    logger.debug(
                                        "Auto-wrapped secondary registry %r in %s",
                                        var_name,
                                        new_class.__module__,
                                    )
                                    break

                        # Create new SecondaryRegistry with wrapped dict
                        wrapped_sec_reg = SecondaryRegistry(
                            registry_dict=wrapped_dict,
                            key_source=sec_reg.key_source,
                            attr_name=sec_reg.attr_name,
                        )
                        wrapped_secondaries.append(wrapped_sec_reg)
                    else:
                        wrapped_secondaries.append(sec_reg)

                # Rebuild config with wrapped secondary registries
                config = replace(config, secondary_registries=wrapped_secondaries)

            registry_config.registry_dict._set_config(new_class, config)

        # Only register concrete classes (not abstract base classes)
        if not bases or getattr(new_class, "__abstractmethods__", None):
            mcs._reject_replacement_without_registration(
                new_class, attrs, "it is abstract and does not register"
            )
            return new_class

        # Get or derive the registration key
        key = mcs._get_registration_key(name, new_class, registry_config)

        # Handle missing key
        if key is None:
            mcs._reject_replacement_without_registration(new_class, attrs, "it has no registry key")
            return mcs._handle_missing_key(name, registry_config, new_class)

        # Register in primary registry
        replaces = attrs.get(REPLACES_REGISTERED_ATTRIBUTE)
        if replaces is not None and not isinstance(replaces, type):
            raise TypeError(
                f"{_describe(new_class)} declares {REPLACES_REGISTERED_ATTRIBUTE} = "
                f"{replaces!r}; it must be the registered class this class replaces."
            )
        superseded = mcs._register_class(
            new_class,
            key,
            registry_config,
            replaces=replaces,
        )

        # Handle secondary registrations
        if registry_config.secondary_registries:
            mcs._register_secondary(
                new_class,
                key,
                registry_config.secondary_registries,
                superseded=superseded,
            )

        # Log registration if enabled
        if registry_config.log_registration:
            logger.debug(f"Auto-registered {name} as '{key}' {registry_config.registry_name}")

        return new_class

    @staticmethod
    def _get_registration_key(
        name: str,
        cls: type,
        config: RegistryConfig,
    ) -> RegistryKey | None:
        """Get the registration key for a class (explicit or derived)."""
        # Try explicit key first. A key that registration stamped on an
        # ancestor after deriving it is that ancestor's key, not a declaration
        # this class inherits: the class derives its own.
        key = getattr(cls, config.key_attribute, None)
        if key is not None and config.key_extractor is not None:
            key_owner = next(
                (base for base in cls.__mro__ if config.key_attribute in vars(base)),
                None,
            )
            if (
                key_owner is not None
                and key_owner is not cls
                and vars(key_owner).get(_DERIVED_KEY_MARKER, False)
            ):
                key = None
        if key is not None:
            if not isinstance(key, Hashable):
                raise TypeError(f"Registry key {key!r} declared by {cls.__name__} is not hashable")
            return key

        # Try key extractor if provided
        if config.key_extractor is not None:
            derived_key = config.key_extractor(name, cls)
            if derived_key is not None:
                setattr(cls, _DERIVED_KEY_MARKER, True)
            return derived_key

        return None

    @staticmethod
    def _handle_missing_key(name: str, config: RegistryConfig, new_class: type) -> type:
        """Handle case where no registration key is available."""
        if config.skip_if_no_key:
            if config.log_registration:
                logger.debug(f"Skipping registration for {name} - no {config.key_attribute}")
            return new_class  # Return the class, just don't register it
        else:
            raise ValueError(
                f"Class {name} must have {config.key_attribute} attribute "
                f"or provide a key_extractor in registry config"
            )

    @classmethod
    def _auto_configure_registry(
        cls: type["AutoRegisterMeta"],
        new_class: type,
        attrs: dict[str, Any],
    ) -> RegistryConfig | None:
        """
        Auto-configure registry from metaclass OR base class attributes.

        Priority:
        1. Metaclass attributes (__registry_dict__, __registry_key__ on metaclass)
        2. Base class attributes (__registry_key__ on class, auto-create __registry__)
        3. Parent class __registry__ (inherit from parent)

        Returns:
            RegistryConfig if auto-configuration successful, None otherwise
        """
        # Check if the metaclass has __registry_dict__ attribute (old style)
        registry_dict = getattr(cls, "__registry_dict__", None)

        # If no metaclass registry, check if base class wants auto-creation or inheritance
        if registry_dict is None:
            # First check if any parent class has __registry__ (inherit from parent)
            # This takes priority over creating a new registry
            for base in new_class.__mro__[1:]:  # Skip self
                if hasattr(base, "__registry__"):
                    registry_dict = getattr(base, "__registry__")
                    key_attribute = getattr(base, "__registry_key__", None)
                    key_extractor = getattr(base, "__key_extractor__", None)
                    skip_if_no_key = getattr(base, "__skip_if_no_key__", True)
                    secondary_registries = getattr(base, "__secondary_registries__", None)
                    registry_name = getattr(base, "__registry_name__", None)
                    break
            else:
                # No parent registry found - check if class explicitly defines a
                # registry family or __registry_key__ (only create new registry
                # from the class body, or from an inherited registry protocol
                # mixin that does not own a registry itself).
                registry_family = attrs.get("__registry_family__")
                key_attribute = attrs.get("__registry_key__")
                if key_attribute is None and isinstance(registry_family, RegistryFamily):
                    key_attribute = registry_family.key_attribute_name
                inherited_registry_base = None
                if key_attribute is None:
                    for base in new_class.__mro__[1:]:
                        inherited_key_attribute = getattr(base, "__registry_key__", None)
                        if inherited_key_attribute is not None:
                            inherited_registry_base = base
                            key_attribute = inherited_key_attribute
                            break
                if key_attribute is not None:
                    # Check if class already provides its own __registry__ dict
                    # (allows opting out of LazyDiscoveryDict)
                    if "__registry__" in attrs:
                        registry_dict = attrs["__registry__"]
                    else:
                        # Auto-create registry dict and store on the class
                        registry_dict = LazyDiscoveryDict()
                        setattr(new_class, "__registry__", registry_dict)

                    # Get other optional attributes from class. Explicit legacy
                    # class attributes override the family/inherited declaration.
                    key_extractor = attrs.get("__key_extractor__")
                    if key_extractor is None and inherited_registry_base is not None:
                        key_extractor = getattr(inherited_registry_base, "__key_extractor__", None)
                    if "__skip_if_no_key__" in attrs:
                        skip_if_no_key = attrs["__skip_if_no_key__"]
                    elif isinstance(registry_family, RegistryFamily):
                        skip_if_no_key = registry_family.skip_if_no_key
                    elif inherited_registry_base is not None:
                        skip_if_no_key = getattr(
                            inherited_registry_base, "__skip_if_no_key__", True
                        )
                    else:
                        skip_if_no_key = True
                    secondary_registries = attrs.get("__secondary_registries__")
                    if secondary_registries is None and inherited_registry_base is not None:
                        secondary_registries = getattr(
                            inherited_registry_base, "__secondary_registries__", None
                        )
                    if "__registry_name__" in attrs:
                        registry_name = attrs["__registry_name__"]
                    elif isinstance(registry_family, RegistryFamily):
                        registry_name = registry_family.registry_name
                    elif inherited_registry_base is not None:
                        registry_name = getattr(inherited_registry_base, "__registry_name__", None)
                    else:
                        registry_name = None
                else:
                    return None  # No registry configuration found
        else:
            # Old style: get from metaclass
            key_attribute = getattr(cls, "__registry_key__", "_registry_key")
            key_extractor = getattr(cls, "__key_extractor__", None)
            skip_if_no_key = getattr(cls, "__skip_if_no_key__", True)
            secondary_registries = getattr(cls, "__secondary_registries__", None)
            registry_name = getattr(cls, "__registry_name__", None)

        # Auto-derive registry name if not provided
        if registry_name is None:
            # Derive from class name: "StorageBackend" → "storage backend"
            # The family is named after the class that owns the registry, so
            # messages about any member name the family.
            registry_owner = next(
                (base for base in new_class.__mro__ if "__registry__" in vars(base)),
                new_class,
            )
            clean_name = registry_owner.__name__
            for suffix in ["Base", "Meta", "Handler", "Registry"]:
                if clean_name.endswith(suffix):
                    clean_name = clean_name[: -len(suffix)]
                    break
            # Convert CamelCase to space-separated lowercase
            import re

            registry_name = re.sub(r"([A-Z])", r" \1", clean_name).strip().lower()

        logger.debug(
            f"Auto-configured registry for {new_class.__name__}: "
            f"key_attribute={key_attribute}, registry_name={registry_name}"
        )

        if not isinstance(key_attribute, str):
            raise TypeError(f"Registry key attribute for {new_class.__name__} must be a string")

        return RegistryConfig(
            registry_dict=registry_dict,
            key_attribute=key_attribute,
            key_extractor=key_extractor,
            skip_if_no_key=skip_if_no_key,
            secondary_registries=secondary_registries,
            registry_name=registry_name,
        )

    @staticmethod
    def _reject_replacement_without_registration(
        cls: type,
        attrs: dict[str, Any],
        reason: str,
    ) -> None:
        """A declared replacement that replaces nothing is an error, not a no-op."""
        replaces = attrs.get(REPLACES_REGISTERED_ATTRIBUTE)
        if replaces is None:
            return
        raise DuplicateRegistryKeyError(
            f"{_describe(cls)} declares {REPLACES_REGISTERED_ATTRIBUTE} = "
            f"{_describe(replaces)}, but {reason}."
        )

    @staticmethod
    def _register_class(
        cls: type,
        key: RegistryKey,
        config: RegistryConfig,
        replaces: object = None,
    ) -> type | None:
        """Register class in primary registry; return the class it took the key from."""
        superseded: type | None = register_once(
            config.registry_dict,
            key,
            cls,
            registry_name=config.registry_name,
            replaces=replaces,
        )
        setattr(cls, config.key_attribute, key)
        if _DECLARATION_TOKEN not in vars(cls):
            setattr(cls, _DECLARATION_TOKEN, object())
        return superseded

    @staticmethod
    def _register_secondary(
        cls: type,
        primary_key: RegistryKey,
        secondary_registries: list[SecondaryRegistry],
        superseded: type | None = None,
    ) -> None:
        """Handle secondary registry registrations."""
        for sec_reg in secondary_registries:
            value = getattr(cls, sec_reg.attr_name, None)
            if value is None:
                continue

            # Determine the key for secondary registration
            secondary_key: RegistryKey
            if sec_reg.key_source == PRIMARY_KEY:
                secondary_key = primary_key
            else:
                declared_secondary_key = getattr(cls, sec_reg.key_source, None)
                if declared_secondary_key is None:
                    logger.warning(
                        f"Cannot register {sec_reg.attr_name} for {cls.__name__} - "
                        f"no {sec_reg.key_source} attribute"
                    )
                    continue
                if not isinstance(declared_secondary_key, Hashable):
                    raise TypeError(
                        f"Secondary registry key {declared_secondary_key!r} declared "
                        f"by {cls.__name__} is not hashable"
                    )
                secondary_key = declared_secondary_key

            # Register in secondary registry. The value registered by the
            # class this one took the primary key from goes with it.
            superseded_value = (
                None if superseded is None else getattr(superseded, sec_reg.attr_name, None)
            )
            register_once(
                sec_reg.registry_dict,
                secondary_key,
                value,
                registry_name=f"{sec_reg.attr_name} (secondary registry of {cls.__name__})",
                superseded_values=() if superseded_value is None else (superseded_value,),
            )
            logger.debug(
                f"Auto-registered {sec_reg.attr_name} from {cls.__name__} as '{secondary_key}'"
            )


class RegisteredEnumMeta(AutoRegisterMeta, EnumMeta):
    """Metaclass for enum families that also need AutoRegisterMeta membership."""


# Helper functions for common key extraction patterns


def extract_key_from_class_name(name: str, cls: type) -> str:
    """Use the concrete class name as its registry key."""
    return name


def make_suffix_extractor(suffix: str) -> KeyExtractor:
    """
    Create a key extractor that removes a suffix from class names.

    Args:
        suffix: The suffix to remove (e.g., 'Handler', 'Backend')

    Returns:
        A key extractor function

    Examples:
        extract_handler = make_suffix_extractor('Handler')
        extract_handler('ImageXpressHandler', cls) -> 'imagexpress'

        extract_backend = make_suffix_extractor('Backend')
        extract_backend('DiskStorageBackend', cls) -> 'diskstorage'
    """
    suffix_len = len(suffix)

    def extractor(name: str, cls: type) -> str:
        if name.endswith(suffix):
            return name[:-suffix_len].lower()
        return name.lower()

    return extractor


# Pre-built extractors for common patterns
extract_key_from_handler_suffix = make_suffix_extractor("Handler")
extract_key_from_backend_suffix = make_suffix_extractor("Backend")
