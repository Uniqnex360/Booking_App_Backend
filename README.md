# Booking Platform — API Documentation
### Backend: Python (FastAPI) | Version: 1.0.0
### Base URL: `https://api.bookingplatform.com/v1`

---

## General Conventions

### Request Headers (All Endpoints)

```
Content-Type:     application/json
Authorization:    Bearer <access_token>   (required on protected routes)
X-Request-ID:     <uuid>                  (optional, for tracing)
Accept-Language:  en                      (optional)
```

### Standard Success Response Structure

```json
{
  "status": "success",
  "code": 200,
  "data": {},
  "message": "Request completed successfully"
}
```

### Standard Error Response Structure

```json
{
  "status": "error",
  "code": 400,
  "error": {
    "type": "VALIDATION_ERROR",
    "message": "Human readable message",
    "details": []
  }
}
```

### HTTP Status Codes Used

| Code | Meaning |
|---|---|
| 200 | Success |
| 201 | Resource created |
| 400 | Bad request / Validation error |
| 401 | Unauthenticated |
| 403 | Forbidden (insufficient role) |
| 404 | Resource not found |
| 409 | Conflict (duplicate, already exists) |
| 422 | Unprocessable entity |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

### Role Types

| Role | Description |
|---|---|
| `USER` | End consumer using the app |
| `PARTNER` | Restaurant, cinema or event organiser |
| `ADMIN` | Internal operations team |

---

## Auth Service

### POST `/auth/register`
Register a new user account.

**Auth required:** No

**Request Body:**
```json
{
  "full_name": "Arjun Mehta",
  "email": "arjun@example.com",
  "phone": "+919876543210",
  "password": "StrongPass@123"
}
```

**Response 201:**
```json
{
  "status": "success",
  "code": 201,
  "data": {
    "user_id": "usr_01J4K8X2P",
    "full_name": "Arjun Mehta",
    "email": "arjun@example.com",
    "phone": "+919876543210",
    "role": "USER",
    "is_verified": false,
    "created_at": "2025-08-19T10:00:00Z"
  },
  "message": "Account created. OTP sent to your phone."
}
```

**Response 409:**
```json
{
  "status": "error",
  "code": 409,
  "error": {
    "type": "DUPLICATE_EMAIL",
    "message": "An account with this email already exists."
  }
}
```

---

### POST `/auth/send-otp`
Send OTP to phone or email for verification.

**Auth required:** No

**Request Body:**
```json
{
  "phone": "+919876543210",
  "purpose": "REGISTRATION"
}
```

**Purpose values:** `REGISTRATION` | `LOGIN` | `PASSWORD_RESET`

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "otp_token": "otp_abc123xyz",
    "expires_in_seconds": 300
  },
  "message": "OTP sent successfully."
}
```

---

### POST `/auth/verify-otp`
Verify the OTP entered by the user.

**Auth required:** No

**Request Body:**
```json
{
  "otp_token": "otp_abc123xyz",
  "otp_code": "847291"
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "verified": true
  },
  "message": "Phone number verified successfully."
}
```

---

### POST `/auth/login`
Login with email and password.

**Auth required:** No

**Request Body:**
```json
{
  "email": "arjun@example.com",
  "password": "StrongPass@123"
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "Bearer",
    "expires_in": 900,
    "user": {
      "user_id": "usr_01J4K8X2P",
      "full_name": "Arjun Mehta",
      "email": "arjun@example.com",
      "role": "USER"
    }
  },
  "message": "Login successful."
}
```

**Response 401:**
```json
{
  "status": "error",
  "code": 401,
  "error": {
    "type": "INVALID_CREDENTIALS",
    "message": "Email or password is incorrect."
  }
}
```

---

### POST `/auth/login/phone`
Login using phone number and OTP.

**Auth required:** No

**Request Body:**
```json
{
  "phone": "+919876543210",
  "otp_code": "847291",
  "otp_token": "otp_abc123xyz"
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "Bearer",
    "expires_in": 900,
    "user": {
      "user_id": "usr_01J4K8X2P",
      "full_name": "Arjun Mehta",
      "role": "USER"
    }
  },
  "message": "Login successful."
}
```

---

### POST `/auth/refresh`
Refresh the access token using a refresh token.

**Auth required:** No

**Request Body:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expires_in": 900
  },
  "message": "Token refreshed successfully."
}
```

---

### POST `/auth/logout`
Invalidate the current session.

**Auth required:** Yes (USER / PARTNER / ADMIN)

**Request Body:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": null,
  "message": "Logged out successfully."
}
```

---

### POST `/auth/password/reset-request`
Request a password reset link or OTP.

**Auth required:** No

**Request Body:**
```json
{
  "email": "arjun@example.com"
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "reset_token": "rst_xyz789abc",
    "expires_in_seconds": 600
  },
  "message": "Password reset instructions sent to your email."
}
```

---

### POST `/auth/password/reset`
Set a new password after reset verification.

**Auth required:** No

**Request Body:**
```json
{
  "reset_token": "rst_xyz789abc",
  "new_password": "NewStrongPass@456"
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": null,
  "message": "Password reset successfully. Please log in."
}
```

---

## User Service

### GET `/users/me`
Get the current authenticated user's profile.

**Auth required:** Yes (USER)

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "user_id": "usr_01J4K8X2P",
    "full_name": "Arjun Mehta",
    "email": "arjun@example.com",
    "phone": "+919876543210",
    "avatar_url": "https://cdn.bookingplatform.com/avatars/usr_01J4K8X2P.jpg",
    "role": "USER",
    "is_verified": true,
    "created_at": "2025-08-19T10:00:00Z"
  },
  "message": "Profile fetched successfully."
}
```

---

### PATCH `/users/me`
Update the current user's profile.

**Auth required:** Yes (USER)

**Request Body:**
```json
{
  "full_name": "Arjun R Mehta",
  "avatar_url": "https://cdn.bookingplatform.com/avatars/usr_new.jpg"
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "user_id": "usr_01J4K8X2P",
    "full_name": "Arjun R Mehta",
    "email": "arjun@example.com",
    "avatar_url": "https://cdn.bookingplatform.com/avatars/usr_new.jpg"
  },
  "message": "Profile updated successfully."
}
```

---

### GET `/users/me/addresses`
Fetch all saved addresses for the current user.

**Auth required:** Yes (USER)

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "addresses": [
      {
        "address_id": "addr_001",
        "label": "Home",
        "line1": "42 MG Road",
        "line2": "Apartment 4B",
        "city": "Bengaluru",
        "state": "Karnataka",
        "pincode": "560001",
        "latitude": 12.9716,
        "longitude": 77.5946,
        "is_default": true
      }
    ]
  },
  "message": "Addresses fetched successfully."
}
```

---

### POST `/users/me/addresses`
Add a new address for the current user.

**Auth required:** Yes (USER)

**Request Body:**
```json
{
  "label": "Work",
  "line1": "Prestige Tech Park, Block A",
  "city": "Bengaluru",
  "state": "Karnataka",
  "pincode": "560103",
  "latitude": 12.9344,
  "longitude": 77.6101,
  "is_default": false
}
```

**Response 201:**
```json
{
  "status": "success",
  "code": 201,
  "data": {
    "address_id": "addr_002",
    "label": "Work",
    "city": "Bengaluru",
    "is_default": false
  },
  "message": "Address added successfully."
}
```

---

### GET `/users/me/bookings`
Fetch current user's booking history.

**Auth required:** Yes (USER)

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `type` | string | `movie` / `event` / `restaurant` / `all` |
| `status` | string | `upcoming` / `completed` / `cancelled` |
| `page` | integer | Page number (default: 1) |
| `limit` | integer | Results per page (default: 10) |

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "bookings": [
      {
        "booking_id": "bkg_9876",
        "type": "movie",
        "title": "Interstellar",
        "venue": "PVR Forum Mall, Bengaluru",
        "show_date": "2025-08-20",
        "show_time": "19:30",
        "seats": ["E4", "E5"],
        "total_amount": 480.00,
        "status": "CONFIRMED",
        "ticket_url": "https://cdn.bookingplatform.com/tickets/bkg_9876.pdf",
        "created_at": "2025-08-19T10:00:00Z"
      }
    ],
    "pagination": {
      "total": 12,
      "page": 1,
      "limit": 10,
      "total_pages": 2
    }
  },
  "message": "Bookings fetched successfully."
}
```

---

## Restaurant Service

### GET `/restaurants`
List restaurants with filters.

**Auth required:** No

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `city` | string | City name |
| `latitude` | float | User latitude |
| `longitude` | float | User longitude |
| `radius_km` | float | Search radius in km (default: 5) |
| `cuisine` | string | Filter by cuisine type |
| `rating` | float | Minimum rating (e.g. 4.0) |
| `price_range` | string | `low` / `medium` / `high` |
| `open_now` | boolean | Show only currently open |
| `page` | integer | Page number |
| `limit` | integer | Results per page |

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "restaurants": [
      {
        "restaurant_id": "rst_001",
        "name": "The Spice Route",
        "cuisine": ["Indian", "Mughlai"],
        "address": "12 Church Street, Bengaluru",
        "city": "Bengaluru",
        "distance_km": 1.2,
        "rating": 4.5,
        "total_reviews": 1230,
        "price_for_two": 1200,
        "price_range": "medium",
        "is_open": true,
        "opens_at": "12:00",
        "closes_at": "23:00",
        "thumbnail_url": "https://cdn.bookingplatform.com/rst_001/thumb.jpg",
        "tags": ["rooftop", "family dining", "valet parking"]
      }
    ],
    "pagination": {
      "total": 48,
      "page": 1,
      "limit": 10,
      "total_pages": 5
    }
  },
  "message": "Restaurants fetched successfully."
}
```

---

### GET `/restaurants/{restaurant_id}`
Get full details of a single restaurant.

**Auth required:** No

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "restaurant_id": "rst_001",
    "name": "The Spice Route",
    "description": "Award-winning North Indian cuisine in the heart of the city.",
    "cuisine": ["Indian", "Mughlai"],
    "address": "12 Church Street, Bengaluru",
    "city": "Bengaluru",
    "latitude": 12.9716,
    "longitude": 77.5946,
    "phone": "+918012345678",
    "rating": 4.5,
    "total_reviews": 1230,
    "price_for_two": 1200,
    "is_open": true,
    "timings": {
      "monday": "12:00 - 23:00",
      "tuesday": "12:00 - 23:00",
      "saturday": "11:00 - 23:30",
      "sunday": "11:00 - 23:00"
    },
    "photos": [
      "https://cdn.bookingplatform.com/rst_001/photo1.jpg",
      "https://cdn.bookingplatform.com/rst_001/photo2.jpg"
    ],
    "amenities": ["wifi", "valet parking", "outdoor seating", "bar"],
    "menu_categories": [
      {
        "category_id": "cat_01",
        "name": "Starters",
        "items": [
          {
            "item_id": "item_001",
            "name": "Chicken Tikka",
            "description": "Tender chicken marinated in yoghurt and spices.",
            "price": 380.00,
            "is_veg": false,
            "is_available": true,
            "photo_url": "https://cdn.bookingplatform.com/items/item_001.jpg"
          }
        ]
      }
    ]
  },
  "message": "Restaurant details fetched successfully."
}
```

---

### GET `/restaurants/{restaurant_id}/availability`
Check table availability for a specific date and party size.

**Auth required:** No

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `date` | string | Date in YYYY-MM-DD format |
| `party_size` | integer | Number of guests |

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "restaurant_id": "rst_001",
    "date": "2025-08-20",
    "party_size": 4,
    "available_slots": [
      {
        "slot_id": "slot_101",
        "time": "19:00",
        "available_tables": 3
      },
      {
        "slot_id": "slot_102",
        "time": "19:30",
        "available_tables": 1
      },
      {
        "slot_id": "slot_103",
        "time": "21:00",
        "available_tables": 5
      }
    ]
  },
  "message": "Availability fetched successfully."
}
```

---

## Movie Service

### GET `/movies`
List currently showing and upcoming movies.

**Auth required:** No

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `city` | string | City name |
| `status` | string | `now_showing` / `upcoming` |
| `language` | string | Filter by language |
| `genre` | string | Filter by genre |
| `page` | integer | Page number |
| `limit` | integer | Results per page |

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "movies": [
      {
        "movie_id": "mov_001",
        "title": "Interstellar",
        "genre": ["Sci-Fi", "Drama"],
        "language": ["English", "Hindi"],
        "duration_minutes": 169,
        "rating": "UA",
        "imdb_rating": 8.6,
        "release_date": "2025-08-15",
        "status": "now_showing",
        "poster_url": "https://cdn.bookingplatform.com/movies/mov_001/poster.jpg",
        "trailer_url": "https://youtube.com/watch?v=xyz"
      }
    ],
    "pagination": {
      "total": 20,
      "page": 1,
      "limit": 10,
      "total_pages": 2
    }
  },
  "message": "Movies fetched successfully."
}
```

---

### GET `/movies/{movie_id}`
Get full details of a movie.

**Auth required:** No

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "movie_id": "mov_001",
    "title": "Interstellar",
    "description": "A team of explorers travel through a wormhole in space.",
    "genre": ["Sci-Fi", "Drama"],
    "language": ["English", "Hindi"],
    "duration_minutes": 169,
    "director": "Christopher Nolan",
    "cast": ["Matthew McConaughey", "Anne Hathaway"],
    "rating": "UA",
    "imdb_rating": 8.6,
    "release_date": "2025-08-15",
    "status": "now_showing",
    "poster_url": "https://cdn.bookingplatform.com/movies/mov_001/poster.jpg",
    "banner_url": "https://cdn.bookingplatform.com/movies/mov_001/banner.jpg",
    "trailer_url": "https://youtube.com/watch?v=xyz"
  },
  "message": "Movie details fetched successfully."
}
```

---

### GET `/movies/{movie_id}/showtimes`
Get all showtimes for a movie in a city.

**Auth required:** No

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `city` | string | City name (required) |
| `date` | string | Date in YYYY-MM-DD format (required) |
| `format` | string | `2D` / `3D` / `IMAX` |
| `language` | string | Filter by language |

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "movie_id": "mov_001",
    "title": "Interstellar",
    "date": "2025-08-20",
    "cinemas": [
      {
        "cinema_id": "cin_001",
        "cinema_name": "PVR Forum Mall",
        "address": "Koramangala, Bengaluru",
        "showtimes": [
          {
            "showtime_id": "sht_001",
            "time": "10:00",
            "language": "English",
            "format": "IMAX",
            "available_seats": 42,
            "total_seats": 120,
            "price_range": {
              "min": 300,
              "max": 600
            }
          },
          {
            "showtime_id": "sht_002",
            "time": "14:30",
            "language": "Hindi",
            "format": "2D",
            "available_seats": 98,
            "total_seats": 200,
            "price_range": {
              "min": 150,
              "max": 250
            }
          }
        ]
      }
    ]
  },
  "message": "Showtimes fetched successfully."
}
```

---

### GET `/movies/showtimes/{showtime_id}/seats`
Get the seat map for a specific showtime.

**Auth required:** Yes (USER)

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "showtime_id": "sht_001",
    "cinema_name": "PVR Forum Mall",
    "screen": "Screen 3 - IMAX",
    "total_seats": 120,
    "available_seats": 42,
    "seat_categories": [
      {
        "category": "RECLINER",
        "price": 600,
        "seats": [
          {
            "seat_id": "seat_A1",
            "row": "A",
            "number": 1,
            "status": "AVAILABLE"
          },
          {
            "seat_id": "seat_A2",
            "row": "A",
            "number": 2,
            "status": "BOOKED"
          }
        ]
      },
      {
        "category": "PREMIUM",
        "price": 400,
        "seats": [
          {
            "seat_id": "seat_E4",
            "row": "E",
            "number": 4,
            "status": "AVAILABLE"
          },
          {
            "seat_id": "seat_E5",
            "row": "E",
            "number": 5,
            "status": "LOCKED"
          }
        ]
      }
    ]
  },
  "message": "Seat map fetched successfully."
}
```

**Seat Status Values:**

| Status | Meaning |
|---|---|
| `AVAILABLE` | Can be selected |
| `LOCKED` | Temporarily held by another user (within 8-min window) |
| `BOOKED` | Permanently sold |
| `BLOCKED` | Blocked by partner or admin |

---

## Event Service

### GET `/events`
List all events with filters.

**Auth required:** No

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `city` | string | City name |
| `category` | string | `concert` / `comedy` / `sports` / `theatre` / `festival` |
| `date_from` | string | Start date YYYY-MM-DD |
| `date_to` | string | End date YYYY-MM-DD |
| `price_max` | integer | Max ticket price |
| `latitude` | float | User latitude |
| `longitude` | float | User longitude |
| `page` | integer | Page number |
| `limit` | integer | Results per page |

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "events": [
      {
        "event_id": "evt_001",
        "title": "Coldplay Live in Bengaluru",
        "category": "concert",
        "venue": "Kanteerava Stadium",
        "city": "Bengaluru",
        "date": "2025-09-10",
        "time": "19:00",
        "duration_hours": 3,
        "price_from": 2500,
        "price_to": 15000,
        "available_tickets": 1200,
        "thumbnail_url": "https://cdn.bookingplatform.com/events/evt_001/thumb.jpg",
        "source": "DIRECT",
        "is_featured": true
      }
    ],
    "pagination": {
      "total": 35,
      "page": 1,
      "limit": 10,
      "total_pages": 4
    }
  },
  "message": "Events fetched successfully."
}
```

---

### GET `/events/{event_id}`
Get full details of a single event.

**Auth required:** No

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "event_id": "evt_001",
    "title": "Coldplay Live in Bengaluru",
    "description": "Coldplay returns to India for their Music of the Spheres World Tour.",
    "category": "concert",
    "venue": "Kanteerava Stadium",
    "address": "Kasturba Road, Bengaluru - 560001",
    "city": "Bengaluru",
    "latitude": 12.9772,
    "longitude": 77.5960,
    "date": "2025-09-10",
    "time": "19:00",
    "duration_hours": 3,
    "language": "English",
    "age_restriction": "All ages",
    "source": "DIRECT",
    "partner_id": "prt_002",
    "ticket_categories": [
      {
        "category_id": "tkt_cat_01",
        "name": "General Standing",
        "price": 2500,
        "available": 800,
        "total": 1000
      },
      {
        "category_id": "tkt_cat_02",
        "name": "Gold Seated",
        "price": 7500,
        "available": 200,
        "total": 300
      },
      {
        "category_id": "tkt_cat_03",
        "name": "Platinum Front Row",
        "price": 15000,
        "available": 40,
        "total": 50
      }
    ],
    "photos": [
      "https://cdn.bookingplatform.com/events/evt_001/photo1.jpg"
    ],
    "poster_url": "https://cdn.bookingplatform.com/events/evt_001/poster.jpg"
  },
  "message": "Event details fetched successfully."
}
```

---

## Inventory Service

### POST `/inventory/lock`
Temporarily lock selected seats or tickets for a user.

**Auth required:** Yes (USER)

**Request Body:**
```json
{
  "resource_type": "movie_seats",
  "showtime_id": "sht_001",
  "seat_ids": ["seat_E4", "seat_E5"],
  "user_id": "usr_01J4K8X2P"
}
```

**Resource Type Values:** `movie_seats` | `event_tickets` | `restaurant_table`

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "lock_id": "lock_xyz001",
    "locked_seats": ["seat_E4", "seat_E5"],
    "expires_at": "2025-08-19T10:08:00Z",
    "lock_duration_seconds": 480
  },
  "message": "Seats locked successfully. Complete payment within 8 minutes."
}
```

**Response 409 (Seat already locked):**
```json
{
  "status": "error",
  "code": 409,
  "error": {
    "type": "SEAT_UNAVAILABLE",
    "message": "One or more selected seats are no longer available.",
    "details": [
      {
        "seat_id": "seat_E5",
        "status": "LOCKED"
      }
    ]
  }
}
```

---

### POST `/inventory/release`
Manually release a lock (on payment failure or cancellation).

**Auth required:** Yes (USER / ADMIN)

**Request Body:**
```json
{
  "lock_id": "lock_xyz001"
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "lock_id": "lock_xyz001",
    "released": true
  },
  "message": "Seats released successfully."
}
```

---

### GET `/inventory/status`
Check current availability status of seats or tickets.

**Auth required:** No

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `resource_type` | string | `movie_seats` / `event_tickets` |
| `showtime_id` | string | Showtime or event ID |

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "showtime_id": "sht_001",
    "total_seats": 120,
    "available": 42,
    "locked": 8,
    "booked": 70
  },
  "message": "Inventory status fetched successfully."
}
```

---

## Booking Service

### POST `/bookings`
Create a new booking (after successful payment).

**Auth required:** Yes (USER)

**Request Body:**
```json
{
  "booking_type": "movie",
  "showtime_id": "sht_001",
  "seat_ids": ["seat_E4", "seat_E5"],
  "lock_id": "lock_xyz001",
  "payment_id": "pay_razorpay_001",
  "user_id": "usr_01J4K8X2P",
  "contact": {
    "email": "arjun@example.com",
    "phone": "+919876543210"
  }
}
```

**Booking Type Values:** `movie` | `event` | `restaurant`

**Response 201:**
```json
{
  "status": "success",
  "code": 201,
  "data": {
    "booking_id": "bkg_9876",
    "booking_type": "movie",
    "status": "CONFIRMED",
    "movie": {
      "title": "Interstellar",
      "cinema": "PVR Forum Mall",
      "screen": "Screen 3 - IMAX",
      "date": "2025-08-20",
      "time": "19:30"
    },
    "seats": ["E4", "E5"],
    "total_amount": 480.00,
    "payment_id": "pay_razorpay_001",
    "ticket_url": null,
    "qr_code_url": null,
    "created_at": "2025-08-19T10:00:00Z",
    "note": "Ticket and QR code will be sent to your email and phone shortly."
  },
  "message": "Booking confirmed. Ticket will arrive within 2 minutes."
}
```

---

### GET `/bookings/{booking_id}`
Get full details of a specific booking.

**Auth required:** Yes (USER / ADMIN)

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "booking_id": "bkg_9876",
    "booking_type": "movie",
    "status": "CONFIRMED",
    "user_id": "usr_01J4K8X2P",
    "movie": {
      "movie_id": "mov_001",
      "title": "Interstellar",
      "cinema": "PVR Forum Mall",
      "screen": "Screen 3 - IMAX",
      "date": "2025-08-20",
      "time": "19:30",
      "language": "English",
      "format": "IMAX"
    },
    "seats": [
      { "seat_id": "seat_E4", "row": "E", "number": 4, "category": "PREMIUM" },
      { "seat_id": "seat_E5", "row": "E", "number": 5, "category": "PREMIUM" }
    ],
    "pricing": {
      "subtotal": 800.00,
      "convenience_fee": 40.00,
      "gst": 40.00,
      "total": 480.00
    },
    "payment": {
      "payment_id": "pay_razorpay_001",
      "method": "UPI",
      "status": "PAID"
    },
    "ticket_url": "https://cdn.bookingplatform.com/tickets/bkg_9876.pdf",
    "qr_code_url": "https://cdn.bookingplatform.com/qr/bkg_9876.png",
    "created_at": "2025-08-19T10:00:00Z"
  },
  "message": "Booking details fetched successfully."
}
```

---

### POST `/bookings/{booking_id}/cancel`
Cancel a booking and initiate refund.

**Auth required:** Yes (USER / ADMIN)

**Request Body:**
```json
{
  "reason": "Change of plans"
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "booking_id": "bkg_9876",
    "status": "CANCELLED",
    "refund": {
      "refund_id": "ref_001",
      "amount": 480.00,
      "method": "ORIGINAL_PAYMENT_METHOD",
      "estimated_days": 5,
      "status": "INITIATED"
    }
  },
  "message": "Booking cancelled. Refund will be processed in 5 business days."
}
```

---

## Payment Service

### POST `/payments/initiate`
Initiate a payment before confirming a booking.

**Auth required:** Yes (USER)

**Request Body:**
```json
{
  "booking_type": "movie",
  "reference_id": "sht_001",
  "seat_ids": ["seat_E4", "seat_E5"],
  "lock_id": "lock_xyz001",
  "amount": 480.00,
  "currency": "INR",
  "payment_method": "UPI"
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "payment_order_id": "order_razorpay_abc123",
    "amount": 480.00,
    "currency": "INR",
    "razorpay_key": "rzp_test_XXXXXXXXXX",
    "expires_at": "2025-08-19T10:08:00Z"
  },
  "message": "Payment order created. Complete payment within 8 minutes."
}
```

---

### POST `/payments/verify`
Verify payment after Razorpay callback.

**Auth required:** Yes (USER)

**Request Body:**
```json
{
  "razorpay_order_id": "order_razorpay_abc123",
  "razorpay_payment_id": "pay_razorpay_001",
  "razorpay_signature": "hmac_sha256_signature_here"
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "payment_id": "pay_razorpay_001",
    "payment_status": "SUCCESS",
    "amount": 480.00,
    "currency": "INR",
    "method": "UPI",
    "paid_at": "2025-08-19T10:03:22Z"
  },
  "message": "Payment verified successfully."
}
```

---

### POST `/payments/refund`
Initiate a refund for a cancelled booking.

**Auth required:** Yes (ADMIN)

**Request Body:**
```json
{
  "payment_id": "pay_razorpay_001",
  "booking_id": "bkg_9876",
  "amount": 480.00,
  "reason": "Customer cancellation within allowed window"
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "refund_id": "ref_001",
    "payment_id": "pay_razorpay_001",
    "amount": 480.00,
    "status": "INITIATED",
    "estimated_days": 5
  },
  "message": "Refund initiated successfully."
}
```

---

### POST `/payments/split`
Split a bill between multiple users.

**Auth required:** Yes (USER)

**Request Body:**
```json
{
  "booking_id": "bkg_9876",
  "total_amount": 960.00,
  "split_with": [
    { "user_id": "usr_002", "amount": 480.00 },
    { "user_id": "usr_003", "amount": 480.00 }
  ]
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "split_id": "spl_001",
    "booking_id": "bkg_9876",
    "total_amount": 960.00,
    "splits": [
      {
        "user_id": "usr_002",
        "amount": 480.00,
        "status": "PENDING",
        "payment_link": "https://pay.bookingplatform.com/split/spl_001_usr002"
      },
      {
        "user_id": "usr_003",
        "amount": 480.00,
        "status": "PENDING",
        "payment_link": "https://pay.bookingplatform.com/split/spl_001_usr003"
      }
    ]
  },
  "message": "Split payment request sent to all users."
}
```

---

## Search Service

### GET `/search`
Universal search across movies, events and restaurants.

**Auth required:** No

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `q` | string | Search keyword (required) |
| `type` | string | `all` / `movie` / `event` / `restaurant` |
| `city` | string | City name |
| `latitude` | float | User latitude |
| `longitude` | float | User longitude |
| `page` | integer | Page number |
| `limit` | integer | Results per page |

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "query": "comedy",
    "total_results": 24,
    "results": {
      "movies": [
        {
          "movie_id": "mov_005",
          "title": "Life of Pi Comedy Night",
          "type": "movie",
          "poster_url": "https://cdn.bookingplatform.com/movies/mov_005/poster.jpg"
        }
      ],
      "events": [
        {
          "event_id": "evt_012",
          "title": "Zakir Khan Live - Bengaluru",
          "type": "event",
          "category": "comedy",
          "date": "2025-09-05",
          "price_from": 799,
          "thumbnail_url": "https://cdn.bookingplatform.com/events/evt_012/thumb.jpg"
        }
      ],
      "restaurants": []
    }
  },
  "message": "Search results fetched successfully."
}
```

---

### GET `/search/suggestions`
Autocomplete suggestions while user is typing.

**Auth required:** No

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `q` | string | Partial search text (min 2 characters) |
| `city` | string | City name |

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "suggestions": [
      { "type": "movie", "id": "mov_001", "label": "Interstellar" },
      { "type": "event", "id": "evt_001", "label": "Coldplay Live in Bengaluru" },
      { "type": "restaurant", "id": "rst_001", "label": "The Spice Route" }
    ]
  },
  "message": "Suggestions fetched successfully."
}
```

---

## Notification Service

### POST `/notifications/send`
Manually trigger a notification (admin or internal use).

**Auth required:** Yes (ADMIN)

**Request Body:**
```json
{
  "user_ids": ["usr_01J4K8X2P"],
  "channel": "push",
  "title": "Your booking is confirmed",
  "body": "Interstellar at PVR Forum Mall on Aug 20 at 7:30 PM. Enjoy the show!",
  "data": {
    "booking_id": "bkg_9876",
    "type": "booking_confirmation"
  }
}
```

**Channel Values:** `push` | `sms` | `email` | `whatsapp`

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "notification_id": "notif_001",
    "sent_to": 1,
    "channel": "push",
    "status": "QUEUED"
  },
  "message": "Notification queued successfully."
}
```

---

### GET `/notifications/me`
Fetch notification history for the current user.

**Auth required:** Yes (USER)

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "notifications": [
      {
        "notification_id": "notif_001",
        "title": "Booking Confirmed",
        "body": "Interstellar at PVR Forum Mall on Aug 20 at 7:30 PM.",
        "is_read": false,
        "created_at": "2025-08-19T10:00:00Z"
      }
    ],
    "unread_count": 1
  },
  "message": "Notifications fetched successfully."
}
```

---

## Partner Service

### POST `/partner/register`
Register a new partner account.

**Auth required:** No

**Request Body:**
```json
{
  "business_name": "PVR Cinemas Pvt Ltd",
  "partner_type": "cinema",
  "contact_name": "Rohan Kapoor",
  "email": "rohan@pvrcinemas.com",
  "phone": "+918011223344",
  "password": "PartnerPass@123",
  "city": "Bengaluru",
  "gst_number": "29ABCDE1234F1Z5",
  "pan_number": "ABCDE1234F"
}
```

**Partner Type Values:** `restaurant` | `cinema` | `event_organiser`

**Response 201:**
```json
{
  "status": "success",
  "code": 201,
  "data": {
    "partner_id": "prt_002",
    "business_name": "PVR Cinemas Pvt Ltd",
    "partner_type": "cinema",
    "email": "rohan@pvrcinemas.com",
    "status": "PENDING_APPROVAL",
    "created_at": "2025-08-19T10:00:00Z"
  },
  "message": "Partner registration submitted. Awaiting admin approval."
}
```

---

### POST `/partner/movies`
Partner adds a new movie listing.

**Auth required:** Yes (PARTNER)

**Request Body:**
```json
{
  "title": "Interstellar",
  "language": "English",
  "format": "IMAX",
  "duration_minutes": 169,
  "genre": ["Sci-Fi", "Drama"],
  "rating": "UA",
  "release_date": "2025-08-15",
  "poster_url": "https://cdn.bookingplatform.com/movies/mov_001/poster.jpg",
  "trailer_url": "https://youtube.com/watch?v=xyz",
  "showtimes": [
    {
      "screen_id": "scr_001",
      "date": "2025-08-20",
      "time": "19:30",
      "price_regular": 250,
      "price_premium": 400,
      "price_recliner": 600
    }
  ]
}
```

**Response 201:**
```json
{
  "status": "success",
  "code": 201,
  "data": {
    "movie_id": "mov_001",
    "title": "Interstellar",
    "status": "PENDING_APPROVAL",
    "showtimes_added": 1
  },
  "message": "Movie submitted for admin approval."
}
```

---

### POST `/partner/events`
Partner adds a new event listing.

**Auth required:** Yes (PARTNER)

**Request Body:**
```json
{
  "title": "Zakir Khan Live - Bengaluru",
  "category": "comedy",
  "description": "An evening of pure entertainment with Zakir Khan.",
  "venue": "St. Joseph's Indoor Stadium",
  "city": "Bengaluru",
  "address": "Museum Road, Bengaluru - 560025",
  "latitude": 12.9740,
  "longitude": 77.5964,
  "date": "2025-09-05",
  "time": "19:30",
  "duration_hours": 2,
  "age_restriction": "13+",
  "ticket_categories": [
    {
      "name": "General",
      "price": 799,
      "total_tickets": 500
    },
    {
      "name": "Premium",
      "price": 1499,
      "total_tickets": 100
    }
  ],
  "poster_url": "https://cdn.bookingplatform.com/events/evt_012/poster.jpg"
}
```

**Response 201:**
```json
{
  "status": "success",
  "code": 201,
  "data": {
    "event_id": "evt_012",
    "title": "Zakir Khan Live - Bengaluru",
    "status": "PENDING_APPROVAL",
    "created_at": "2025-08-19T10:00:00Z"
  },
  "message": "Event submitted for admin approval."
}
```

---

### GET `/partner/bookings`
Partner views all bookings for their listings.

**Auth required:** Yes (PARTNER)

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `type` | string | `movie` / `event` / `restaurant` |
| `date` | string | Filter by date YYYY-MM-DD |
| `status` | string | `confirmed` / `cancelled` |
| `page` | integer | Page number |

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "bookings": [
      {
        "booking_id": "bkg_9876",
        "booking_type": "movie",
        "movie_title": "Interstellar",
        "show_date": "2025-08-20",
        "show_time": "19:30",
        "seats": ["E4", "E5"],
        "user_name": "Arjun Mehta",
        "amount": 480.00,
        "status": "CONFIRMED",
        "created_at": "2025-08-19T10:00:00Z"
      }
    ],
    "pagination": {
      "total": 50,
      "page": 1,
      "limit": 10,
      "total_pages": 5
    }
  },
  "message": "Bookings fetched successfully."
}
```

---

### POST `/partner/checkin`
Check in a guest by scanning QR code.

**Auth required:** Yes (PARTNER)

**Request Body:**
```json
{
  "booking_id": "bkg_9876",
  "qr_code": "QR_DATA_DECODED_FROM_SCAN"
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "booking_id": "bkg_9876",
    "user_name": "Arjun Mehta",
    "seats": ["E4", "E5"],
    "checked_in": true,
    "checked_in_at": "2025-08-20T19:22:00Z"
  },
  "message": "Guest checked in successfully."
}
```

---

### GET `/partner/reports/sales`
Get sales report for partner's listings.

**Auth required:** Yes (PARTNER)

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `from_date` | string | Start date YYYY-MM-DD |
| `to_date` | string | End date YYYY-MM-DD |
| `type` | string | `movie` / `event` / `restaurant` |

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "period": {
      "from": "2025-08-01",
      "to": "2025-08-19"
    },
    "summary": {
      "total_bookings": 320,
      "total_revenue": 128000.00,
      "platform_commission": 12800.00,
      "partner_payout": 115200.00
    },
    "breakdown": [
      {
        "date": "2025-08-19",
        "bookings": 20,
        "revenue": 8000.00
      }
    ]
  },
  "message": "Sales report fetched successfully."
}
```

---

## Admin Service

### GET `/admin/partners`
List all partner registrations.

**Auth required:** Yes (ADMIN)

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `status` | string | `PENDING_APPROVAL` / `APPROVED` / `SUSPENDED` |
| `type` | string | `restaurant` / `cinema` / `event_organiser` |
| `page` | integer | Page number |

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "partners": [
      {
        "partner_id": "prt_002",
        "business_name": "PVR Cinemas Pvt Ltd",
        "partner_type": "cinema",
        "contact_name": "Rohan Kapoor",
        "email": "rohan@pvrcinemas.com",
        "city": "Bengaluru",
        "status": "PENDING_APPROVAL",
        "created_at": "2025-08-19T10:00:00Z"
      }
    ],
    "pagination": {
      "total": 12,
      "page": 1,
      "limit": 10,
      "total_pages": 2
    }
  },
  "message": "Partners fetched successfully."
}
```

---

### PATCH `/admin/partners/{partner_id}/status`
Approve, reject or suspend a partner.

**Auth required:** Yes (ADMIN)

**Request Body:**
```json
{
  "status": "APPROVED",
  "note": "All documents verified. Partner approved."
}
```

**Status Values:** `APPROVED` | `REJECTED` | `SUSPENDED`

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "partner_id": "prt_002",
    "business_name": "PVR Cinemas Pvt Ltd",
    "status": "APPROVED",
    "updated_at": "2025-08-19T11:00:00Z"
  },
  "message": "Partner status updated successfully."
}
```

---

### PATCH `/admin/content/{content_id}/status`
Approve or reject a movie, event or restaurant listing.

**Auth required:** Yes (ADMIN)

**Request Body:**
```json
{
  "content_type": "movie",
  "status": "APPROVED",
  "note": "Content verified and approved."
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "content_id": "mov_001",
    "content_type": "movie",
    "status": "APPROVED",
    "updated_at": "2025-08-19T11:05:00Z"
  },
  "message": "Content approved and is now live."
}
```

---

### GET `/admin/analytics`
Platform-wide analytics overview.

**Auth required:** Yes (ADMIN)

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `from_date` | string | Start date YYYY-MM-DD |
| `to_date` | string | End date YYYY-MM-DD |

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "period": {
      "from": "2025-08-01",
      "to": "2025-08-19"
    },
    "summary": {
      "total_bookings": 12400,
      "total_revenue": 4960000.00,
      "total_users": 58000,
      "new_users": 3200,
      "total_partners": 240,
      "new_partners": 14
    },
    "breakdown_by_type": {
      "movie": {
        "bookings": 7800,
        "revenue": 3120000.00
      },
      "event": {
        "bookings": 3200,
        "revenue": 1280000.00
      },
      "restaurant": {
        "bookings": 1400,
        "revenue": 560000.00
      }
    },
    "top_events": [
      {
        "event_id": "evt_001",
        "title": "Coldplay Live in Bengaluru",
        "bookings": 980,
        "revenue": 1470000.00
      }
    ],
    "top_movies": [
      {
        "movie_id": "mov_001",
        "title": "Interstellar",
        "bookings": 2100
      }
    ]
  },
  "message": "Analytics fetched successfully."
}
```

---

### POST `/admin/inventory/force-release`
Force release locked seats in edge cases.

**Auth required:** Yes (ADMIN)

**Request Body:**
```json
{
  "showtime_id": "sht_001",
  "seat_ids": ["seat_E4", "seat_E5"],
  "reason": "Payment gateway timeout — seats stuck in LOCKED state"
}
```

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "released_seats": ["seat_E4", "seat_E5"],
    "showtime_id": "sht_001"
  },
  "message": "Seats force-released successfully."
}
```

---

## Media Service

### POST `/media/upload`
Upload an image or poster.

**Auth required:** Yes (PARTNER / ADMIN)

**Request:** `multipart/form-data`

| Field | Type | Description |
|---|---|---|
| `file` | file | Image file (JPG, PNG, WebP, max 5MB) |
| `resource_type` | string | `restaurant` / `movie` / `event` / `avatar` |
| `resource_id` | string | ID of the resource this image belongs to |

**Response 201:**
```json
{
  "status": "success",
  "code": 201,
  "data": {
    "media_id": "med_001",
    "url": "https://cdn.bookingplatform.com/rst_001/photo3.jpg",
    "thumbnail_url": "https://cdn.bookingplatform.com/rst_001/photo3_thumb.jpg",
    "size_bytes": 204800,
    "format": "jpg"
  },
  "message": "Image uploaded successfully."
}
```

---

## Review Service

### POST `/reviews`
Submit a review for a restaurant, movie or event.

**Auth required:** Yes (USER)

**Request Body:**
```json
{
  "resource_type": "restaurant",
  "resource_id": "rst_001",
  "booking_id": "bkg_9876",
  "rating": 4,
  "title": "Great food, slow service",
  "body": "The food quality was excellent but service was a little slow.",
  "photos": [
    "https://cdn.bookingplatform.com/reviews/photo1.jpg"
  ]
}
```

**Response 201:**
```json
{
  "status": "success",
  "code": 201,
  "data": {
    "review_id": "rev_001",
    "resource_type": "restaurant",
    "resource_id": "rst_001",
    "rating": 4,
    "status": "PUBLISHED",
    "created_at": "2025-08-19T12:00:00Z"
  },
  "message": "Review submitted successfully."
}
```

---

### GET `/reviews/{resource_type}/{resource_id}`
Fetch all reviews for a restaurant, movie or event.

**Auth required:** No

**Query Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `sort` | string | `recent` / `top_rated` / `lowest_rated` |
| `page` | integer | Page number |
| `limit` | integer | Results per page |

**Response 200:**
```json
{
  "status": "success",
  "code": 200,
  "data": {
    "resource_id": "rst_001",
    "resource_type": "restaurant",
    "average_rating": 4.5,
    "total_reviews": 1230,
    "rating_breakdown": {
      "5": 700,
      "4": 350,
      "3": 120,
      "2": 40,
      "1": 20
    },
    "reviews": [
      {
        "review_id": "rev_001",
        "user_name": "Arjun M.",
        "rating": 4,
        "title": "Great food, slow service",
        "body": "The food quality was excellent but service was a little slow.",
        "photos": [],
        "created_at": "2025-08-19T12:00:00Z"
      }
    ],
    "pagination": {
      "total": 1230,
      "page": 1,
      "limit": 10,
      "total_pages": 123
    }
  },
  "message": "Reviews fetched successfully."
}
```

---

## API Endpoint Summary

### Auth Service
| Method | Endpoint | Auth | Role |
|---|---|---|---|
| POST | `/auth/register` | No | — |
| POST | `/auth/send-otp` | No | — |
| POST | `/auth/verify-otp` | No | — |
| POST | `/auth/login` | No | — |
| POST | `/auth/login/phone` | No | — |
| POST | `/auth/refresh` | No | — |
| POST | `/auth/logout` | Yes | Any |
| POST | `/auth/password/reset-request` | No | — |
| POST | `/auth/password/reset` | No | — |

### User Service
| Method | Endpoint | Auth | Role |
|---|---|---|---|
| GET | `/users/me` | Yes | USER |
| PATCH | `/users/me` | Yes | USER |
| GET | `/users/me/addresses` | Yes | USER |
| POST | `/users/me/addresses` | Yes | USER |
| GET | `/users/me/bookings` | Yes | USER |

### Restaurant Service
| Method | Endpoint | Auth | Role |
|---|---|---|---|
| GET | `/restaurants` | No | — |
| GET | `/restaurants/{id}` | No | — |
| GET | `/restaurants/{id}/availability` | No | — |

### Movie Service
| Method | Endpoint | Auth | Role |
|---|---|---|---|
| GET | `/movies` | No | — |
| GET | `/movies/{id}` | No | — |
| GET | `/movies/{id}/showtimes` | No | — |
| GET | `/movies/showtimes/{id}/seats` | Yes | USER |

### Event Service
| Method | Endpoint | Auth | Role |
|---|---|---|---|
| GET | `/events` | No | — |
| GET | `/events/{id}` | No | — |

### Inventory Service
| Method | Endpoint | Auth | Role |
|---|---|---|---|
| POST | `/inventory/lock` | Yes | USER |
| POST | `/inventory/release` | Yes | USER / ADMIN |
| GET | `/inventory/status` | No | — |

### Booking Service
| Method | Endpoint | Auth | Role |
|---|---|---|---|
| POST | `/bookings` | Yes | USER |
| GET | `/bookings/{id}` | Yes | USER / ADMIN |
| POST | `/bookings/{id}/cancel` | Yes | USER / ADMIN |

### Payment Service
| Method | Endpoint | Auth | Role |
|---|---|---|---|
| POST | `/payments/initiate` | Yes | USER |
| POST | `/payments/verify` | Yes | USER |
| POST | `/payments/refund` | Yes | ADMIN |
| POST | `/payments/split` | Yes | USER |

### Search Service
| Method | Endpoint | Auth | Role |
|---|---|---|---|
| GET | `/search` | No | — |
| GET | `/search/suggestions` | No | — |

### Notification Service
| Method | Endpoint | Auth | Role |
|---|---|---|---|
| POST | `/notifications/send` | Yes | ADMIN |
| GET | `/notifications/me` | Yes | USER |

### Partner Service
| Method | Endpoint | Auth | Role |
|---|---|---|---|
| POST | `/partner/register` | No | — |
| POST | `/partner/movies` | Yes | PARTNER |
| POST | `/partner/events` | Yes | PARTNER |
| GET | `/partner/bookings` | Yes | PARTNER |
| POST | `/partner/checkin` | Yes | PARTNER |
| GET | `/partner/reports/sales` | Yes | PARTNER |

### Admin Service
| Method | Endpoint | Auth | Role |
|---|---|---|---|
| GET | `/admin/partners` | Yes | ADMIN |
| PATCH | `/admin/partners/{id}/status` | Yes | ADMIN |
| PATCH | `/admin/content/{id}/status` | Yes | ADMIN |
| GET | `/admin/analytics` | Yes | ADMIN |
| POST | `/admin/inventory/force-release` | Yes | ADMIN |

### Media and Review Services
| Method | Endpoint | Auth | Role |
|---|---|---|---|
| POST | `/media/upload` | Yes | PARTNER / ADMIN |
| POST | `/reviews` | Yes | USER |
| GET | `/reviews/{type}/{id}` | No | — |

---

Would you like me to prepare next:
- FastAPI folder and file structure for the full project?
- PostgreSQL database schema for all services?
- Sequence diagrams for booking, payment and cancellation flows?
- Celery task definitions and RabbitMQ queue setup?

psql -U booking_user -d core_db -h localhost -p 5433
cd /home/lexicon/Documents/Harisankar/Projects/booking-platform/backend

# Commit the fix
git add core-monolith/requirements.txt
git commit -m "Clean requirements.txt - remove system packages"
git push origin main

#start command
uvicorn app.main:app --host 0.0.0.0 --port 9001