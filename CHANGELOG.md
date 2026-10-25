# Changelog

## Unreleased

- `metaclass_registry.mro_dispatch`: `MroDispatch` and `handles`, moved from
  `agent_comms.mro_dispatch`. A consumer declares `@handles(SomeClass)` on its
  methods; dispatch runs the handlers along the value's MRO, most specific
  first, so a handler on `ast.stmt` also receives every statement subclass.
  A handler may return a same-type replacement or `DISCARD`.

## 0.4.1

- P54: `LazyDiscoveryDict` accepts a declared module as well as a package.
  A module is imported once; only packages have child modules to scan.
- Discovery import and declaration errors now raise instead of publishing an
  incomplete registry as discovered. Explicit module exclusions and selection
  still decide eligibility before import.
- Module cache inventories contain that module's source, not its neighbours.

## 0.4.0

Behaviour change: a registry key names one class.

- Registering a different class under a key that already holds a class raises
  `DuplicateRegistryKeyError` (a `RegistryError`) naming the family, the key
  and both classes. Before, the second class silently replaced the first, so
  nothing reading the registry could tell that a class had been displaced.
  The same rule applies to secondary registries and to entries loaded from the
  discovery cache.
- Not a conflict: the same class object again, and the same class statement
  created again (equal `__module__` and `__qualname__`, as produced by
  `importlib.reload`, a re-import, or a second run of one function body; or a
  class rebuilt from a copy of the registered class's namespace, as
  `dataclass(slots=True)` does). The new object takes the key.
- Intentional replacement is declared in the replacing class body:
  `__replaces_registered__ = OtherClass`. It is not inherited, and the key
  must currently hold exactly `OtherClass`. A secondary entry registered by
  the replaced class goes with it. The declaration must be a class, and a
  class that declares it without registering (abstract, no key, no registry)
  raises: a declared replacement that replaces nothing is an error.
- `register_once(registry, key, value, registry_name=...)` and
  `is_same_declaration(a, b)` are public, for registries that are filled by
  hand.
- `metaclass_registry.testing.restored_registry(family, released=(...))` lets a
  test define stand-in members under released keys and restores the registry
  exactly afterwards.
- Fix: a subclass of a registered class whose key came from the family's key
  extractor derives its own key. Before, it inherited the key stamped on its
  parent and displaced the parent.
- `DuplicateRegistryKeyError` propagates through discovery instead of being
  logged as a skipped module, and a discovery that fails this way is not
  recorded as complete.
- The derived name of a family (used in messages) comes from the class that
  owns the registry, not from the member being registered.

Migration: give each colliding class its own key, or declare
`__replaces_registered__`. Tests that define throwaway members of a shared
family need unique keys or their own family.

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
