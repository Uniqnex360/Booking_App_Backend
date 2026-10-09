# app/user/exceptions.py

from fastapi import HTTPException, status


class ProfileNotFoundHTTP(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found"
        )
class UserRepositoryHTTP(HTTPException):
    def __init__(self, detail: str = "A database error occurred in the user service"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )

class AddressNotFoundHTTP(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )


class UnauthorizedAddressHTTP(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this address"
        )