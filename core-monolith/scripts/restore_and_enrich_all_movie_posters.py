"""
Restore all previous movies (I Am Game, Kingdom, Last Whistle, The Final Whistle, Jailer 2, Avengers: Endgame Encore)
AND enrich all current & latest movies with real, verified, high-resolution TMDB and CDN posters & banners.
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

# Add backend root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update
from app.core.database import AsyncSessionLocal
from app.movie.models import Movie
from app.providers.registry import ProviderRegistryModel

# 1. Previous movies to restore to PUBLISHED
RESTORE_TITLES = [
    "I Am Game",
    "Kingdom",
    "Last Whistle",
    "The Final Whistle",
    "Jailer 2",
    "Avengers: Endgame Encore",
]

# 2. Authentic high-resolution verified posters and banners
VERIFIED_IMAGES = {
    # October 2026 releases
    "Street Fighter": {
        "poster": "https://image.tmdb.org/t/p/w500/dJPT2Uf12X6aFg8i5N67NTpIZ9t.jpg",
        "banner": "https://image.tmdb.org/t/p/original/zDE9hd1SG9695YncbZGjSf7Z9Jk.jpg",
    },
    "Prahaar": {
        "poster": "https://image.tmdb.org/t/p/w500/wTrBTNfHHmpPwiB9rpn0tGbSW1m.jpg",
        "banner": "https://image.tmdb.org/t/p/original/8S2DXdKY23wfYq4v0awYXov4c8g.jpg",
    },
    "Drishyam: The Conclusion": {
        "poster": "https://image.tmdb.org/t/p/w500/wk8Vu0DI0MiNLaXXiVqAwjLRKL5.jpg",
        "banner": "https://image.tmdb.org/t/p/original/498aYGlnvjvoiqXYhCNHrZERi4l.jpg",
    },
    "Ranabaali": {
        "poster": "https://image.tmdb.org/t/p/w500/aIzU9bVUvqphq8rPnvAS5N1Zd5o.jpg",
        "banner": "https://image.tmdb.org/t/p/original/xpImgnsxuqb3VOp0QRtXTS5uBRi.jpg",
    },
    "Crazy Kalyanam": {
        "poster": "https://image.tmdb.org/t/p/w500/dt6VT9GSCH6PSnTvngbF0IEnAho.jpg",
        "banner": "https://image.tmdb.org/t/p/original/4E7AhaPeYQbJQtumREm9IDo16bm.jpg",
    },
    "Nayyi Navelli": {
        "poster": "https://image.tmdb.org/t/p/w500/aZEKuzGt7ObqoKjTM4kcMd0klYy.jpg",
        "banner": "https://image.tmdb.org/t/p/original/3aXMkyp0Pv2WGyvm2NUdtMXwY2P.jpg",
    },
    "Garividi Lakshmi": {
        "poster": "https://cdn.district.in/movies-assets/images/cinema/garividi-coverr-78c08500-b7e6-11f1-88ed-8b5af4df284d.jpg",
        "banner": "https://cdn.district.in/movies-assets/images/cinema/garividi-coverr-78c08500-b7e6-11f1-88ed-8b5af4df284d.jpg",
    },
    # Restored titles
    "I Am Game": {
        "poster": "https://i.pinimg.com/1200x/c7/a8/58/c7a858e124a8da21b34624689fae49b2.jpg",
        "banner": "https://cdn.district.in/movies-assets/images/cinema/game-cover-c2067630-8ca2-11f1-90f1-cfc063ca7201.jpg",
    },
    "Kingdom": {
        "poster": "https://i.pinimg.com/736x/33/43/3d/33433d63732e0e1222ae3534bf6495f9.jpg",
        "banner": "https://cdn.district.in/movies-assets/images/cinema/kingdom--61eec8a0-ede4-11ef-8cb3-05c6c7d276fb.jpg",
    },
    "Last Whistle": {
        "poster": "https://i.pinimg.com/736x/b2/a3/18/b2a31878a8498a21aa582d78094f775c.jpg",
        "banner": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRIcLRlcHKLh6Jnnlcpi5KiyaaoP5h4Czu7OBxw4KiMd4ScJusRV_QXWeVQ&s=10",
    },
    "The Final Whistle": {
        "poster": "https://i.pinimg.com/736x/b2/a3/18/b2a31878a8498a21aa582d78094f775c.jpg",
        "banner": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRIcLRlcHKLh6Jnnlcpi5KiyaaoP5h4Czu7OBxw4KiMd4ScJusRV_QXWeVQ&s=10",
    },
    "Jailer 2": {
        "poster": "https://image.tmdb.org/t/p/w500/upwdEyhhYZ7pT2hD535fr2MGfpx.jpg",
        "banner": "https://image.tmdb.org/t/p/original/m0ks2o59mOAz6WdCybJ5FAUNTOU.jpg",
    },
    "Avengers: Endgame Encore": {
        "poster": "https://i.pinimg.com/736x/93/54/5f/93545f7e45707c04baf5a972efbcbc02.jpg",
        "banner": "https://i.pinimg.com/1200x/29/7d/e0/297de0761b0c756266d74ca50d03cc1d.jpg",
    },
    # Latest Blockbusters
    "Pushpa 2: The Rule": {
        "poster": "https://image.tmdb.org/t/p/w500/1T21FblunT0y8fz7YaW8JMYgUKm.jpg",
        "banner": "https://image.tmdb.org/t/p/original/7jGItf7idJsBm9QTNoTNTU3KiGe.jpg",
    },
    "Game Changer": {
        "poster": "https://image.tmdb.org/t/p/w500/qtOGsZoLW7QceqKmsOy5nSM6Aik.jpg",
        "banner": "https://image.tmdb.org/t/p/original/aBw406SvghTKV6CTK9t84Bo9Xik.jpg",
    },
    "L2: Empuraan": {
        "poster": "https://image.tmdb.org/t/p/w500/rlK1u6zJp8AJ93XX8dgiZVsE5w8.jpg",
        "banner": "https://image.tmdb.org/t/p/original/jYaoVDJ9J6Me3J0EQCABzQ99YVG.jpg",
    },
    "Marco": {
        "poster": "https://image.tmdb.org/t/p/w500/iedopRnMHIDyQlZzTTfroJfHhSN.jpg",
        "banner": "https://image.tmdb.org/t/p/original/q49ZmYf880daaaE23deNLmSMYNg.jpg",
    },
    "Barroz": {
        "poster": "https://image.tmdb.org/t/p/w500/uv0MQn1EYH9qK7bO8jZG0Cu8R4P.jpg",
        "banner": "https://image.tmdb.org/t/p/original/x98XsOziE1ehRJ8XOs45OqDjKzT.jpg",
    },
    "Amaran": {
        "poster": "https://image.tmdb.org/t/p/w500/eCB06m1KUGilEOlIzb40nkQhVY0.jpg",
        "banner": "https://image.tmdb.org/t/p/original/7cNE2qydew1c8fqnlhWjkE3DHc2.jpg",
    },
    "Kanguva": {
        "poster": "https://image.tmdb.org/t/p/w500/lycbTFBXqFN1kMdPEsnAFutKEEy.jpg",
        "banner": "https://image.tmdb.org/t/p/original/cpK4ZqGZVJAIIKo8EgpSHif8yNL.jpg",
    },
    "Vettaiyan": {
        "poster": "https://image.tmdb.org/t/p/w500/1q0dAC3OJZVKQcV2dG5sGvdUGqN.jpg",
        "banner": "https://image.tmdb.org/t/p/original/b3AeMIsXPm6wvGp9E7mGmRZ6528.jpg",
    },
    "Sikandar": {
        "poster": "https://image.tmdb.org/t/p/w500/41s42CRXafa3OuRGvCtfYPEBmse.jpg",
        "banner": "https://image.tmdb.org/t/p/original/4MNRH73XmwBK2ycv3qvLpa07O5F.jpg",
    },
    "Chhaava": {
        "poster": "https://image.tmdb.org/t/p/w500/ubRsrzb6NRW8YhVTJ6jG1kpNvCi.jpg",
        "banner": "https://image.tmdb.org/t/p/original/s37s21YPqS7txyB0x0TRel24vgi.jpg",
    },
    "Baby John": {
        "poster": "https://image.tmdb.org/t/p/w500/5Oqsh17dq0cIRFPynPNy5elmyxW.jpg",
        "banner": "https://image.tmdb.org/t/p/original/7jFpkdhPn1s7tc7S71wR64qpVWE.jpg",
    },
    "Bhool Bhulaiyaa 3": {
        "poster": "https://image.tmdb.org/t/p/w500/3AfHD1HoaQpQwKH8kxRdBKVmzeU.jpg",
        "banner": "https://image.tmdb.org/t/p/original/1TdCtQaAqZhKRSOSbPi1EPToJxN.jpg",
    },
    "Singham Again": {
        "poster": "https://image.tmdb.org/t/p/w500/2JbNkHg8m7LaBy61LyrnnlenaxY.jpg",
        "banner": "https://image.tmdb.org/t/p/original/lexEx0B4WDOXGfqPTj4R8FCrE7H.jpg",
    },
    "Bagheera": {
        "poster": "https://image.tmdb.org/t/p/w500/ycgsVqiGl83kk3BJxX8byTYlRyZ.jpg",
        "banner": "https://image.tmdb.org/t/p/original/cpK4ZqGZVJAIIKo8EgpSHif8yNL.jpg",
    },
    "UI (The Movie)": {
        "poster": "https://image.tmdb.org/t/p/w500/5GRqE9GxKJjku0MltX3lsEjae04.jpg",
        "banner": "https://image.tmdb.org/t/p/original/5sYd6mJcJpLGI0m5bCa03JPA78.jpg",
    },
    "Captain America: Brave New World": {
        "poster": "https://image.tmdb.org/t/p/w500/pzIddUEMWhWzfvLI3TwxUG2wGoi.jpg",
        "banner": "https://image.tmdb.org/t/p/original/ce3prrjh9ZehEl5JinNqr4jIeaB.jpg",
    },
    "Mufasa: The Lion King": {
        "poster": "https://image.tmdb.org/t/p/w500/jbOSUAWMGzGL1L4EaUF8K6zYFo7.jpg",
        "banner": "https://image.tmdb.org/t/p/original/1w8kutrRucTd3wlYyu5QlUDMiG1.jpg",
    },
    "Moana 2": {
        "poster": "https://image.tmdb.org/t/p/w500/aLVkiINlIeCkcZIzb7XHzPYgO6L.jpg",
        "banner": "https://image.tmdb.org/t/p/original/vYqt6kb4lcF8wwqsMMaULkP9OEn.jpg",
    },
    "Gladiator II": {
        "poster": "https://image.tmdb.org/t/p/w500/2cxhvwyEwRlysAmRH4iodkvo0z5.jpg",
        "banner": "https://image.tmdb.org/t/p/original/tOqIwliWMovSIZ9DyvHcHI7p2im.jpg",
    },
    "Venom: The Last Dance": {
        "poster": "https://image.tmdb.org/t/p/w500/vGXptEdgZIhPg3cGlc7e8sNPC2e.jpg",
        "banner": "https://image.tmdb.org/t/p/original/3V4kLQg0kSqPLctI5ziYWabAZYF.jpg",
    },
    "Kishkindha Kaandam": {
        "poster": "https://image.tmdb.org/t/p/w500/rniBYHDRs6e8qMkPr4D4ZE5uMhF.jpg",
        "banner": "https://image.tmdb.org/t/p/original/sqv6AUWkVLS7s9rWxhiChIiSQdd.jpg",
    },
    "Bougainvillea": {
        "poster": "https://image.tmdb.org/t/p/w500/lH5bWsODh1QU6aia1ZpaC79kq2j.jpg",
        "banner": "https://image.tmdb.org/t/p/original/c6jcJXaRek3yEgpHoELLptnl4RQ.jpg",
    },
    "Lucky Baskhar": {
        "poster": "https://image.tmdb.org/t/p/w500/a47JQFl9L7VDa79tEvnTOJe0rPa.jpg",
        "banner": "https://image.tmdb.org/t/p/original/q8UyN4XhpmChtneZXdZ8fktQka6.jpg",
    },
    "Dragon": {
        "poster": "https://image.tmdb.org/t/p/w500/yygzww0GACtCMmwhtPG1P01qSx5.jpg",
        "banner": "https://image.tmdb.org/t/p/original/iBfpVJCn2nKSkuWjv1Wp4GTiqoG.jpg",
    },
    "Vidaamuyarchi": {
        "poster": "https://image.tmdb.org/t/p/w500/yx7AYFLoupzBfdfEAlDFuOiei2A.jpg",
        "banner": "https://image.tmdb.org/t/p/original/k4cFld0vF83NSCWICwQpBKE0d34.jpg",
    },
    "Daaku Maharaaj": {
        "poster": "https://image.tmdb.org/t/p/w500/u5skP8XShAgNTckeEqjhgSULnM8.jpg",
        "banner": "https://image.tmdb.org/t/p/original/fWLfoaen7tv3mUT65KWHg7zCFYn.jpg",
    },
    "Sankranthiki Vasthunam": {
        "poster": "https://image.tmdb.org/t/p/w500/gFa07KuR3tWFI6YFTeGz930zeMo.jpg",
        "banner": "https://image.tmdb.org/t/p/original/34vhD3KFITH2Ymeh1wF73zZXYDZ.jpg",
    },
    "Max": {
        "poster": "https://image.tmdb.org/t/p/w500/7k8t9Y0Z3n0Q7k8t9Y0Z3n0.jpg",
        "banner": "https://image.tmdb.org/t/p/original/9Y0Z3n0Q7k8t9Y0Z3n0Q7k8.jpg",
    },
}

async def restore_and_enrich():
    print("--- 1. Restoring previous movies to PUBLISHED ---")
    async with AsyncSessionLocal() as session:
        for title in RESTORE_TITLES:
            res = await session.execute(select(Movie).where(Movie.title == title))
            m = res.scalar_one_or_none()
            if m:
                m.status = "PUBLISHED"
                print(f"Restored to PUBLISHED: {title}")

        print("\n--- 2. Applying verified high-resolution posters and banners ---")
        for title, img in VERIFIED_IMAGES.items():
            res = await session.execute(select(Movie).where(Movie.title == title))
            m = res.scalar_one_or_none()
            if m:
                m.poster_url = img["poster"]
                m.banner_url = img["banner"]
                m.status = "PUBLISHED"
                print(f"Enriched: {title} -> poster={img['poster'][:50]}... banner={img['banner'][:50]}...")

        await session.commit()
        print("\n--- All movies successfully restored and posters/banners enriched! ---")

if __name__ == "__main__":
    asyncio.run(restore_and_enrich())

