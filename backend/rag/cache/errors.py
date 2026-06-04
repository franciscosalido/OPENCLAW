"""Errors raised by the HybridRAG semantic cache layer."""


class CacheError(RuntimeError):
    """Base cache error."""


class CacheDisabled(CacheError):
    """Raised when a write is attempted while cache is disabled."""


class CacheCollectionMismatchError(CacheError):
    """Raised when an existing cache collection does not match settings."""


class CachePayloadError(CacheError):
    """Raised when a Qdrant payload cannot be safely parsed."""


class CacheVectorDimensionError(CacheError):
    """Raised when a query vector does not match configured dimensions."""


class CacheSafetyError(CacheError):
    """Raised when sensitive fields are detected in cache metadata."""
