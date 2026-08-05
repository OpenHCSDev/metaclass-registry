# Changelog

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
