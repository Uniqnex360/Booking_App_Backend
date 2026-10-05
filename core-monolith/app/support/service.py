import logging
import httpx
from typing import List, Optional
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

Tone & Style:
- Warm, polite, reassuring, and concise.
- Use clear bullet points for step-by-step instructions.
- Keep responses within 2 to 4 concise paragraphs or bullet points.
- If you cannot fully resolve an issue or if manual account intervention is required, invite the user to submit a support ticket using the 'New support ticket' button on the page.
"""

def get_knowledge_base_fallback(query: str, category: Optional[str] = None) -> str:
    q = (query or "").lower().strip()
    cat = (category or "").lower()

    if any(k in q for k in ["cancel", "cancellation", "exchange"]) or "cancel" in cat:
        return (
            "Here is how you can cancel your ticket on Vyhbz:\n\n"
            "1. Log in to your account and go to **Profile > Purchase History**.\n"
            "2. Select the booking you wish to cancel and click **Cancel Booking**.\n"
            "3. Review the refundable amount and confirm.\n\n"
            "• **Cut-off time:** Cancellation is allowed up to 2 hours before showtime (or cinema policy).\n"
            "• **Refund speed:** UPI/Wallets within 24-48 hrs; Cards within 5-7 business days.\n"
            "• Note: Live events and concerts are non-cancellable per organizer guidelines."
        )

    if any(k in q for k in ["refund", "money back", "deducted", "debited", "rrn"]) or "refund" in cat or "payment" in cat:
        return (
            "Here is the refund status guide for Vyhbz:\n\n"
            "• **UPI / Paytm / PhonePe:** Credited within 24 to 48 hours.\n"
            "• **Debit & Credit Cards:** Credited within 5 to 7 working days.\n"
            "• **Money debited without ticket?** This happens during banking network drops. Your bank will automatically reverse 100% of the funds within 2-4 business days.\n\n"
            "You can track the **Bank RRN number** under **Profile > Purchase History** to verify with your issuing bank."
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
    category: Optional[str] = None
) -> SupportChatResponse:
    openai_key = settings.OPENAI_API_KEY

    # If no key configured on Render yet, use smart local knowledge base
    if not openai_key or openai_key.strip() in ("", "your_openai_api_key_here"):
        logger.info("OPENAI_API_KEY not configured. Responding via Vyhbz Knowledge Base.")
        fallback = get_knowledge_base_fallback(message, category)
        return SupportChatResponse(reply=fallback, source="knowledge_base")

    # Format OpenAI conversation messages
    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
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
    fallback = get_knowledge_base_fallback(message, category)
    return SupportChatResponse(reply=fallback, source="knowledge_base")
