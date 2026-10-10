# Changelog

## 0.3.0

- Add `metaclass_registry.strategies`: enum-keyed, nominal-type-keyed and
  most-derived-context strategy family mixins, generated leaf class specs and
  enum payload helpers. Cached registry views are rebuilt when a family gains a
  member, so a strategy declared after the first lookup is selected.
- Add `metaclass_registry.caches`: `BoundedCache`, `SynchronizedBoundedCache`,
  and the `ProcessLocalBoundedCache` family, whose members register by
  inheritance and are cleared together by `clear_process_caches()`;
  `IdentityBoundProcessCache` binds values to owner identity.
- `AutoRegisterMeta` forwards class keywords to `__init_subclass__`.

## 0.2.2

- Add `LazyDiscoveryDict.discover_matching` for declaration-selected, flat
  discovery through the original importer and registration owner. Partial
  admission does not publish the full-discovery flag or cache; selected import
  and declaration failures propagate. Explicit full discovery retains exact
  registered identities.
- Avoid creating an empty persistent discovery cache merely by probing it.

## 0.2.1

- Preserve host-owned root logging while importing discovery modules, including
  modules that call `logging.basicConfig(..., force=True)` during import.
- Remove the string-keyed lazy cache-component map and use the cache declarations
  directly.
- Type registry keys by their actual hashable contract, validate declaration keys,
  and preserve non-string keys when restoring a pickled lazy registry.
- Restore green Ruff, Black, and mypy source gates.

## 0.2.0

- Make package discovery an explicit nominal-root declaration. Ordinary
  `AutoRegisterMeta` registries now contain classes imported by the application and do
  not infer a package or recursive scan from module layout.
- Accept `RegistryConfig` directly as a root's `__registry_config__`, with the registry,
  key axis, discovery package, and cache behavior owned by that single declaration.
- Invalidate persistent discovery caches when Python source files are added as well as
  when existing files are modified or removed.
- Preserve exact imported class identity when reconstructing a registry from cache.

Migration: a registry that needs lazy package discovery must declare a
`LazyDiscoveryDict` and `discovery_package` in its root-owned `__registry_config__`.
Set `discovery_recursive=True` only when discovery must traverse subpackages.
