"""
telegram_fix.py — Drop-in replacement for Telegram notifications in agent.py
Fixes the async/threading issue that caused silent failures.
"""

import os
from dotenv import load_dotenv
load_dotenv()

import logging
import threading
import requests

logger = logging.getLogger(__name__)

TELEGRAM_ENABLED = os.environ.get("TELEGRAM_ENABLED", "false").lower() == "true"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ─── Core send function (pure requests, no async) ────────────────────────────

def send_telegram(message: str, parse_mode: str = "HTML") -> bool:
    """
    Send a Telegram message synchronously via HTTP.
    Returns True on success, False on failure.
    Safe to call from any thread or async context.
    """
    if not TELEGRAM_ENABLED:
        return False

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": parse_mode,
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("Telegram notification sent.")
            return True
        else:
            logger.error(f"Telegram API error {resp.status_code}: {resp.text}")
            return False
    except requests.exceptions.Timeout:
        logger.error("Telegram send timed out.")
        return False
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


def send_telegram_async(message: str):
    """
    Fire-and-forget: send Telegram message in a background thread.
    Use this in Flask routes / agent handlers so it never blocks.
    """
    t = threading.Thread(target=send_telegram, args=(message,), daemon=True)
    t.start()


# ─── Notification helpers ────────────────────────────────────────────────────

def notify_trend_found(product_name: str, trend_score: float, region: str = "India"):
    msg = (
        f"📈 <b>Trending Product Found!</b>\n\n"
        f"Product: <b>{product_name}</b>\n"
        f"Trend Score: {trend_score:.0f}/100\n"
        f"Region: {region}\n\n"
        f"🔗 Check dashboard for full analysis."
    )
    send_telegram_async(msg)


def notify_budget_approval(item: str, amount: float, level: str):
    emoji = "✅" if level == "auto" else "⏳"
    msg = (
        f"{emoji} <b>Budget {'Auto-Approved' if level == 'auto' else 'Pending Approval'}</b>\n\n"
        f"Item: {item}\n"
        f"Amount: ${amount:,.2f}\n"
        f"Approval level: {level}"
    )
    send_telegram_async(msg)


def notify_supplier_found(product: str, supplier: str, price: float):
    msg = (
        f"🏭 <b>Supplier Found</b>\n\n"
        f"Product: {product}\n"
        f"Supplier: {supplier}\n"
        f"Price: ${price:.2f}"
    )
    send_telegram_async(msg)


def notify_error(error_msg: str, context: str = ""):
    msg = (
        f"🚨 <b>DropShip Agent Error</b>\n\n"
        f"Context: {context}\n"
        f"Error: {error_msg}"
    )
    send_telegram_async(msg)


def notify_agent_started():
    msg = (
        "🚀 <b>DropShip AI Agent Started</b>\n\n"
        "All systems online. Ready for dropshipping intelligence.\n"
        "Track 3 (AlloyDB) active."
    )
    send_telegram_async(msg)


# ─── Test when run directly ──────────────────────────────────────────────────

if __name__ == "__main__":
    print("Sending test message to Telegram...")
    success = send_telegram(
        "🧪 <b>Test from DropShip Agent</b>\n\nTelegram notifications are working! 🎉"
    )
    print("Success!" if success else "Failed — check your token and chat ID.")
