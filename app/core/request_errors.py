from fastapi import HTTPException


class RequestNotStartedError(HTTPException):
    """Admission failed before side effects; retrying the same action is safe."""
