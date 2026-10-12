"""Exceptions for metaclass-registry."""


class RegistryError(Exception):
    """Base exception for registry-related errors."""

    pass


class DiscoveryError(RegistryError):
    """Exception raised when plugin discovery fails."""

    pass


class CacheError(RegistryError):
    """Exception raised when cache operations fail."""

    pass


class DuplicateRegistryKeyError(RegistryError):
    """Raised when a registry key that names one class is claimed by another."""

    pass
