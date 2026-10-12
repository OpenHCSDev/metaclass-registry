"""Test support: stand-in members of a registered family.

A registry key names one class, so a test cannot define a second class under
the key of a registered one, and a class a test does register stays registered
for the rest of the process. ``restored_registry`` frees the keys a test's
stand-ins need for the duration of a block and then puts the registry back
exactly as it was.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from .core import RegistryKey


@contextmanager
def restored_registry(
    family: type,
    *,
    released: tuple[RegistryKey, ...] = (),
) -> Iterator[None]:
    """Restore ``family.__registry__`` on exit; free ``released`` keys inside.

    Classes registered inside the block are not registered after it, and the
    classes that held the released keys hold them again. Only the primary
    registry is touched.
    """
    from .strategies import _invalidate_family_projections

    registry: dict[RegistryKey, object] = getattr(family, "__registry__")
    # Finish lazy discovery first: a discovery that ran inside the block would
    # find the released keys occupied by stand-ins.
    len(registry)
    registered = dict(dict.items(registry))
    for key in released:
        dict.pop(registry, key, None)
    _invalidate_family_projections()
    try:
        yield
    finally:
        dict.clear(registry)
        dict.update(registry, registered)
        _invalidate_family_projections()
