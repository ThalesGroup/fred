from fastapi import HTTPException


class UnavailableError(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=503, detail=f"Resource unavailable: {message}")


class InvalidCacheError(FileNotFoundError):
    ...
