from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession


from app.auth.dependencies import get_current_user
from app.auth.interfaces import User as AuthUserDomain, UserRole
from app.shared.exceptions import ForbiddenError


from app.core.database import get_db
from app.event.repository import SQLAlchemyEventRepository
from app.admin.services import AdminService


async def require_admin(
    current_user: AuthUserDomain = Depends(get_current_user)
) -> AuthUserDomain:
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenError("Admin access required")
    return current_user


def get_event_repo(db: AsyncSession = Depends(get_db)):
    return SQLAlchemyEventRepository(db)

def get_admin_service(repo = Depends(get_event_repo)) -> AdminService:
    return AdminService(repo)