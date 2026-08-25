# metaclass-registry

**Zero-boilerplate metaclass-driven plugin registry system with lazy discovery and caching**

[![PyPI version](https://badge.fury.io/py/metaclass-registry.svg)](https://badge.fury.io/py/metaclass-registry)
[![Documentation Status](https://readthedocs.org/projects/metaclass-registry/badge/?version=latest)](https://metaclass-registry.readthedocs.io/en/latest/?badge=latest)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Coverage](https://raw.githubusercontent.com/OpenHCSDev/metaclass-registry/main/.github/badges/coverage.svg)](https://openhcsdev.github.io/metaclass-registry/coverage/)

## Features

- **Zero Boilerplate**: No custom metaclasses, no manual registry creation, just class attributes
- **Lazy Discovery**: Plugins discovered automatically on first access
- **Registry Inheritance**: Child classes inherit parent's registry for clean interface hierarchies
- **Secondary Registries**: Auto-populate related registries from primary registry
- **Persistent Caching**: Cache discovery results across process restarts
- **Explicit Discovery**: Package scans occur only when the nominal root declares them
- **Host Logging Safety**: Discovery imports preserve application-owned root logging
- **Nominal Registry Families**: Stable key-axis declarations with
  ``RegistryFamily`` and ``RegistryKeyAttribute``
- **Registered Enums**: ``RegisteredEnumMeta`` for enum members backed by a
  nominal registry
- **Type-Safe**: Full type hints and mypy support

## Quick Start

```python
from metaclass_registry import AutoRegisterMeta, RegistryFamily

# Define the nominal family and its semantic key axis.
class PluginBase(metaclass=AutoRegisterMeta):
    __registry_family__ = RegistryFamily(
        "plugin_name",
        registry_name="plugin",
    )
    __registry__ = {}  # Local script: no package discovery required.
    plugin_name = None

# Access the auto-created registry
PLUGINS = PluginBase.__registry__

# Define plugins - they auto-register!
class MyPlugin(PluginBase):
    plugin_name = 'my_plugin'
    
    def run(self):
        return "Hello from my plugin!"

# Use the registry
print(list(PLUGINS.keys()))  # ['my_plugin']
plugin = PLUGINS['my_plugin']()
print(plugin.run())  # "Hello from my plugin!"
```

``RegistryFamily`` is the preferred declaration for an ordinary nominal root.
It installs the compatibility attributes used by ``AutoRegisterMeta`` while
keeping the key axis in one object. Consumers should iterate or query
``PluginBase.__registry__`` rather than maintain a parallel plugin mapping.
The explicit plain registry is appropriate for this one-file example. Ordinary roots
register declarations as their modules are imported; package discovery is opt-in through
``RegistryConfig.discovery_package``.

Use ``RegistryConfig`` when a family needs a supplied registry, a key extractor,
lazy discovery, secondary registries, or custom logging:

```python
from metaclass_registry import (
    AutoRegisterMeta,
    RegistryConfig,
    make_suffix_extractor,
)

HANDLERS = {}
HANDLER_CONFIG = RegistryConfig(
    registry_dict=HANDLERS,
    key_attribute="handler_type",
    key_extractor=make_suffix_extractor("Handler"),
    skip_if_no_key=True,
    registry_name="handler",
)

class Handler(metaclass=AutoRegisterMeta):
    __registry_config__ = HANDLER_CONFIG
    handler_type = None

class FileHandler(Handler):
    pass

assert HANDLERS["file"] is FileHandler
```

### Package discovery

Package discovery is explicit in 0.2.0. A nominal root that must discover declarations
which are not otherwise imported owns that behavior directly:

```python
from metaclass_registry import AutoRegisterMeta, LazyDiscoveryDict, RegistryConfig

class Plugin(metaclass=AutoRegisterMeta):
    __registry_config__ = RegistryConfig(
        registry_dict=LazyDiscoveryDict(),
        key_attribute="plugin_name",
        discovery_package="my_application.plugins",
        discovery_recursive=False,
    )
    plugin_name = None
```

Use ``discovery_recursive=True`` only when plugin declarations live in subpackages.
Without ``discovery_package``, the registry contains declarations imported by the
application and never scans the surrounding package implicitly.

## Installation

```bash
pip install metaclass-registry
```

## Why metaclass-registry?

Most plugin systems require boilerplate code:

**Before** (Traditional approach):
```python
# Custom metaclass per registry
class PluginMeta(type):
    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        if hasattr(cls, 'plugin_name') and cls.plugin_name:
            PLUGINS[cls.plugin_name] = cls
        return cls

# Manual registry creation
PLUGINS = {}

# Base class with custom metaclass
class PluginBase(metaclass=PluginMeta):
    plugin_name = None
```

**After** (metaclass-registry):
```python
# One nominal family declaration owns the registry protocol.
class PluginBase(metaclass=AutoRegisterMeta):
    __registry_family__ = RegistryFamily("plugin_name")
    plugin_name = None

# Access auto-created registry
PLUGINS = PluginBase.__registry__
```

## Advanced Features

### Registry Inheritance

```python
class BackendBase(metaclass=AutoRegisterMeta):
    __registry_family__ = RegistryFamily("backend_type")
    backend_type = None

class StorageBackend(BackendBase):
    pass  # Inherits BackendBase.__registry__

class ReadOnlyBackend(BackendBase):
    pass  # Also inherits BackendBase.__registry__

# All share the SAME registry!
assert StorageBackend.__registry__ is BackendBase.__registry__
```

### Secondary Registries

Pass ``SecondaryRegistry`` declarations through the family's authoritative
``RegistryConfig``. Secondary mappings are derived indexes; populate them only
through registration, never through a second manual registration path.

### Custom Key Extractors

Set ``RegistryConfig.key_extractor`` when names must be derived. The extractor
receives ``(class_name, cls)`` and should return the semantic key. Prefer an
explicit family key attribute when the declaration can own the value directly.

## Documentation

Full documentation available at [metaclass-registry.readthedocs.io](https://metaclass-registry.readthedocs.io)

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome through the
[repository](https://github.com/OpenHCSDev/metaclass-registry) and its
[issue tracker](https://github.com/OpenHCSDev/metaclass-registry/issues).

## Credits

Developed by Tristan Simas as part of the OpenHCS project.
