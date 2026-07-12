class NapalmAutomationError(Exception):
    """Base exception for all napalm-101 errors."""
    pass


class InventoryError(NapalmAutomationError):
    """Raised when inventory loading or validation fails."""
    pass


class ConnectionError(NapalmAutomationError):
    """Raised when connection to a network device fails."""
    pass


class TaskExecutionError(NapalmAutomationError):
    """Raised when a task execution fails."""
    pass
