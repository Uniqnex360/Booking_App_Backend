    
class DomainError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class EntityNotFoundError(DomainError):
    pass
class ForbiddenError(DomainError):
    pass

class UnauthorizedError(DomainError):
    pass


class RepositoryError(DomainError):
    pass


class DuplicateEntityError(DomainError):
    pass