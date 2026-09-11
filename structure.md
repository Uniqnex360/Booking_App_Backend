# Backend Structure — Hybrid Architecture
### Core Monolith + Independent Microservices

---

## Complete Project Structure (High-Level View)

```
booking-platform-backend/
|
|-- core-monolith/              <-- Main FastAPI app (Auth, User, Restaurant,
|                                    Movie, Event, Booking, Partner, Admin)
|
|-- services/                   <-- Independent Microservices
|   |-- payment-service/
|   |-- inventory-service/
|   |-- notification-service/
|   |-- search-service/
|   |-- media-service/
|
|-- infrastructure/             <-- Shared infra configs
|   |-- nginx/
|   |-- docker-compose.yml
|
|-- shared-lib/                 <-- Optional shared Python package
|
|-- .env.example
|-- README.md
```

---

## 1. Core Monolith — Full Structure

```
core-monolith/
|
|-- app/
|   |
|   |-- auth/
|   |   |-- __init__.py
|   |   |-- models.py           (User, RefreshToken DB models)
|   |   |-- schemas.py          (Pydantic request/response)
|   |   |-- routes.py           (API endpoints)
|   |   |-- services.py         (business logic)
|   |   |-- security.py         (password hash, JWT)
|   |   |-- dependencies.py     (get_current_user, role checks)
|   |
|   |-- user/
|   |   |-- __init__.py
|   |   |-- models.py           (UserProfile, Address)
|   |   |-- schemas.py
|   |   |-- routes.py
|   |   |-- services.py
|   |
|   |-- restaurant/
|   |   |-- __init__.py
|   |   |-- models.py           (Restaurant, Menu, Table)
|   |   |-- schemas.py
|   |   |-- routes.py
|   |   |-- services.py
|   |
|   |-- movie/
|   |   |-- __init__.py
|   |   |-- models.py           (Movie, Cinema, Showtime)
|   |   |-- schemas.py
|   |   |-- routes.py
|   |   |-- services.py
|   |
|   |-- event/
|   |   |-- __init__.py
|   |   |-- models.py           (Event, TicketCategory)
|   |   |-- schemas.py
|   |   |-- routes.py
|   |   |-- services.py
|   |
|   |-- booking/
|   |   |-- __init__.py
|   |   |-- models.py           (Booking, BookingItem)
|   |   |-- schemas.py
|   |   |-- routes.py
|   |   |-- services.py         (calls Inventory + Payment microservices)
|   |   |-- clients/
|   |       |-- inventory_client.py   (HTTP calls to Inventory Service)
|   |       |-- payment_client.py     (HTTP calls to Payment Service)
|   |
|   |-- review/
|   |   |-- __init__.py
|   |   |-- models.py
|   |   |-- schemas.py
|   |   |-- routes.py
|   |   |-- services.py
|   |
|   |-- partner/
|   |   |-- __init__.py
|   |   |-- models.py           (Partner)
|   |   |-- schemas.py
|   |   |-- routes.py
|   |   |-- services.py
|   |
|   |-- admin/
|   |   |-- __init__.py
|   |   |-- schemas.py
|   |   |-- routes.py
|   |   |-- services.py
|   |
|   |-- shared/
|   |   |-- __init__.py
|   |   |-- database.py         (SQLAlchemy engine + session)
|   |   |-- config.py           (env variables, settings)
|   |   |-- exceptions.py       (custom exception classes)
|   |   |-- response.py         (standard success/error response format)
|   |   |-- pagination.py       (common pagination helper)
|   |   |-- rabbitmq.py         (publish events to RabbitMQ)
|   |   |-- middlewares.py      (logging, request-id, CORS)
|   |
|   |-- main.py                 (FastAPI app entrypoint, includes all routers)
|
|-- alembic/                    (database migrations)
|   |-- versions/
|   |-- env.py
|
|-- tests/
|   |-- test_auth.py
|   |-- test_booking.py
|   |-- ...
|
|-- requirements.txt
|-- Dockerfile
|-- .env
|-- alembic.ini
```

---

## 2. Payment Service — Full Structure (Independent Microservice)

```
services/payment-service/
|
|-- app/
|   |-- models.py               (Payment, Refund, SplitPayment)
|   |-- schemas.py
|   |-- routes.py                (POST /initiate, /verify, /refund, /split)
|   |-- services.py
|   |-- gateway/
|   |   |-- razorpay_client.py
|   |   |-- stripe_client.py
|   |-- database.py              (OWN database connection - payment_db)
|   |-- config.py
|   |-- rabbitmq.py               (publishes "payment.success" events)
|
|-- alembic/
|   |-- versions/
|
|-- main.py
|-- requirements.txt
|-- Dockerfile
|-- .env
```

---

## 3. Inventory Service — Full Structure (Independent Microservice)

```
services/inventory-service/
|
|-- app/
|   |-- models.py                (SeatLock, TableLock)
|   |-- schemas.py
|   |-- routes.py                 (POST /lock, /release, GET /status)
|   |-- services.py
|   |-- redis_client.py            (Redis lock logic - core of this service)
|   |-- database.py                 (OWN database - inventory_db, for audit trail)
|   |-- config.py
|
|-- main.py
|-- requirements.txt
|-- Dockerfile
|-- .env
```

---

## 4. Notification Service — Full Structure (Independent Microservice)

```
services/notification-service/
|
|-- app/
|   |-- models.py                  (NotificationLog)
|   |-- schemas.py
|   |-- routes.py                   (POST /send, GET /me)
|   |-- services.py
|   |-- channels/
|   |   |-- sms_client.py            (Twilio)
|   |   |-- email_client.py           (SendGrid)
|   |   |-- push_client.py             (Firebase)
|   |-- consumers/
|   |   |-- booking_confirmed_consumer.py   (listens to RabbitMQ)
|   |   |-- payment_success_consumer.py
|   |-- celery_app.py                 (Celery configuration)
|   |-- tasks.py                       (Celery background tasks)
|   |-- database.py                     (OWN database - notification_db)
|   |-- config.py
|
|-- main.py                             (FastAPI app, for manual trigger APIs)
|-- celery_worker.py                     (entrypoint to run Celery worker)
|-- requirements.txt
|-- Dockerfile
|-- .env
```

---

## 5. Search Service — Full Structure (Independent Microservice)

```
services/search-service/
|
|-- app/
|   |-- schemas.py
|   |-- routes.py                  (GET /search, /suggestions)
|   |-- services.py
|   |-- elasticsearch_client.py     (connection + query builder)
|   |-- indexers/
|   |   |-- movie_indexer.py         (syncs Movie data into ES)
|   |   |-- event_indexer.py
|   |   |-- restaurant_indexer.py
|   |-- consumers/
|   |   |-- content_updated_consumer.py   (listens for content changes)
|   |-- config.py
|
|-- main.py
|-- requirements.txt
|-- Dockerfile
|-- .env
```

---

## 6. Media Service — Full Structure (Independent Microservice)

```
services/media-service/
|
|-- app/
|   |-- schemas.py
|   |-- routes.py                 (POST /upload)
|   |-- services.py
|   |-- s3_client.py                (AWS S3 upload logic)
|   |-- config.py
|
|-- main.py
|-- requirements.txt
|-- Dockerfile
|-- .env
```

---

## 7. Infrastructure Folder

```
infrastructure/
|
|-- nginx/
|   |-- nginx.conf               (API Gateway routing rules)
|
|-- docker-compose.yml           (Orchestrates everything together)
|
|-- postgres/
|   |-- init-multiple-dbs.sh     (creates payment_db, inventory_db, etc.
|                                  on container startup)
|
|-- rabbitmq/
|   |-- definitions.json          (pre-configured queues/exchanges)
```

---

## 8. Shared Library (Optional — For Common Code)

If you want to avoid repeating code like the standard response format or JWT decoding across services:

```
shared-lib/
|
|-- booking_platform_common/
|   |-- __init__.py
|   |-- response.py              (standard API response format)
|   |-- jwt_utils.py               (decode/verify JWT - used by all services)
|   |-- exceptions.py
|   |-- logging_config.py
|
|-- setup.py                       (makes it an installable Python package)
```

Each service can then install this as a dependency:
```
pip install -e ../../shared-lib
```

---

## Docker Compose — Structure Overview

```
docker-compose.yml defines these services:

infrastructure:
  - postgres          (shared instance, multiple databases inside)
  - redis
  - rabbitmq
  - elasticsearch
  - nginx              (API Gateway)

core-monolith:
  - core-api           (the main FastAPI app)

microservices:
  - payment-service
  - inventory-service
  - notification-service
  - notification-celery-worker
  - search-service
  - media-service
```

---

## How Each Piece Maps to a Port (Internal Network)

| Service | Internal Port | Exposed via Gateway Path |
|---|---|---|
| Core Monolith | 8000 | `/v1/auth/*`, `/v1/users/*`, `/v1/restaurants/*`, `/v1/movies/*`, `/v1/events/*`, `/v1/bookings/*`, `/v1/partner/*`, `/v1/admin/*`, `/v1/reviews/*` |
| Payment Service | 8001 | `/v1/payments/*` |
| Inventory Service | 8002 | `/v1/inventory/*` |
| Notification Service | 8003 | `/v1/notifications/*` |
| Search Service | 8004 | `/v1/search/*` |
| Media Service | 8005 | `/v1/media/*` |
| Nginx (Gateway) | 80 / 443 | Entry point for everything |

---

## Database Layout

```
PostgreSQL Server (one instance, multiple databases)
|
|-- core_db              <-- Used by Core Monolith
|   |-- users
|   |-- addresses
|   |-- restaurants
|   |-- menus
|   |-- movies
|   |-- events
|   |-- bookings
|   |-- partners
|   |-- reviews
|
|-- payment_db           <-- ONLY Payment Service
|-- inventory_db         <-- ONLY Inventory Service (audit log)
|-- notification_db      <-- ONLY Notification Service

Redis (one instance, different key prefixes or DB indexes)
|-- inventory locks       (used by Inventory Service)
|-- core sessions/cache   (used by Core Monolith)

Elasticsearch
|-- movies_index          (used by Search Service)
|-- events_index
|-- restaurants_index
```

---

## How the Core Monolith Calls a Microservice (Folder-Level View)

```
core-monolith/app/booking/clients/inventory_client.py
        |
        | (makes HTTP call using httpx)
        v
http://inventory-service:8002/v1/inventory/lock
        |
        v
services/inventory-service/app/routes.py
(receives request, processes, returns response)
```

This `clients/` folder pattern inside Booking module is important — it keeps all "calls to other services" organized in one place instead of scattered across the codebase.

---

## Summary Checklist for This Structure

```
[ ] Core Monolith = 1 repo/folder, 1 database, multiple internal modules
[ ] Each Microservice = own folder, own database, own Dockerfile, own port
[ ] Core Monolith talks to Microservices via clients/ folder (HTTP calls)
[ ] Microservices talk back via RabbitMQ events (for async notifications)
[ ] Nginx sits in front of everything, routes by URL path
[ ] docker-compose.yml ties everything together for local development
[ ] Optional shared-lib avoids duplicating common code (JWT, response format)
```

---

Would you like me to go deeper into:
1. What exact files go inside one module (e.g., full `auth/` folder file-by-file breakdown)?
2. The `docker-compose.yml` structure in more plan-level detail (what each block needs)?
3. How `nginx.conf` routing rules are structured to split traffic between monolith and microservices?
4. The exact contract (request/response) between Core Monolith and Inventory Service for seat locking?