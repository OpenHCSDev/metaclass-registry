"""Family-level tests for metaclass_registry.caches."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Barrier

import pytest

from metaclass_registry.caches import (
    BoundedCache,
    IdentityBoundProcessCache,
    ProcessLocalBoundedCache,
    SynchronizedBoundedCache,
)


def _concurrent_singletons(cache_type: type[ProcessLocalBoundedCache], workers: int = 8):
    barrier = Barrier(workers)

    def obtain(_index: int) -> ProcessLocalBoundedCache:
        barrier.wait(timeout=5)
        return cache_type.process_cache()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return tuple(pool.map(obtain, range(workers)))


@pytest.mark.parametrize("cache_type", (BoundedCache, SynchronizedBoundedCache))
def test_bounded_caches_evict_least_recently_used(cache_type):
    cache = cache_type(max_entries=2)
    cache.store_value("oldest", 1)
    cache.store_value("middle", 2)
    assert cache.cached_value("oldest") == 1
    assert cache.store_value("newest", 3) == 3
    assert cache.cached_value("middle") is None
    assert (cache.cached_value("oldest"), cache.cached_value("newest")) == (1, 3)
    cache.clear()
    assert not cache.entries


@pytest.mark.parametrize("base", (ProcessLocalBoundedCache, IdentityBoundProcessCache))
def test_each_family_member_owns_one_singleton_and_joins_family_cleanup(base):
    @dataclass
    class ParentCache(base):
        max_entries: int = 2

    parent = ParentCache.process_cache()
    parent.store_value("parent", "parent-only")

    @dataclass(slots=True)
    class ChildCache(ParentCache):
        max_entries: int = 3

    children = _concurrent_singletons(ChildCache)
    child = children[0]
    assert all(cache is child for cache in children)
    assert (type(parent), type(child)) == (ParentCache, ChildCache)
    assert (parent.max_entries, child.max_entries) == (2, 3)
    assert child.cached_value("parent") is None

    for cache_type in (ParentCache, ChildCache):
        key = f"{cache_type.__module__}.{cache_type.__name__}"
        assert ProcessLocalBoundedCache.__registry__[key] is cache_type
        assert cache_type.process_cache_key == key

    child.store_value("child", "child-only")
    ChildCache.clear_process_cache()
    assert ChildCache.process_cache() is child
    assert child.cached_value("child") is None
    assert parent.cached_value("parent") == "parent-only"

    child.store_value("child", "child-only")
    ChildCache.clear_process_caches()
    assert parent.cached_value("parent") == "parent-only"
    assert child.cached_value("child") is None

    child.store_value("child", "child-only")
    ProcessLocalBoundedCache.clear_process_caches()
    assert not parent.entries and not child.entries


def test_synchronized_diamond_members_keep_separate_singletons_locks_and_lru():
    @dataclass
    class ParentDiamondCache(
        SynchronizedBoundedCache[str, str],
        ProcessLocalBoundedCache[str, str],
    ):
        max_entries: int = 2

    class LeftDiamondCache(ParentDiamondCache):
        pass

    class RightDiamondCache(ParentDiamondCache):
        pass

    class DiamondCache(LeftDiamondCache, RightDiamondCache):
        pass

    family = (ParentDiamondCache, LeftDiamondCache, RightDiamondCache, DiamondCache)
    for cache_type in family[:-1]:
        cache_type.process_cache().store_value(cache_type.__name__, "value")
    diamonds = _concurrent_singletons(DiamondCache)
    diamond = diamonds[0]
    assert all(cache is diamond for cache in diamonds)
    caches = tuple(cache_type.process_cache() for cache_type in family)
    assert tuple(type(cache) for cache in caches) == family
    assert len({id(cache._lock) for cache in caches}) == 4
    assert len({id(cache_type._process_cache_lock) for cache_type in family}) == 4
    assert not diamond.entries

    diamond.store_value("oldest", "first")
    diamond.store_value("middle", "second")
    assert diamond.cached_value("oldest") == "first"
    diamond.store_value("newest", "third")
    assert diamond.cached_value("middle") is None

    ProcessLocalBoundedCache.clear_process_caches()
    assert all(not cache.entries for cache in caches)


def test_process_cache_subclass_hook_cooperates_with_other_bases():
    observed = []

    class HookObserver:
        def __init_subclass__(cls, *, marker, **kwargs):
            super().__init_subclass__(**kwargs)
            observed.append((cls, marker))

    class CooperativeCache(ProcessLocalBoundedCache, HookObserver, marker="owner"):
        pass

    assert observed == [(CooperativeCache, "owner")]
    assert type(CooperativeCache.process_cache()) is CooperativeCache


def test_identity_bound_cache_rejects_a_reused_identity():
    class OwnerBoundCache(IdentityBoundProcessCache):
        pass

    cache = OwnerBoundCache.process_cache()
    owner = object()
    assert cache.put_bound(owner, "payload") == "payload"
    assert cache.get_bound(owner) == "payload"

    impostor = object()
    cache.entries[id(impostor)] = (owner, "stale")
    assert cache.get_bound(impostor) is None
    assert id(impostor) not in cache.entries

    ProcessLocalBoundedCache.clear_process_caches()
    assert cache.get_bound(owner) is None
