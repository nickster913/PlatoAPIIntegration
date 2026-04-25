class PlatoAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PlatoAuthError(PlatoAPIError):
    """Raised on 401/403 responses."""


class PlatoNotFoundError(PlatoAPIError):
    """Raised on 404 responses."""
