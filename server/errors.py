"""Domain exceptions raised by the server state and command layers."""


class NicknameInUseError(ValueError):
    """Raised when a client tries to claim an occupied IRC nickname."""
