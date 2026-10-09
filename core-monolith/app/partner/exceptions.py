from fastapi import HTTPException, status

class PartnerNotFoundHTTP(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Partner profile not found"
        )

class DuplicatePartnerHTTP(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT, 
            detail=detail
        )
class PartnerRepositoryHTTP(HTTPException):
    def __init__(self, detail: str = "A database error occurred in the partner service"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )
class InvalidStatusTransitionHTTP(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=detail
        )

class PartnerNotApprovedHTTP(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Your partner account is not approved yet."
        )