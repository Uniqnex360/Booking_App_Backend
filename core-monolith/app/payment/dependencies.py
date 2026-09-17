from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.booking.dependencies import get_booking_service
from app.movie.dependencies import get_movie_service
from app.movie.services import MovieService
from app.payment.repository import PaymentRepository
from app.payment.services import PaymentService


async def get_payment_service(
    session: AsyncSession = Depends(get_db),
    booking_service = Depends(get_booking_service),
    movie_service: MovieService = Depends(get_movie_service),
) -> PaymentService:
    payment_repo = PaymentRepository(session)
    return PaymentService(
        payment_repo=payment_repo,
        booking_service=booking_service,
        session=session,
        movie_service=movie_service,
    )
