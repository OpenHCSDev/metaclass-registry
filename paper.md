---
title: 'metaclass-registry: Zero-Boilerplate Plugin Registration via Python Metaclasses'
tags:
  - Python
  - plugin systems
  - metaclasses
  - software architecture
authors:
  - name: Tristan Simas
    orcid: 0000-0002-6526-3149
    affiliation: 1
affiliations:
  - name: McGill University
    index: 1
date: 13 January 2026
bibliography: paper.bib
---

# Summary

`metaclass-registry` registers Python classes in a registry when they are defined. A root class uses the metaclass `AutoRegisterMeta` and names the class attribute that holds each member's key. Every concrete subclass is then stored under its key, with no configuration file, decorator or dictionary insertion:

```python
from metaclass_registry import AutoRegisterMeta

class StorageBackend(metaclass=AutoRegisterMeta):
    __registry_key__ = "_backend_type"

class ZarrBackend(StorageBackend):
    _backend_type = "zarr"

assert StorageBackend.__registry__["zarr"] is ZarrBackend
```

A key names one class: a different class that claims a taken key raises `DuplicateRegistryKeyError`, unless it declares the replacement with `__replaces_registered__`. A root that declares a discovery package gets its plugin modules imported on first registry access, with a validated disk cache. Roots can also declare secondary registries and a key extractor that derives keys from class names.

# Statement of Need

Applications with storage backends, file format handlers, hardware drivers or GUI widgets need plugin registration. The standard Python approaches each have a cost:

**Setuptools entry points** require `pyproject.toml` configuration per plugin and package installation, which is deployment work with no benefit for plugins inside one application.

**Explicit registration** (`BACKENDS["zarr"] = ZarrBackend` or `@register`) is easy to forget: a class without its registration call is absent, with no error. Two classes can also write the same key, and the second silently displaces the first.

**Manual discovery** (`pkgutil.iter_modules` plus `importlib.import_module`) is the same scanning loop written again for each registry.

`metaclass-registry` replaces all three. The root class states the registry configuration once, and each member's class statement is its registration, so there is no second table to keep in step. Since 0.4.0 a collision between two members is an error instead of a silent replacement.

# State of the Field

**Stevedore** [@stevedore] manages plugins via setuptools entry points. It provides driver managers and extension managers but requires entry point configuration in `pyproject.toml` for each plugin class.

**Pluggy** [@pluggy] powers pytest's hook system. It provides hook calling with ordering and wrappers but requires `@hookimpl` decorators and explicit `register()` calls. It targets hook-based extensibility rather than class registration.

`metaclass-registry` targets a different use case: **plugins inside an application whose code the developer controls**.

| Feature | metaclass-registry | Stevedore | pluggy |
|---------|-------------------|-----------|--------|
| Zero config files | ✓ | ✗ | ✗ |
| Zero registration calls | ✓ | ✗ | ✗ |
| Lazy discovery | ✓ | ✓ | ✗ |
| Disk caching with mtime | ✓ | ✓ | ✗ |
| Secondary registries | ✓ | ✗ | ✗ |
| Works without install | ✓ | ✗ | ✓ |

# Software Design

A root declares `__registry_key__` as above, or one `RegistryConfig` that owns the registry, the key attribute and the discovery package:

```python
from metaclass_registry import LazyDiscoveryDict, RegistryConfig

class BackendBase(metaclass=AutoRegisterMeta):
    __registry_config__ = RegistryConfig(
        registry_dict=LazyDiscoveryDict(),
        key_attribute='_backend_type',
        skip_if_no_key=True,
        discovery_package='polystore',
    )
```

**Registration.** When Python executes a subclass statement, `AutoRegisterMeta.__new__` reads the key and stores the class. The root and classes with unimplemented abstract methods are not registered. The key is the value of the key attribute, inherited values included. If there is none and the root declares a key extractor (for example `make_suffix_extractor("Backend")`), the key is derived from the class name. A class with no key is skipped or raises `ValueError`, according to `skip_if_no_key`.

**One class per key.** Registering the same class object again does nothing. A new class object from the same class statement (same module and qualified name, as after `importlib.reload`) takes the key from the old one. Any other class raises `DuplicateRegistryKeyError`, naming the registry, the key and both classes; this includes a subclass that inherits a registered parent's declared key. Replacement is declared by the replacing class and is not inherited:

```python
class ChunkedZarrBackend(ZarrBackend):
    __replaces_registered__ = ZarrBackend
```

The key must currently hold exactly the named class, and a declaration on a class that does not register raises. The same rule covers secondary registries and entries loaded from the discovery cache; `register_once` applies it to dictionaries filled by hand.

**Lazy discovery** applies only when the `RegistryConfig` declares a `discovery_package`. `LazyDiscoveryDict` overrides its read methods (`__getitem__`, `__contains__`, iteration) to scan the package with `pkgutil.iter_modules` and import its modules on first use. The result is written to `~/.cache/metaclass-registry/` (or under `$XDG_CACHE_HOME`). A later start imports the recorded classes directly instead of scanning, provided the root package's `__version__` is unchanged, the cache is under seven days old, and the package's `.py` files are the same set with the same modification times. A module that fails to import during a scan is logged and skipped, so its classes are absent; a duplicate key propagates. Roots without a discovery package hold only the classes the application has imported.

**Secondary registries** store a value declared by each member, under the member's key or a key read from another attribute:

```python
METADATA_HANDLERS = {}

class MicroscopeHandler(metaclass=AutoRegisterMeta):
    __registry__ = {}
    __registry_key__ = '_microscope_type'
    __secondary_registries__ = [
        SecondaryRegistry(
            registry_dict=METADATA_HANDLERS,
            key_source=PRIMARY_KEY,
            attr_name='_metadata_handler_class'
        )
    ]

class ImageXpressHandler(MicroscopeHandler):
    _microscope_type = 'imagexpress'
    _metadata_handler_class = ImageXpressMetadata
```

Defining `ImageXpressHandler` fills both `MicroscopeHandler.__registry__['imagexpress']` and `METADATA_HANDLERS['imagexpress']`. The root here supplies a plain dict as its registry.

**Thread safety.** A `LazyDiscoveryDict` holds a reentrant `threading.RLock` throughout discovery and takes it on every read, so no reader sees a partly filled registry. Registration takes no lock.

# Research Impact Statement

`metaclass-registry` is a dependency of the OpenHCS microscopy platform and its libraries:

- **openhcs**: 240 class statements use `AutoRegisterMeta`; the roots with a discovery package include `LibraryRegistryBase` and `SessionOperation`
- **polystore**: `BackendBase` (storage backends, discovered in the `polystore` package)
- **arraybridge**: `ArrayLibrary` (one class per array library) and `ConversionRoute`
- **pyqt-reactor**: `CellEditor` and `WidgetDescriptorProjector`, among others

# AI Usage Disclosure

Generative AI (Claude) assisted with code generation and documentation. All content was reviewed and tested against the implementation.

# Acknowledgements

This work was supported in part by the Fournier lab at the Montreal Neurological Institute, McGill University.

# References
