"""Bounded value caches and the process-local cache family.

``BoundedCache`` is a plain LRU whose lifetime belongs to whoever holds it.
``ProcessLocalBoundedCache`` is a registered family: every subclass is a member by
inheritance and owns one process-local singleton, so a whole family (or any
subfamily) can be cleared without a roster of cache types.
"""

from __future__ import annotations

from _thread import LockType
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, ClassVar, Generic, TypeVar, cast

from .core import AutoRegisterMeta, RegistryConfig, RegistryDict

CacheKey = TypeVar("CacheKey")
CachedValue = TypeVar("CachedValue")
_ProcessCacheT = TypeVar("_ProcessCacheT", bound="ProcessLocalBoundedCache[Any, Any]")


@dataclass(slots=True)
class BoundedCache(Generic[CacheKey, CachedValue]):
    """Bounded LRU values with lifetime supplied by their owning consumer."""

    max_entries: int = 4096
    entries: OrderedDict[CacheKey, CachedValue] = field(default_factory=OrderedDict)

    def cached_value(self, key: CacheKey) -> CachedValue | None:
        if key not in self.entries:
            return None
        value = self.entries[key]
        self.entries.move_to_end(key)
        return value

    def store_value(self, key: CacheKey, value: CachedValue) -> CachedValue:
        self.entries[key] = value
        self.entries.move_to_end(key)
        while len(self.entries) > self.max_entries:
            self.entries.popitem(last=False)
        return value

    def clear(self) -> None:
        """Discard all values retained by this cache instance."""
        self.entries.clear()


@dataclass
class SynchronizedBoundedCache(BoundedCache[CacheKey, CachedValue]):
    """Bounded storage whose individual mutations share one instance lock."""

    _lock: LockType = field(default_factory=Lock, init=False, repr=False, compare=False)

    def cached_value(self, key: CacheKey) -> CachedValue | None:
        with self._lock:
            return super().cached_value(key)

    def store_value(self, key: CacheKey, value: CachedValue) -> CachedValue:
        with self._lock:
            return super().store_value(key, value)

    def clear(self) -> None:
        with self._lock:
            super().clear()


def _module_class_name(name: str, cls: type) -> str:
    # ``dataclass(slots=True)`` rebuilds a class before restoring its ``__qualname__``,
    # so the key uses ``__name__`` and the rebuilt class replaces its predecessor.
    return f"{cls.__module__}.{name}"


_PROCESS_CACHE_FAMILY: RegistryDict = {}


@dataclass(slots=True)
class ProcessLocalBoundedCache(
    BoundedCache[CacheKey, CachedValue],
    metaclass=AutoRegisterMeta,
):
    """Bounded values with one process-local singleton per class.

    Subclassing is membership: each subclass registers under ``module.ClassName``
    and gets its own singleton and lock, so a warmed parent never becomes a
    child's singleton and ``clear_process_caches`` reaches every member.
    """

    __registry_config__: ClassVar[RegistryConfig] = RegistryConfig(
        registry_dict=_PROCESS_CACHE_FAMILY,
        key_attribute="process_cache_key",
        key_extractor=_module_class_name,
        registry_name="process-local cache",
        log_registration=False,
    )
    __registry__: ClassVar[RegistryDict] = _PROCESS_CACHE_FAMILY

    process_cache_key: ClassVar[str | None] = None
    _process_cache: ClassVar[ProcessLocalBoundedCache[Any, Any] | None] = None
    _process_cache_lock: ClassVar[LockType] = Lock()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        # slots=True replaces the class; name the final class for cooperative super.
        super(ProcessLocalBoundedCache, cls).__init_subclass__(**kwargs)
        cls._process_cache = None
        cls._process_cache_lock = Lock()
        cls.process_cache_key = None

    @classmethod
    def process_cache(cls: type[_ProcessCacheT]) -> _ProcessCacheT:
        """Return this class's process-local singleton, creating it once."""
        cache = cls._process_cache
        if cache is None:
            with cls._process_cache_lock:
                cache = cls._process_cache
                if cache is None:
                    cache = cls()
                    cls._process_cache = cache
        return cast(_ProcessCacheT, cache)

    @classmethod
    def clear_process_cache(cls) -> None:
        """Discard the values held by this class's singleton, keeping the singleton."""
        cache = cls._process_cache
        if cache is not None:
            cache.clear()

    @classmethod
    def clear_process_caches(cls) -> None:
        """Clear the singleton of every registered member that subclasses ``cls``."""
        for cache_type in tuple(cls.__registry__.values()):
            if issubclass(cache_type, cls):
                cache_type.clear_process_cache()


class IdentityBoundProcessCache(ProcessLocalBoundedCache[int, tuple[object, Any]]):
    """Process-local values bound to an owner object, protected against ``id`` reuse."""

    def get_bound(self, owner: object) -> Any | None:
        cache_key = id(owner)
        cached = self.cached_value(cache_key)
        if cached is None:
            return None
        cached_owner, value = cached
        if cached_owner is not owner:
            del self.entries[cache_key]
            return None
        return value

    def put_bound(self, owner: object, value: Any) -> Any:
        return self.store_value(id(owner), (owner, value))[1]
