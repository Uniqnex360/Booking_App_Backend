from fastapi import HTTPException, status
from app.shared.exceptions import EntityNotFoundError


class DuplicateEmailError(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists"
        )


class InvalidCredentialsError(HTTPException):
    def __init__(self, detail: str = "Invalid email or password"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

class InactiveAccountError(HTTPException):
    def __init__(self, detail: str = "Account is inactive"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
        
class UserNotFoundError(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="User not found or registration session expired."
        )


class InvalidTokenError(HTTPException):
    def __init__(self, detail: str = "Invalid or expired token"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class InactiveAccountError(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive or suspended"
        )
class RepositoryError(Exception):
    def __init__(self, detail: str):
        self.detail = detail

# class ForbiddenError(HTTPException):
#     def __init__(self, detail: str = "Insufficient permissions"):
#         super().__init__(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail=detail
#         )
class ProfileNotFoundError(EntityNotFoundError):
    def __init__(self):
        super().__init__("User profile not found")

class TokenReuseError(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Security violation detected. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )