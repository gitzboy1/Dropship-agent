from dotenv import load_dotenv
load_dotenv()

from google import genai
from browser_agent import run_product_research
import json
import asyncio
from datetime import datetime
from pytrends.request import TrendReq
import requests
import os
import uuid
import logging
import threading
import re
from database import db_manager
from telegram_fix import (
    notify_trend_found,
    notify_budget_approval,
    notify_supplier_found,
    notify_agent_started,
    notify_error,
    send_telegram_async,
)

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

session_store = {}


def _new_session_state(session_id=None):
    return {
        "budget": 0,
        "spent": 0,
        "approval_level": "confirm",
        "actions": [],
        "products_found": [],
        "conversation": [],
        "session_id": session_id or str(uuid.uuid4()),
    }


def get_session_data(session_id=None):
    key = session_id or "default"
    if key not in session_store:
        session_store[key] = _new_session_state(session_id)
    return session_store[key]


def _run_in_background(task, *args, **kwargs):
    def runner():
        try:
            task(*args, **kwargs)
        except Exception as exc:
            logger.warning("Background task failed: %s", exc)

    threading.Thread(target=runner, daemon=True).start()


def _persist_trending_products(products, geo):
    for product in products[:3]:
        db_manager.save_product({
            "name": product,
            "category": "Trending",
            "trend_score": 80.0,
            "research_data": {"source": "Google Trends", "geo": geo},
        })


def _persist_conversation(session_id, agent_type, message, response):
    db_manager.save_conversation(
        session_id=session_id,
        agent_type=agent_type,
        user_message=message,
        ai_response=response,
    )


def _persist_profile(session_id, amount, approval_level):
    db_manager.update_profile(session_id, {
        "budget_total": amount,
        "approval_level": approval_level,
    })

# ── Telegram (now uses telegram_fix — reliable, non-blocking) ─────────────────

def send_telegram(message):
    """Legacy wrapper — kept so existing calls in this file still work."""
    send_telegram_async(message)


# ── Google Trends ──────────────────────────────────────────────────────────────

def get_real_trends(keyword="dropshipping products", geo="IN"):
    if os.environ.get("ENABLE_PYTRENDS", "false").lower() != "true":
        fallback = {
            "IN": ["air purifier", "smart watch", "LED strip lights", "bluetooth earbuds", "yoga mat", "portable blender", "resistance bands", "laptop stand"],
            "US": ["stanley cup", "ring light", "posture corrector", "silk pillowcase", "portable charger", "car organizer", "face massager", "LED face mask"],
            "GB": ["heated gloves", "electric blanket", "air fryer accessories", "book light", "cord organizer", "smart plug", "phone stand", "reusable bags"]
        }
        return fallback.get(geo, fallback["IN"])
    try:
        pytrends = TrendReq(hl='en-US', tz=360)
        kw_list = [keyword, "online shopping", "ecommerce"]
        pytrends.build_payload(kw_list, cat=0, timeframe='now 7-d', geo=geo)
        data = pytrends.related_queries()
        trending = []
        for kw in kw_list:
            if kw in data and data[kw]['top'] is not None:
                top = data[kw]['top'].head(3)
                for _, row in top.iterrows():
                    trending.append(row['query'])
        if trending:
            return trending[:8]
    except:
        pass
    fallback = {
        "IN": ["air purifier", "smart watch", "LED strip lights", "bluetooth earbuds", "yoga mat", "portable blender", "resistance bands", "laptop stand"],
        "US": ["stanley cup", "ring light", "posture corrector", "silk pillowcase", "portable charger", "car organizer", "face massager", "LED face mask"],
        "GB": ["heated gloves", "electric blanket", "air fryer accessories", "book light", "cord organizer", "smart plug", "phone stand", "reusable bags"]
    }
    return fallback.get(geo, fallback["IN"])

def get_trending_products(region="IN", city=None):
    trends = get_real_trends(geo=region)
    city_boost = {
        "delhi": ["air purifier", "smart watch", "LED strip lights"],
        "mumbai": ["portable blender", "sunglasses", "phone stand"],
        "bangalore": ["mechanical keyboard", "webcam", "desk lamp"],
        "new york": ["stanley cup", "ring light", "posture corrector"],
        "london": ["heated gloves", "electric blanket", "book light"],
    }
    if city and city.lower() in city_boost:
        combined = city_boost[city.lower()] + [t for t in trends if t not in city_boost[city.lower()]]
        return combined[:8]
    return trends


# ── Finance helpers ────────────────────────────────────────────────────────────

def calculate_profit(cost_price, selling_price, units=1):
    profit_per_unit = selling_price - cost_price
    profit = profit_per_unit * units
    margin = ((selling_price - cost_price) / selling_price) * 100
    roi = ((selling_price - cost_price) / cost_price) * 100
    return {
        "cost_price": cost_price,
        "selling_price": selling_price,
        "profit_per_unit": round(profit_per_unit, 2),
        "profit_margin_percent": round(margin, 2),
        "roi_percent": round(roi, 2),
        "total_profit": round(profit * units, 2),
        "units": units,
        "verdict": "Excellent" if margin > 50 else "Good" if margin > 30 else "Risky" if margin > 15 else "Not recommended"
    }

def get_suppliers(product_name="general"):
    return [
        {"name": "AliExpress", "url": "https://aliexpress.com", "price_range": "₹150-400", "shipping_days": "15-30", "rating": 4.2, "moq": 1},
        {"name": "CJ Dropshipping", "url": "https://cjdropshipping.com", "price_range": "₹200-500", "shipping_days": "7-15", "rating": 4.5, "moq": 1},
        {"name": "Zendrop", "url": "https://zendrop.com", "price_range": "₹250-600", "shipping_days": "5-10", "rating": 4.7, "moq": 1},
        {"name": "Spocket", "url": "https://spocket.co", "price_range": "₹300-700", "shipping_days": "3-7", "rating": 4.6, "moq": 1},
    ]

def analyze_budget(session_state, budget, products=5):
    session_state["budget"] = budget
    per_product = budget / products
    return {
        "total_budget": budget,
        "products_to_test": products,
        "per_product_budget": round(per_product, 2),
        "allocation": {
            "inventory": round(per_product * 0.6, 2),
            "marketing": round(per_product * 0.3, 2),
            "reserve": round(per_product * 0.1, 2)
        },
        "recommendation": "Conservative — start with 2 products" if budget < 5000 else "Moderate — test 3-4 products" if budget < 15000 else "Aggressive — test 5+ products"
    }

def request_approval(session_state, action, amount, details):
    if session_state["approval_level"] == "auto":
        return True
    msg = f"""
<b>APPROVAL REQUIRED</b>

Action: {action}
Amount: ₹{amount}
Details: {details}

Reply YES to approve or NO to reject.
Your DropShip AI Agent is waiting...
    """
    send_telegram_async(msg)
    session_state["actions"].append({
        "action": action,
        "amount": amount,
        "details": details,
        "status": "pending",
        "time": datetime.now().isoformat()
    })
    return "pending"


# ── Context builder ────────────────────────────────────────────────────────────

def build_context(user_message, session_state):
    msg = user_message.lower()
    session_data = session_state
    context = f"""You are DropShip AI — an expert multi-agent dropshipping intelligence platform powered by Gemini 2.5, MCP tool orchestration, and real-time market data.

You have access to real tools: Google Trends data, supplier databases, profit calculators, budget managers, and Telegram notifications.

Current session:
- Budget set: ₹{session_data['budget']}
- Spent so far: ₹{session_data['spent']}
- Approval level: {session_data['approval_level']}
- Products found this session: {len(session_data['products_found'])}

"""
    if any(w in msg for w in ["trend", "trending", "popular", "hot", "sell", "what to sell", "product"]):
        geo = "US" if any(w in msg for w in ["us", "usa", "america", "american"]) else \
              "GB" if any(w in msg for w in ["uk", "britain", "england", "london"]) else "IN"
        city = None
        for c in ["delhi", "mumbai", "bangalore", "new york", "london", "chennai", "hyderabad"]:
            if c in msg:
                city = c
                break
        trends = get_trending_products(geo, city)
        context += f"REAL-TIME TRENDING PRODUCTS ({geo}{' - ' + city.title() if city else ''}): {json.dumps(trends)}\n\n"
        session_state["products_found"] = trends

        _run_in_background(_persist_trending_products, trends, geo)

        notify_trend_found(
            trends[0] if trends else "Unknown",
            80.0,
            f"{geo}{' - ' + city.title() if city else ''}"
        )

    if any(w in msg for w in ["supplier", "source", "vendor", "aliexpress", "cj"]):
        suppliers = get_suppliers()
        context += f"SUPPLIER DATABASE: {json.dumps(suppliers, indent=2)}\n\n"

    if any(w in msg for w in ["profit", "margin", "calculate", "earn", "roi", "revenue"]):
        context += "PROFIT CALCULATOR available. Extract cost and selling price from user message if mentioned. Formula: margin = (sell-cost)/sell*100\n\n"

    if any(w in msg for w in ["budget", "invest", "capital", "money", "rupee", "₹"]):
        numbers = [value for value in _extract_numbers(user_message) if value > 100]
        if numbers:
            budget_analysis = analyze_budget(session_state, numbers[0])
            context += f"BUDGET ANALYSIS: {json.dumps(budget_analysis, indent=2)}\n\n"

    if any(w in msg for w in ["approve", "permission", "gate", "confirm"]):
        context += f"APPROVAL SYSTEM: Current level is '{session_state['approval_level']}'. User can set to 'view', 'confirm', or 'auto'.\n\n"

    if any(w in msg for w in ["research", "investigate", "deep dive", "find product", "analyze product"]):
        for product in session_state.get("products_found", [])[:1]:
            research = run_product_research(product, GEMINI_API_KEY)
            context += f"PRODUCT RESEARCH REPORT: {json.dumps(research, indent=2)}\n\n"
            notify_supplier_found(product, "CJ Dropshipping", 0)
            break

    if any(w in msg for w in ["set budget", "my budget is", "i have"]):
        context += "Help user set their budget and configure approval level for actions.\n\n"

    context += f"\nUser: {user_message}\n\nRespond in a clear, structured way. Use bullet points for lists. Be specific with numbers. Always mention next steps."
    return context


def _extract_numbers(text):
    values = []
    for match in re.findall(r'[\d,]+', text):
        cleaned = match.replace(',', '')
        if cleaned.isdigit():
            values.append(int(cleaned))
    return values


def _format_currency(amount):
    return f"Rs {amount:,.0f}"


def _product_hint(product_name):
    hints = {
        "air purifier": "good for problem-solving marketing and metro-city demand",
        "smart watch": "works well for broad audiences and video ads",
        "LED strip lights": "strong visual appeal for impulse purchases",
        "bluetooth earbuds": "repeatable evergreen demand with many supplier options",
        "portable blender": "clear health and convenience angle",
        "ring light": "creator-focused demand and strong demo value",
    }
    return hints.get(product_name.lower(), "lightweight enough for fast testing and ad creatives")


def _build_rule_based_response(message, session_state, agent_type):
    msg = message.lower()

    if re.search(r"\b(hello|hi|hey)\b", msg):
        return (
            "I am ready to help you build a real dropshipping plan.\n"
            "- Ask for trending products in a country or city.\n"
            "- Ask me to calculate profit for a product.\n"
            "- Ask for a beginner roadmap if you want a full plan.\n"
            "Next step: try 'What are the trending products in India right now?'"
        )

    if any(word in msg for word in ["roadmap", "beginner", "start dropshipping", "how do i start"]):
        return (
            "Here is a practical beginner roadmap.\n"
            "1. Pick one simple category with visual products and low shipping risk.\n"
            "2. Validate 3 to 5 products with trend checks, supplier comparison, and margin math.\n"
            "3. Build one clean landing page for the strongest product instead of a huge catalog.\n"
            "4. Start with a strict test budget and track spend, clicks, and add-to-cart rate daily.\n"
            "5. Scale only the product that proves demand and margin.\n"
            "Next step: give me your budget and country, and I will turn this into a custom launch plan."
        )

    if any(word in msg for word in ["trend", "trending", "popular", "what to sell", "hot product"]):
        geo = "US" if any(word in msg for word in ["us", "usa", "america"]) else "GB" if any(word in msg for word in ["uk", "london", "britain"]) else "IN"
        city = None
        for candidate in ["delhi", "mumbai", "bangalore", "new york", "london", "chennai", "hyderabad"]:
            if candidate in msg:
                city = candidate
                break
        products = session_state.get("products_found") or get_trending_products(geo, city)
        session_state["products_found"] = products
        product_lines = "\n".join(
            f"- {product}: {_product_hint(product)}"
            for product in products[:5]
        )
        region_label = f"{geo} - {city.title()}" if city else geo
        return (
            f"Top products to test in {region_label} right now:\n"
            f"{product_lines}\n"
            "Next step: tell me one product from this list and I will break down supplier options, pricing, and margin."
        )

    if any(word in msg for word in ["supplier", "source", "vendor", "aliexpress", "cj"]):
        suppliers = get_suppliers()
        supplier_lines = "\n".join(
            f"- {supplier['name']}: shipping {supplier['shipping_days']}, rating {supplier['rating']}, typical price {supplier['price_range']}"
            for supplier in suppliers
        )
        return (
            "These are the best starting supplier options from the current setup:\n"
            f"{supplier_lines}\n"
            "Next step: tell me the product name and I will recommend the best supplier for speed versus margin."
        )

    if any(word in msg for word in ["profit", "margin", "roi", "calculate", "revenue"]):
        numbers = _extract_numbers(message)
        if len(numbers) >= 2:
            cost_price = numbers[0]
            selling_price = numbers[1]
            units = numbers[2] if len(numbers) >= 3 else 1
            analysis = calculate_profit(cost_price, selling_price, units)
            return (
                "Profit analysis:\n"
                f"- Cost price: {_format_currency(analysis['cost_price'])}\n"
                f"- Selling price: {_format_currency(analysis['selling_price'])}\n"
                f"- Profit per unit: {_format_currency(analysis['profit_per_unit'])}\n"
                f"- Total profit: {_format_currency(analysis['total_profit'])}\n"
                f"- Margin: {analysis['profit_margin_percent']}%\n"
                f"- ROI: {analysis['roi_percent']}%\n"
                f"- Verdict: {analysis['verdict']}\n"
                "Next step: if you want, I can also suggest an ad-testing budget for this product."
            )
        return (
            "Send me cost price, selling price, and optionally units.\n"
            "Example: 'Calculate profit for cost 250, selling 799, 40 units'."
        )

    if any(word in msg for word in ["budget", "invest", "capital", "money", "rupee"]):
        numbers = [value for value in _extract_numbers(message) if value > 100]
        if numbers:
            analysis = analyze_budget(session_state, numbers[0])
            return (
                "Budget plan:\n"
                f"- Total budget: {_format_currency(analysis['total_budget'])}\n"
                f"- Products to test: {analysis['products_to_test']}\n"
                f"- Budget per product: {_format_currency(analysis['per_product_budget'])}\n"
                f"- Inventory: {_format_currency(analysis['allocation']['inventory'])}\n"
                f"- Marketing: {_format_currency(analysis['allocation']['marketing'])}\n"
                f"- Reserve: {_format_currency(analysis['allocation']['reserve'])}\n"
                f"- Recommendation: {analysis['recommendation']}\n"
                "Next step: set approval mode to confirm or auto, then I can help you choose the first products to test."
            )
        return "Tell me your total budget and I will split it into testing, inventory, and reserve."

    if any(word in msg for word in ["research", "investigate", "deep dive", "analyze product"]):
        product_name = session_state.get("products_found", ["air purifier"])[0]
        report = run_product_research(product_name, GEMINI_API_KEY)
        return (
            f"Quick product research for {product_name}:\n"
            f"- Recommended selling price: {report['profit_analysis']['recommended_selling_price']}\n"
            f"- Profit margin: {report['profit_analysis']['profit_margin']}\n"
            f"- Profit per unit: {report['profit_analysis']['profit_per_unit']}\n"
            f"- Recommendation: {report['recommendation']}\n"
            "Next step: ask for supplier comparison or a store launch angle for this product."
        )

    return (
        "I can help with product research, supplier comparison, budget planning, and profit math.\n"
        "- Ask for trends in your target market.\n"
        "- Ask for a supplier comparison.\n"
        "- Ask for a beginner roadmap.\n"
        "Next step: tell me your country and budget, and I will suggest what to test first."
    )


# ── Multi-agent orchestrator ───────────────────────────────────────────────────

class MultiAgentOrchestrator:
    def __init__(self):
        self.agents = {
            "trend": self._trend_agent,
            "supplier": self._supplier_agent,
            "finance": self._finance_agent,
            "general": self._general_agent
        }

    def _detect_agent(self, message):
        msg = message.lower()
        if any(w in msg for w in ["trend", "trending", "popular", "hot product", "what to sell"]):
            return "trend"
        elif any(w in msg for w in ["supplier", "source", "vendor", "aliexpress"]):
            return "supplier"
        elif any(w in msg for w in ["profit", "margin", "budget", "invest", "roi", "calculate"]):
            return "finance"
        return "general"

    def _trend_agent(self, context):
        return client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"You are the Trend Specialist Agent. Your ONLY job is finding and analyzing trending products with market data.\n\n{context}"
        ).text

    def _supplier_agent(self, context):
        return client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"You are the Supplier Intelligence Agent. Your ONLY job is finding, vetting, and comparing suppliers.\n\n{context}"
        ).text

    def _finance_agent(self, context):
        return client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"You are the Finance & Profit Agent. Your ONLY job is analyzing profits, margins, ROI, and budget allocation.\n\n{context}"
        ).text

    def _general_agent(self, context):
        return client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"You are the DropShip AI general assistant. Help with dropshipping strategy, roadmaps, and general advice.\n\n{context}"
        ).text

    def _fallback_response(self, message, session_state, agent_type):
        return _build_rule_based_response(message, session_state, agent_type)

    def process(self, message, session_id=None):
        session_state = get_session_data(session_id)
        agent_type = self._detect_agent(message)
        context = build_context(message, session_state)
        if not client:
            response = self._fallback_response(message, session_state, agent_type)
        else:
            try:
                response = self.agents[agent_type](context)
            except Exception as e:
                logger.exception("Agent generation failed", exc_info=e)
                notify_error(str(e), f"{agent_type} agent request")
                response = self._fallback_response(message, session_state, agent_type)

        # Save conversation to AlloyDB (silent — never crashes the app)
        _run_in_background(
            _persist_conversation,
            session_state["session_id"],
            agent_type,
            message,
            response,
        )

        session_state["conversation"].append({
            "role": "user", "content": message,
            "agent": agent_type, "time": datetime.now().isoformat()
        })
        session_state["conversation"].append({
            "role": "assistant", "content": response,
            "agent": agent_type
        })
        session_state["conversation"] = session_state["conversation"][-20:]
        return response, agent_type


orchestrator = MultiAgentOrchestrator()

# Notify on startup (non-blocking)
notify_agent_started()


def get_agent_response(message, session_id=None):
    response, agent_type = orchestrator.process(message, session_id)
    return response, agent_type

def set_budget(amount, approval_level="confirm", session_id=None):
    session_state = get_session_data(session_id)
    session_state["budget"] = amount
    session_state["approval_level"] = approval_level

    _run_in_background(
        _persist_profile,
        session_state["session_id"],
        amount,
        approval_level,
    )

    notify_budget_approval("Budget configuration", amount, approval_level)
    return {"budget": amount, "approval_level": approval_level}
