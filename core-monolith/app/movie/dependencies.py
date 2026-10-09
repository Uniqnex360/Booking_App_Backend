
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.movie.repository import MovieRepository
from app.movie.services import MovieService


def get_movie_repo(db: AsyncSession = Depends(get_db)) -> MovieRepository:
    return MovieRepository(db)


def get_movie_service(
    repo: MovieRepository = Depends(get_movie_repo),
) -> MovieService:
    return MovieService(movie_repo=repo)
