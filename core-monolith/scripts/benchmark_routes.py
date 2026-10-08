import asyncio
import time
import json
import uuid
from types import SimpleNamespace
from httpx import AsyncClient, ASGITransport
from sqlalchemy import event, text
from app.main import app
from app.core.database import engine
from app.auth.security import JWTTokenService

# Global query tracker
request_queries = []

@event.listens_for(engine.sync_engine, "before_cursor_execute")
def before_cursor(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.perf_counter()

@event.listens_for(engine.sync_engine, "after_cursor_execute")
def after_cursor(conn, cursor, statement, parameters, context, executemany):
    duration_ms = (time.perf_counter() - context._query_start_time) * 1000
    cleaned_sql = " ".join(statement.split())
    request_queries.append({
        "duration_ms": duration_ms,
        "statement": cleaned_sql,
        "parameters": parameters,
    })

admin_user = SimpleNamespace(id=uuid.UUID("3412cace-875a-482c-b575-14aed56ba525"), role="ADMIN")
admin_token = JWTTokenService().create_access_token(admin_user)

normal_user = SimpleNamespace(id=uuid.UUID("3bf12362-c21c-449a-b008-5077d579f1a8"), role="USER")
normal_token = JWTTokenService().create_access_token(normal_user)

TARGET_ENDPOINTS = [
    {"method": "GET", "url": "/v1/movies?city=Chennai", "headers": {}, "name": "list_movies(Chennai)"},
    {"method": "GET", "url": "/v1/movies?city=Kochi", "headers": {}, "name": "list_movies(Kochi)"},
    {"method": "GET", "url": "/v1/movies/d0db6b4f-1eef-442b-8509-1031d143109c?city=Chennai", "headers": {}, "name": "get_movie_details(Last Whistle)"},
    {"method": "GET", "url": "/v1/movies/544782a8-b33e-42fd-bc59-200cfcf901b8?city=Chennai", "headers": {}, "name": "get_movie_details(ID 5447)"},
    {"method": "GET", "url": "/v1/movies/544782a8-b33e-42fd-bc59-200cfcf901b8/reviews", "headers": {}, "name": "list_reviews(ID 5447)"},
    {"method": "GET", "url": "/v1/events?city=Kochi", "headers": {}, "name": "list_events(Kochi)"},
    {"method": "GET", "url": "/v1/events/venues?city=Kochi", "headers": {}, "name": "list_venues(Kochi)"},
    {"method": "GET", "url": "/v1/events/fb67aa38-eb7f-4cb0-97a7-b3d43db79926", "headers": {}, "name": "get_event_by_id"},
    {"method": "GET", "url": "/v1/showtimes/722b16eb-ad08-47e2-9123-e225b987954b/seat-map", "headers": {}, "name": "get_seat_map"},
    {"method": "GET", "url": "/v1/showtimes/722b16eb-ad08-47e2-9123-e225b987954b/availability", "headers": {}, "name": "get_showtime_availability"},
    {"method": "GET", "url": "/v1/showtimes/722b16eb-ad08-47e2-9123-e225b987954b/fnb-menu", "headers": {}, "name": "get_fnb_menu"},
    {"method": "GET", "url": "/v1/bookings", "headers": {"Authorization": f"Bearer {normal_token}"}, "name": "list_my_bookings"},
    {"method": "GET", "url": "/v1/users/me", "headers": {"Authorization": f"Bearer {normal_token}"}, "name": "get_my_profile"},
    {"method": "GET", "url": "/v1/admin/movies", "headers": {"Authorization": f"Bearer {admin_token}"}, "name": "admin_list_movies"},
    {"method": "GET", "url": "/v1/admin/events", "headers": {"Authorization": f"Bearer {admin_token}"}, "name": "admin_list_events"},
    {"method": "GET", "url": "/v1/admin/users", "headers": {"Authorization": f"Bearer {admin_token}"}, "name": "admin_list_users"},
    {"method": "GET", "url": "/v1/admin/stats", "headers": {"Authorization": f"Bearer {admin_token}"}, "name": "admin_get_stats"},
]

async def run_benchmark():
    transport = ASGITransport(app=app)
    results = []
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Warmup connection
        print("Warming up connection...")
        try:
            await client.get("/health")
        except Exception as e:
            print("Warmup failed:", e)

        for target in TARGET_ENDPOINTS:
            global request_queries
            request_queries = []
            
            t0 = time.perf_counter()
            try:
                response = await client.request(
                    method=target["method"],
                    url=target["url"],
                    headers=target["headers"]
                )
                t1 = time.perf_counter()
                total_latency_ms = (t1 - t0) * 1000
                status_code = response.status_code
                payload_bytes = len(response.content)
                
                queries_count = len(request_queries)
                db_time_ms = sum(q["duration_ms"] for q in request_queries)
                slowest_q = max(request_queries, key=lambda x: x["duration_ms"]) if request_queries else None
                
                result_entry = {
                    "name": target["name"],
                    "method": target["method"],
                    "url": target["url"],
                    "status_code": status_code,
                    "total_latency_ms": round(total_latency_ms, 2),
                    "db_queries_count": queries_count,
                    "db_time_ms": round(db_time_ms, 2),
                    "payload_bytes": payload_bytes,
                    "slowest_query_ms": round(slowest_q["duration_ms"], 2) if slowest_q else 0,
                    "slowest_query_sql": slowest_q["statement"][:200] if slowest_q else "",
                    "all_queries": [
                        {"ms": round(q["duration_ms"], 2), "sql": q["statement"]} for q in request_queries
                    ]
                }
                results.append(result_entry)
                print(f"[{status_code}] {target['name']:30} | Latency: {total_latency_ms:7.1f}ms | Queries: {queries_count:2} | DB Time: {db_time_ms:7.1f}ms | Size: {payload_bytes:6}B")
            except Exception as e:
                print(f"[ERR] {target['name']}: {e}")

    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved benchmark results to benchmark_results.json")

if __name__ == "__main__":
    asyncio.run(run_benchmark())

