class StorageError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
