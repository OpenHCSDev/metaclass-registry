"""
Generic registry class discovery utility.

Consolidates duplicated registry discovery patterns across:
- Library registries (processing backends)
- Format registries (experimental analysis)
- Microscope handler registries
- Storage backend registries

This module eliminates ~70 lines of duplicated pkgutil + importlib boilerplate
by providing a single, well-tested discovery function.
"""

import importlib
import inspect
import logging
import pkgutil
import threading
from collections.abc import Callable, Iterable
from types import ModuleType

logger = logging.getLogger(__name__)
_ROOT_LOGGING_IMPORT_LOCK = threading.RLock()


def import_module_preserving_root_logging(
    module_name: str,
    package: str | None = None,
) -> ModuleType:
    """Import a module without transferring root-logger ownership to it.

    Plugin and callable discovery imports code owned by third parties. Some
    packages configure the process root logger at import time, which can replace
    application handlers or write diagnostics into machine-readable stdout.
    Discovery owns importing those modules, but the hosting application retains
    ownership of root logging.

    A temporary handler prevents ordinary ``logging.basicConfig`` calls from
    installing handlers. The prior root handler set, level, disabled state, and
    global logging threshold are restored even when the import fails. Named
    package loggers remain under the imported package's control.
    """

    with _ROOT_LOGGING_IMPORT_LOCK:
        root_logger = logging.getLogger()
        previous_handlers = tuple(root_logger.handlers)
        previous_level = root_logger.level
        previous_disabled = root_logger.disabled
        previous_disable_threshold = root_logger.manager.disable
        guard_handler = logging.NullHandler()
        root_logger.handlers = [guard_handler]
        try:
            return importlib.import_module(module_name, package)
        finally:
            temporary_handlers = tuple(root_logger.handlers)
            root_logger.handlers = list(previous_handlers)
            root_logger.setLevel(previous_level)
            root_logger.disabled = previous_disabled
            logging.disable(previous_disable_threshold)
            previous_handler_ids = {id(handler) for handler in previous_handlers}
            for handler in temporary_handlers:
                if id(handler) not in previous_handler_ids:
                    handler.close()


def discover_registry_classes(
    package_path: Iterable[str],
    package_prefix: str,
    base_class: type,
    exclude_modules: set[str] | None = None,
    validation_func: Callable[[type], bool] | None = None,
    skip_packages: bool = True,
) -> list[type]:
    """
    Generic registry class discovery using pkgutil + importlib pattern.

    Scans a package for classes that inherit from a base class and automatically
    discovers them for registration. This eliminates duplicated discovery code
    across different registry systems.

    Args:
        package_path: Package __path__ attribute to scan (e.g., openhcs.io.__path__)
                     Accepts any iterable of strings (List, Tuple, _NamespacePath, etc.)
        package_prefix: Module prefix for importlib (e.g., "openhcs.io.")
        base_class: Base class to filter for (e.g., StorageBackend)
        exclude_modules: Set of module name substrings to skip (e.g., {'base', 'registry'})
        validation_func: Optional function to validate discovered classes
                        Should return True to include, False to exclude
        skip_packages: If True, skip package directories (default: True)

    Returns:
        List of discovered registry classes

    Example:
        >>> from openhcs.io.base import StorageBackend
        >>> import openhcs.io
        >>> backends = discover_registry_classes(
        ...     package_path=openhcs.io.__path__,
        ...     package_prefix="openhcs.io.",
        ...     base_class=StorageBackend,
        ...     exclude_modules={'base', 'backend_registry'}
        ... )
        >>> print([b.__name__ for b in backends])
        ['DiskStorageBackend', 'MemoryStorageBackend', 'ZarrStorageBackend']
    """
    registry_classes = []
    exclude_modules = exclude_modules or set()

    logger.debug(
        f"Discovering registry classes: base={base_class.__name__}, "
        f"prefix={package_prefix}, exclude={exclude_modules}"
    )

    for importer, module_name, ispkg in pkgutil.iter_modules(package_path, package_prefix):
        # Skip packages if requested
        if ispkg and skip_packages:
            continue

        # Skip excluded modules
        if any(excluded in module_name for excluded in exclude_modules):
            logger.debug(f"Skipping excluded module: {module_name}")
            continue

        try:
            # Import the module
            module = import_module_preserving_root_logging(module_name)

            # Find all classes in the module
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # Filter for subclasses of base_class
                if not issubclass(obj, base_class):
                    continue

                # Exclude the base class itself
                if obj is base_class:
                    continue

                # Only include classes defined in this module (not imported)
                if obj.__module__ != module_name:
                    continue

                # Apply optional validation function
                if validation_func and not validation_func(obj):
                    logger.debug(f"Validation failed for {obj.__name__}")
                    continue

                logger.debug(f"Discovered registry class: {obj.__name__} from {module_name}")
                registry_classes.append(obj)

        except ImportError as e:
            # Skip modules that can't be imported (e.g., missing optional dependencies)
            logger.debug(f"Could not import module {module_name}: {e}")
            continue
        except Exception as e:
            # Log unexpected errors but continue discovery
            logger.warning(f"Failed to load registry module {module_name}: {e}")
            continue

    logger.info(
        f"Discovered {len(registry_classes)} registry classes for {base_class.__name__}: "
        f"{[cls.__name__ for cls in registry_classes]}"
    )

    return registry_classes


def discover_registry_classes_recursive(
    package_path: Iterable[str],
    package_prefix: str,
    base_class: type,
    exclude_modules: set[str] | None = None,
    validation_func: Callable[[type], bool] | None = None,
) -> list[type]:
    """
    Recursive version of discover_registry_classes that walks entire package tree.

    Uses pkgutil.walk_packages instead of iter_modules to recursively scan
    all subpackages. Useful for deeply nested registry structures.

    Args:
        package_path: Package __path__ attribute to scan
                     Accepts any iterable of strings (List, Tuple, _NamespacePath, etc.)
        package_prefix: Module prefix for importlib
        base_class: Base class to filter for
        exclude_modules: Set of module name substrings to skip
        validation_func: Optional function to validate discovered classes

    Returns:
        List of discovered registry classes

    Example:
        >>> from openhcs.processing.backends.lib_registry.unified_registry import (
        ...     LibraryRegistryBase,
        ... )
        >>> import openhcs.processing.backends.experimental_analysis
        >>> registries = discover_registry_classes_recursive(
        ...     package_path=openhcs.processing.backends.experimental_analysis.__path__,
        ...     package_prefix="openhcs.processing.backends.experimental_analysis.",
        ...     base_class=MicroscopeFormatRegistryBase,
        ...     exclude_modules={'base'}
        ... )
    """
    registry_classes = []
    exclude_modules = exclude_modules or set()

    logger.debug(
        f"Discovering registry classes (recursive): base={base_class.__name__}, "
        f"prefix={package_prefix}, exclude={exclude_modules}"
    )

    # Walk through all modules in the package tree
    for importer, modname, ispkg in pkgutil.walk_packages(package_path, prefix=package_prefix):
        # Skip packages (only process modules)
        if ispkg:
            continue

        # Skip excluded modules
        if any(excluded in modname for excluded in exclude_modules):
            logger.debug(f"Skipping excluded module: {modname}")
            continue

        try:
            # Import the module
            module = import_module_preserving_root_logging(modname)

            # Find all classes in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)

                # Check if it's a class
                if not isinstance(attr, type):
                    continue

                # Check if it's a subclass of base_class
                if not issubclass(attr, base_class):
                    continue

                # Exclude the base class itself
                if attr is base_class:
                    continue

                # Apply optional validation function
                if validation_func and not validation_func(attr):
                    logger.debug(f"Validation failed for {attr.__name__}")
                    continue

                logger.debug(f"Discovered registry class: {attr.__name__} from {modname}")
                registry_classes.append(attr)

        except ImportError as e:
            # Skip modules that can't be imported
            logger.debug(f"Could not import module {modname}: {e}")
            continue
        except Exception as e:
            # Log unexpected errors but continue discovery
            logger.warning(f"Failed to load registry module {modname}: {e}")
            continue

    logger.info(
        "Discovered %d registry classes (recursive) for %s: %s",
        len(registry_classes),
        base_class.__name__,
        [cls.__name__ for cls in registry_classes],
    )

    return registry_classes
