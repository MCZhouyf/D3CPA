class DC3PAError(Exception):
    """Base exception for the staged DC3PA implementation."""


class ContractValidationError(DC3PAError, ValueError):
    """Raised when a plan/state payload violates a public contract."""


class MemoryInvariantError(DC3PAError, RuntimeError):
    """Raised when a memory write would violate research invariants."""


class PatchApplicationError(DC3PAError, RuntimeError):
    """Raised when a guarded legacy patch cannot be applied safely."""
