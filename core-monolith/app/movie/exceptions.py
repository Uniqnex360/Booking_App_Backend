
from fastapi import HTTPException, status


class MovieNotFoundHTTPError(HTTPException):
    def __init__(self, detail: str = "Movie not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ShowtimeNotFoundHTTPError(HTTPException):
    def __init__(self, detail: str = "Showtime not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ScreenNotFoundHTTPError(HTTPException):
    def __init__(self, detail: str = "Screen not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class VenueNotFoundHTTPError(HTTPException):
    def __init__(self, detail: str = "Venue not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class SeatNotFoundHTTPError(HTTPException):
    def __init__(self, detail: str = "Seat not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class PartnerOwnershipHTTPError(HTTPException):
    def __init__(self, detail: str = "Not authorized to modify this resource"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class UnapprovedPartnerHTTPError(HTTPException):
    def __init__(self, detail: str = "Partner is not approved"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class MovieNotPublishedHTTPError(HTTPException):
    def __init__(self, detail: str = "Cannot create showtime for unpublished movie"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class ScreenLayoutLockedHTTPError(HTTPException):
    def __init__(self, detail: str = "Cannot modify screen layout with active bookings"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class SeatConflictHTTPError(HTTPException):
    def __init__(self, detail: str = "Seat is already booked and cannot be blocked"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class InvalidLayoutGridHTTPError(HTTPException):
    def __init__(self, detail: str = "Invalid text-grid layout syntax"):
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)