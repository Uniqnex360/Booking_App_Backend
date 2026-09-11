from fastapi import HTTPException, status

class BookingNotFoundHTTPError(HTTPException):
    def __init__(self, detail: str = "Booking not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        self.code = "BOOKING_NOT_FOUND"

class SeatUnavailableRemoteHTTPError(HTTPException):
    def __init__(self, detail: str = "Seats unavailable remotely"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)
        self.code = "SEAT_UNAVAILABLE_REMOTE"

class HoldExpiredHTTPError(HTTPException):
    def __init__(self, detail: str = "Hold expired remotely"):
        super().__init__(status_code=status.HTTP_410_GONE, detail=detail)
        self.code = "HOLD_EXPIRED"

class HoldAlreadyCommittedHTTPError(HTTPException):
    def __init__(self, detail: str = "Hold already committed"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)
        self.code = "HOLD_ALREADY_COMMITTED"

class ProviderUnavailableHTTPError(HTTPException):
    def __init__(self, detail: str = "Provider unavailable"):
        super().__init__(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
        self.code = "PROVIDER_UNAVAILABLE"

class SoldOutHTTPError(HTTPException):
    def __init__(self, detail: str = "Ticket tier is sold out"):
        super().__init__(status_code=status.HTTP_410_GONE, detail=detail)
        self.code = "SOLD_OUT"

class TierInactiveHTTPError(HTTPException):
    def __init__(self, detail: str = "This ticket tier is currently inactive"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
        self.code = "TIER_INACTIVE"

class EventNotPublishedHTTPError(HTTPException):
    def __init__(self, detail: str = "Event is not in a bookable state (must be PUBLISHED)"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
        self.code = "EVENT_NOT_PUBLISHED"

class QuantityExceedsLimitHTTPError(HTTPException):
    def __init__(self, detail: str = "Requested quantity exceeds limit"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
        self.code = "QUANTITY_EXCEEDS_LIMIT"

class IdempotencyKeyReusedHTTPError(HTTPException):
    def __init__(self, detail: str = "Idempotency key already reused with different parameters"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
        self.code = "IDEMPOTENCY_KEY_REUSED"

class LayoutInvalidHTTPError(HTTPException):
    def __init__(self, detail: str = "Invalid layout text grid syntax"):
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
        self.code = "LAYOUT_INVALID"

class SourceUnavailableHTTPError(HTTPException):
    def __init__(self, detail: str = "Source upstream currently unavailable"):
        super().__init__(status_code=status.HTTP_200_OK, detail=detail)
        self.code = "SOURCE_UNAVAILABLE"
