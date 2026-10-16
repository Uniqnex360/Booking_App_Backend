from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession


from app.auth.dependencies import get_current_user
from app.auth.interfaces import User as AuthUserDomain, UserRole
from app.shared.exceptions import ForbiddenError


from app.core.database import get_db
from app.event.repository import SQLAlchemyEventRepository
from app.admin.services import AdminService


ALL_ADMIN_ROLES = {
    UserRole.ADMIN,
    UserRole.SUPER_ADMIN,
    UserRole.OPERATIONS_ADMIN,
    UserRole.FINANCE_ADMIN,
    UserRole.SUPPORT_ADMIN,
}

FINANCE_ROLES = {
    UserRole.ADMIN,
    UserRole.SUPER_ADMIN,
    UserRole.FINANCE_ADMIN,
}

OPS_ROLES = {
    UserRole.ADMIN,
    UserRole.SUPER_ADMIN,
    UserRole.OPERATIONS_ADMIN,
}

SUPER_ROLES = {
    UserRole.ADMIN,
    UserRole.SUPER_ADMIN,
}


async def require_admin(
    current_user: AuthUserDomain = Depends(get_current_user)
) -> AuthUserDomain:
    if current_user.role not in ALL_ADMIN_ROLES:
        raise ForbiddenError("Admin access required")
    return current_user


async def require_finance_admin(
    current_user: AuthUserDomain = Depends(get_current_user)
) -> AuthUserDomain:
    if current_user.role not in FINANCE_ROLES:
        raise ForbiddenError("Finance admin access required")
    return current_user


async def require_ops_admin(
    current_user: AuthUserDomain = Depends(get_current_user)
) -> AuthUserDomain:
    if current_user.role not in OPS_ROLES:
        raise ForbiddenError("Operations admin access required")
    return current_user


async def require_super_admin(
    current_user: AuthUserDomain = Depends(get_current_user)
) -> AuthUserDomain:
    if current_user.role not in SUPER_ROLES:
        raise ForbiddenError("Super admin access required")
    return current_user


def get_event_repo(db: AsyncSession = Depends(get_db)):
    return SQLAlchemyEventRepository(db)

def get_admin_service(repo = Depends(get_event_repo)) -> AdminService:
    return AdminService(repo)