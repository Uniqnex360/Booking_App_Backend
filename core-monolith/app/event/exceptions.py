from fastapi import HTTPException, status

class EventNotFoundError(HTTPException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

class TicketCategoryNotFoundError(HTTPException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket category not found")

class EventNotOwnedError(HTTPException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this event")

class EventLockedError(HTTPException):
    def __init__(self, message="Event is locked and cannot be edited"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=message)

class EventNotPublishableError(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=message)