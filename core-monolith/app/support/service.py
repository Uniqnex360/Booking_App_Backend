import logging
import uuid
import json
import httpx
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.support.schemas import ChatMessageItem, SupportChatResponse

logger = logging.getLogger("support.service")

SYSTEM_PROMPT = """You are Vyhbz Support Assistant — the dedicated AI support representative for Vyhbz, a premier cinema and live entertainment booking platform in India (similar to BookMyShow).

Your role is to help users quickly and accurately with:
1. Movie Ticket Cancellations & Refunds:
   - Cancellation cutoff: Generally up to 2 hours before showtime (subject to exhibitor policy).
   - How to cancel: Log in -> Profile -> Purchase History -> Select booking -> Cancel Booking.
   - Refund timeline: UPI & Wallets within 24-48 hours. Credit/Debit cards within 5-7 working days.
   - Bank RRN (Refund Reference Number) is available in Purchase History for bank tracking.
   - Cancellation limit: Maximum 3 cancellations per calendar month per account.
2. Payment & Debit Issues:
   - If money is deducted but tickets were not generated due to a banking network glitch, banks automatically reverse 100% of the funds within 2-4 business days.
   - Advise users to check Profile -> Purchase History to verify if the booking exists.
3. Confirmation Not Received:
   - Users can open Profile -> Purchase History and click "Resend Confirmation" to immediately trigger fresh SMS and WhatsApp/Email delivery.
   - Showing the digital booking screen or QR code in Profile is 100% accepted at all cinema turnstiles.
4. Couple Recliner Seating:
   - Couple recliner loungers can only be reserved in pairs of 2.
5. 360° Auditorium View:
   - Users can preview the exact viewing angle from any seat (Silver front rows, Prime Plus center, Recliner elevated back rows) via the 360° Theatre View button on the seat map.
6. Live Events & Concerts:
   - Tickets for concerts, comedy shows, and sports are strictly non-cancellable unless the organizer officially cancels or reschedules the event.
7. Vyhbz Stream:
   - Digital rentals are accessible for 30 days, or 48 hours once playback starts. Non-refundable once streamed.
8. Personalized Customer Bookings:
   - When [Customer Context] is provided below, reference their specific bookings, showtimes, seats, and booking reference codes accurately when asked (e.g. "What is my booking?", "Where are my tickets?", "What seats do I have?").
   - If user asks to cancel an active booking, state whether it is eligible and remind them they can tap Profile -> Purchase History -> Cancel Booking.
   - If [Customer Context] indicates "Authentication: Guest (Not logged in)" and user asks about their booking or tickets, politely guide them to log in to their Vyhbz account so their bookings can be retrieved.

Tone & Style:
- Warm, polite, reassuring, and concise.
- Use clear bullet points for step-by-step instructions.
- Keep responses within 2 to 4 concise paragraphs or bullet points.
- If you cannot fully resolve an issue or if manual account intervention is required, invite the user to submit a support ticket using the 'New support ticket' button on the page.
"""

async def get_user_recent_bookings(db: AsyncSession, user_id: uuid.UUID, limit: int = 5) -> List[dict]:
    """
    Fetches enriched recent bookings for the authenticated user (movies and live events).
    """
    from sqlalchemy import select
    from app.booking.models import BookingModel
    from app.movie.models import Showtime, Movie, Screen, Venue
    from app.event.models import EventORM, TicketCategoryORM

    stmt = (
        select(
            BookingModel,
            Showtime,
            Movie,
            Screen,
            Venue,
            EventORM,
            TicketCategoryORM,
        )
        .outerjoin(Showtime, BookingModel.showtime_id == Showtime.id)
        .outerjoin(Movie, Showtime.movie_id == Movie.id)
        .outerjoin(Screen, Showtime.screen_id == Screen.id)
        .outerjoin(Venue, Screen.venue_id == Venue.id)
        .outerjoin(EventORM, BookingModel.event_id == EventORM.id)
        .outerjoin(TicketCategoryORM, BookingModel.tier_id == TicketCategoryORM.id)
        .where(BookingModel.user_id == user_id)
        .order_by(BookingModel.created_at.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    rows = res.all()

    enriched_bookings = []
    for b, st, movie, screen, venue, event, tier in rows:
        seat_codes: List[str] = []
        raw = b.seat_codes_json or b.seat_refs_json
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    seat_codes = [str(x) for x in parsed]
            except Exception:
                seat_codes = []

        if movie:
            title = movie.title
            booking_type = "MOVIE"
            venue_name = f"{venue.name} • {screen.name}" if (venue and screen) else (venue.name if venue else "Cinema Hall")
            location = venue.city if venue else "Kochi"
            show_date = st.starts_at.strftime("%d %b %Y, %I:%M %p") if st and st.starts_at else (b.created_at.strftime("%d %b %Y") if b.created_at else "N/A")
            quantity = len(seat_codes) if seat_codes else (b.quantity or 1)
        elif event:
            title = event.title
            booking_type = "EVENT"
            venue_name = event.venue_name or "Event Venue"
            location = event.venue_address or event.city or "Kochi"
            show_date = event.starts_at.strftime("%d %b %Y, %I:%M %p") if event and event.starts_at else (b.created_at.strftime("%d %b %Y") if b.created_at else "N/A")
            quantity = b.quantity or 1
        else:
            title = "Cinema Booking" if b.booking_type == "MOVIE" else "Experience Booking"
            booking_type = b.booking_type or "BOOKING"
            venue_name = "PVR Cinemas" if b.provider_id else "Venue"
            location = "Kochi"
            show_date = b.created_at.strftime("%d %b %Y") if b.created_at else "N/A"
            quantity = b.quantity or 1

        total_rupees = (b.total_paise // 100) if b.total_paise is not None else 0

        enriched_bookings.append({
            "id": str(b.id),
            "ref_code": b.ref_code or str(b.id)[:8].upper(),
            "type": booking_type,
            "title": title,
            "venue": venue_name,
            "location": location,
            "date": show_date,
            "seats": seat_codes,
            "quantity": quantity,
            "total_rupees": total_rupees,
            "status": b.status or "CONFIRMED",
        })

    return enriched_bookings

def get_knowledge_base_fallback(
    query: str,
    category: Optional[str] = None,
    user_name: Optional[str] = None,
    user_bookings: Optional[List[dict]] = None,
) -> str:
    q = (query or "").lower().strip()
    cat = (category or "").lower()

    # 1. Personalized Booking / Ticket Inquiries
    is_personal_booking_query = (
        any(k in q for k in [
            "my booking", "my ticket", "my reservation", "what did i book",
            "show my ticket", "last booking", "recent booking", "active booking",
            "my shows", "my seats", "which seat", "ticket status", "booking status"
        ])
        or ("booking" in q and any(k in q for k in ["my", "show", "recent", "list", "status", "detail"]))
    )

    if is_personal_booking_query:
        if user_bookings is None:
            return (
                "To view your bookings and tickets, please **log in** to your Vyhbz account.\n\n"
                "Once logged in, your active tickets, QR codes, and purchase history will be accessible right here and under **Profile > Purchase History**!"
            )
        elif len(user_bookings) == 0:
            return (
                f"Hi {user_name or 'there'}, you don't have any bookings in your Vyhbz account yet.\n\n"
                "Once you reserve movie tickets or live events, your booking confirmations, seat numbers, and QR tickets will appear right here and under **Profile > Purchase History**!"
            )
        else:
            # Check if asking specifically about seats
            if any(k in q for k in ["seat", "seats"]):
                latest = user_bookings[0]
                seats_display = ", ".join(latest.get("seats", [])) or f"{latest.get('quantity', 1)} ticket(s)"
                return (
                    f"Here are the seat details for your latest booking:\n\n"
                    f"🎬 **{latest['title']}**\n"
                    f"• **Seats / Tickets:** {seats_display}\n"
                    f"• **Venue:** {latest['venue']}, {latest['location']}\n"
                    f"• **Date / Time:** {latest['date']}\n"
                    f"• **Booking Ref:** `{latest['ref_code']}`\n"
                    f"• **Status:** {latest['status']}\n\n"
                    f"You can view your QR ticket anytime under **Profile > Purchase History**."
                )

            # General listing of recent bookings
            lines = [f"Hi {user_name or 'there'}! Here are your recent bookings on Vyhbz:\n"]
            for idx, b in enumerate(user_bookings[:3], 1):
                icon = "🎬" if b.get("type") == "MOVIE" else "🎟️"
                seats_info = f", Seats: {', '.join(b['seats'])}" if b.get("seats") else f", Qty: {b.get('quantity', 1)}"
                lines.append(
                    f"{icon} **{idx}. {b['title']}** ({b['status']})\n"
                    f"• **Booking Ref:** `{b['ref_code']}`\n"
                    f"• **Date:** {b['date']}\n"
                    f"• **Venue:** {b['venue']}, {b['location']}{seats_info}\n"
                    f"• **Total Paid:** ₹{b['total_rupees']}\n"
                )
            lines.append("• Need to download an invoice or cancel? Visit **Profile > Purchase History**.")
            return "\n".join(lines)

    # 2. Cancellations & Exchange
    if any(k in q for k in ["cancel", "cancellation", "exchange"]) or "cancel" in cat:
        # If user has a confirmed booking, offer helpful context
        extra_note = ""
        if user_bookings and len(user_bookings) > 0:
            latest = user_bookings[0]
            if latest.get("status") == "CONFIRMED":
                extra_note = f"\n\n*Note for your booking **{latest['title']}** (Ref: `{latest['ref_code']}`): You can cancel this directly under Profile > Purchase History up to 2 hours before showtime.*"

        return (
            "Here is how you can cancel your ticket on Vyhbz:\n\n"
            "1. Log in to your account and go to **Profile > Purchase History**.\n"
            "2. Select the booking you wish to cancel and click **Cancel Booking**.\n"
            "3. Review the refundable amount and confirm.\n\n"
            "• **Cut-off time:** Cancellation is allowed up to 2 hours before showtime (or cinema policy).\n"
            "• **Refund speed:** UPI/Wallets within 24-48 hrs; Cards within 5-7 business days.\n"
            "• Note: Live events and concerts are non-cancellable per organizer guidelines."
            f"{extra_note}"
        )

    # 3. Refunds & Payments
    if any(k in q for k in ["refund", "money back", "deducted", "debited", "rrn"]) or "refund" in cat or "payment" in cat:
        cancelled_booking = None
        if user_bookings:
            for b in user_bookings:
                if b.get("status") == "CANCELLED":
                    cancelled_booking = b
                    break

        refund_context = ""
        if cancelled_booking:
            refund_context = (
                f"\n\n💡 *Regarding your cancelled booking for **{cancelled_booking['title']}** (Ref: `{cancelled_booking['ref_code']}`):*\n"
                f"Your refund of ₹{cancelled_booking['total_rupees']} is being processed by the payment gateway."
            )

        return (
            "Here is the refund status guide for Vyhbz:\n\n"
            "• **UPI / Paytm / PhonePe:** Credited within 24 to 48 hours.\n"
            "• **Debit & Credit Cards:** Credited within 5 to 7 working days.\n"
            "• **Money debited without ticket?** This happens during banking network drops. Your bank will automatically reverse 100% of the funds within 2-4 business days.\n\n"
            "You can track the **Bank RRN number** under **Profile > Purchase History** to verify with your issuing bank."
            f"{refund_context}"
        )

    if any(k in q for k in ["confirmation", "sms", "email", "whatsapp", "ticket not received"]) or "confirm" in cat:
        return (
            "Did not receive your confirmation SMS or Email?\n\n"
            "1. Go to **Profile > Purchase History** on Vyhbz.\n"
            "2. Your confirmed ticket with QR code is always saved there — you can show this screen directly at the theater gate.\n"
            "3. Click **Resend Confirmation** to receive a fresh SMS and WhatsApp message instantly."
        )

    if any(k in q for k in ["couple", "pair", "recliner", "two seats"]):
        return (
            "**Couple Recliner Policy:**\n\n"
            "Couple Recliner loungers are designed as paired seating and can only be booked in pairs of 2.\n"
            "If you select one couple seat, its adjacent partner seat will be automatically included in your selection."
        )

    if any(k in q for k in ["360", "angle", "view", "perspective", "seat view", "screen"]):
        return (
            "**360° Auditorium Seat View:**\n\n"
            "You can preview the exact view of the screen from every tier:\n"
            "• **Silver:** Front rows directly under the towering screen (elevated upward pitch).\n"
            "• **Prime Plus:** Center rows at eye-level sweet spot.\n"
            "• **Recliner:** Elevated back rows with full auditorium panoramic view.\n\n"
            "Simply click the **360° Theatre View** button on the seat map!"
        )

    if any(k in q for k in ["offer", "promo", "coupon", "discount"]):
        return (
            "**Applying Offers & Promocodes:**\n\n"
            "On the payment checkout screen, expand the **Unlock Offers or Apply Promocodes** section.\n"
            "Enter your promo code (e.g. `VYHBZ20`) or select eligible credit/debit card offers to apply instant discounts."
        )

    return (
        "I'm here to help with your Vyhbz booking, ticket cancellation, refund status, and cinema queries!\n\n"
        "• For quick help, check **Profile > Purchase History** to manage bookings and track refunds.\n"
        "• If you have an urgent inquiry, you can also submit a support ticket using the **+ New support ticket** button above."
    )

async def generate_support_reply(
    message: str,
    history: List[ChatMessageItem],
    category: Optional[str] = None,
    user_name: Optional[str] = None,
    user_email: Optional[str] = None,
    user_bookings: Optional[List[dict]] = None,
) -> SupportChatResponse:
    openai_key = settings.OPENAI_API_KEY

    # Build customer context summary
    context_lines = []
    if user_name:
        context_lines.append(f"Customer Name: {user_name}")
    if user_email:
        context_lines.append(f"Customer Email: {user_email}")
    if user_bookings is not None:
        if len(user_bookings) == 0:
            context_lines.append("Recent Bookings: None found (User has 0 past or active bookings).")
        else:
            context_lines.append(f"Recent Bookings ({len(user_bookings)}):")
            for idx, b in enumerate(user_bookings, 1):
                seats_str = f", Seats: {', '.join(b['seats'])}" if b.get('seats') else f", Quantity: {b.get('quantity', 1)}"
                context_lines.append(
                    f"{idx}. [{b.get('type')}] \"{b.get('title')}\" - Status: {b.get('status')} | "
                    f"Ref Code: {b.get('ref_code')} | Show Date: {b.get('date')} | "
                    f"Venue: {b.get('venue')}, {b.get('location')}{seats_str} | Paid: ₹{b.get('total_rupees')}"
                )
    else:
        context_lines.append("Authentication: Guest (Not logged in).")

    customer_context_str = "\n".join(context_lines)

    # If no key configured on Render yet, use smart local knowledge base
    if not openai_key or openai_key.strip() in ("", "your_openai_api_key_here"):
        logger.info("OPENAI_API_KEY not configured. Responding via Vyhbz Knowledge Base.")
        fallback = get_knowledge_base_fallback(
            message,
            category,
            user_name=user_name,
            user_bookings=user_bookings,
        )
        return SupportChatResponse(reply=fallback, source="knowledge_base")

    # Format OpenAI conversation messages
    api_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"[Customer Context]\n{customer_context_str}"},
    ]

    # Append recent conversation history (max 8 messages for context)
    for h in history[-8:]:
        if h.role in ("user", "assistant") and h.content:
            api_messages.append({"role": h.role, "content": h.content})

    user_prompt = message
    if category:
        user_prompt = f"[User Topic: {category}]\n{message}"
    api_messages.append({"role": "user", "content": user_prompt})

    try:
        async with httpx.AsyncClient(timeout=18.0) as client:
            res = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {openai_key}",
                },
                json={
                    "model": settings.OPENAI_MODEL or "gpt-4o-mini",
                    "messages": api_messages,
                    "max_tokens": 500,
                    "temperature": 0.6,
                },
            )

            if res.status_code == 200:
                data = res.json()
                reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if reply:
                    return SupportChatResponse(reply=reply.strip(), source="ai")

            logger.warning(f"OpenAI API non-200 response ({res.status_code}): {res.text}")
    except Exception as e:
        logger.error(f"Error calling OpenAI API: {e}", exc_info=True)

    # Seamless fallback on any network error or quota limits
    fallback = get_knowledge_base_fallback(
        message,
        category,
        user_name=user_name,
        user_bookings=user_bookings,
    )
    return SupportChatResponse(reply=fallback, source="knowledge_base")

