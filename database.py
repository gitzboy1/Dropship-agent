"""
database.py — AlloyDB integration for DropShip AI Agent
Handles conversations, products, user profiles, and vector search
"""

import os
import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional, List, Dict, Any

# SQLAlchemy
from sqlalchemy import create_engine, text, Column, String, Float, DateTime, Text, Integer, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid

logger = logging.getLogger(__name__)

Base = declarative_base()

# ─── ORM Models ──────────────────────────────────────────────────────────────

class Conversation(Base):
    __tablename__ = "conversations"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id   = Column(String(100), nullable=False, index=True)
    agent_type   = Column(String(50))          # trend / supplier / finance / general
    user_message = Column(Text)
    ai_response  = Column(Text)
    tokens_used  = Column(Integer, default=0)
    created_at   = Column(DateTime, default=datetime.utcnow)
    extra_data   = Column(JSONB, default={})


class Product(Base):
    __tablename__ = "products"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name            = Column(String(255), nullable=False)
    category        = Column(String(100))
    supplier_url    = Column(Text)
    cost_price      = Column(Float)
    selling_price   = Column(Float)
    profit_margin   = Column(Float)
    trend_score     = Column(Float)            # 0-100 from Google Trends
    is_active       = Column(Boolean, default=True)
    research_data   = Column(JSONB, default={})  # raw research dump
    embedding       = Column(Text)             # JSON-serialised float list for pgvector
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id     = Column(String(100), unique=True, nullable=False)
    budget_total   = Column(Float, default=10000.0)
    budget_spent   = Column(Float, default=0.0)
    approval_level = Column(String(20), default="confirm")  # view / confirm / auto
    preferences    = Column(JSONB, default={})
    created_at     = Column(DateTime, default=datetime.utcnow)
    last_active    = Column(DateTime, default=datetime.utcnow)


class BudgetTransaction(Base):
    __tablename__ = "budget_transactions"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id  = Column(String(100), nullable=False, index=True)
    amount      = Column(Float, nullable=False)
    category    = Column(String(100))
    description = Column(Text)
    approved    = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=datetime.utcnow)


# ─── Database Manager ────────────────────────────────────────────────────────

class DatabaseManager:
    """
    Manages AlloyDB connection and all DB operations.
    Connection string comes from env vars; falls back gracefully if DB is unavailable.
    """

    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._connected = False
        self._last_init_attempt = 0.0
        self._init_backoff_seconds = 30
        self._connect_timeout_seconds = int(os.environ.get("DB_CONNECT_TIMEOUT", "5"))
        self._auto_create_schema = os.environ.get("AUTO_CREATE_DB_SCHEMA", "false").lower() == "true"

    def _build_connection_string(self) -> Optional[str]:
        """Build PostgreSQL connection string from environment variables."""
        host     = os.environ.get("ALLOYDB_HOST")
        port     = os.environ.get("ALLOYDB_PORT", "5432")
        database = os.environ.get("ALLOYDB_DATABASE", "dropship_db")
        user     = os.environ.get("ALLOYDB_USER", "postgres")
        password = os.environ.get("ALLOYDB_PASSWORD")

        if not host or not password:
            logger.warning("AlloyDB credentials not set — running without database.")
            return None

        return f"postgresql+pg8000://{user}:{password}@{host}:{port}/{database}"

    def _init_db(self):
        conn_str = self._build_connection_string()
        if not conn_str:
            return False

        try:
            self.engine = create_engine(
                conn_str,
                pool_size=5,
                max_overflow=10,
                pool_timeout=5,
                pool_recycle=1800,
                pool_pre_ping=True,
                connect_args={"ssl_context": None},   # PSC — no TLS needed inside VPC
            )
            self.SessionLocal = sessionmaker(bind=self.engine)
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            if self._auto_create_schema:
                self._create_tables()
            self._connected = True
            logger.info("AlloyDB connected successfully.")
            return True
        except Exception as e:
            logger.error(f"AlloyDB connection failed: {e}")
            self.engine = None
            self.SessionLocal = None
            self._connected = False
            return False

    def _create_tables(self):
        """Create all tables and enable pgvector extension."""
        with self.engine.connect() as conn:
            # Enable pgvector (safe to run multiple times)
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()

        Base.metadata.create_all(self.engine)

        # Add vector column separately if it doesn't exist
        # (SQLAlchemy can't natively handle vector type)
        with self.engine.connect() as conn:
            try:
                conn.execute(text(
                    "ALTER TABLE products ADD COLUMN IF NOT EXISTS "
                    "product_embedding vector(768);"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS products_embedding_idx "
                    "ON products USING ivfflat (product_embedding vector_cosine_ops) "
                    "WITH (lists = 100);"
                ))
                conn.commit()
            except Exception as e:
                logger.warning(f"Vector column setup: {e}")

    def _ensure_initialized(self, force: bool = False) -> bool:
        if self._connected and self.engine and self.SessionLocal:
            return True

        now = time.monotonic()
        if not force and self._last_init_attempt and now - self._last_init_attempt < self._init_backoff_seconds:
            return False

        self._last_init_attempt = now
        return bool(self._init_db())

    def _mark_unavailable(self, error: Exception):
        logger.error(f"Database unavailable: {error}")
        self._connected = False
        self.engine = None
        self.SessionLocal = None

    def get_session(self) -> Optional[Session]:
        if not self._ensure_initialized():
            return None
        return self.SessionLocal()

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Conversations ────────────────────────────────────────────────────────

    def save_conversation(
        self,
        session_id: str,
        agent_type: str,
        user_message: str,
        ai_response: str,
        tokens_used: int = 0,
        extra_data: dict = None,
    ) -> Optional[str]:
        db = self.get_session()
        if not db:
            return None
        try:
            conv = Conversation(
                session_id=session_id,
                agent_type=agent_type,
                user_message=user_message,
                ai_response=ai_response,
                tokens_used=tokens_used,
                extra_data=extra_data or {},
            )
            db.add(conv)
            db.commit()
            db.refresh(conv)
            return str(conv.id)
        except Exception as e:
            db.rollback()
            self._mark_unavailable(e)
            return None
        finally:
            db.close()

    def get_conversation_history(
        self, session_id: str, limit: int = 20
    ) -> List[Dict]:
        db = self.get_session()
        if not db:
            return []
        try:
            rows = (
                db.query(Conversation)
                .filter(Conversation.session_id == session_id)
                .order_by(Conversation.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": str(r.id),
                    "agent_type": r.agent_type,
                    "user_message": r.user_message,
                    "ai_response": r.ai_response,
                    "created_at": r.created_at.isoformat(),
                }
                for r in reversed(rows)
            ]
        except Exception as e:
            self._mark_unavailable(e)
            return []
        finally:
            db.close()

    # ── Products ─────────────────────────────────────────────────────────────

    def save_product(self, product_data: Dict[str, Any]) -> Optional[str]:
        db = self.get_session()
        if not db:
            return None
        try:
            # Calculate profit margin if prices are present
            cost   = product_data.get("cost_price", 0)
            sell   = product_data.get("selling_price", 0)
            margin = ((sell - cost) / sell * 100) if sell > 0 else 0

            product = Product(
                name=product_data.get("name", "Unknown"),
                category=product_data.get("category", "General"),
                supplier_url=product_data.get("supplier_url", ""),
                cost_price=cost,
                selling_price=sell,
                profit_margin=round(margin, 2),
                trend_score=product_data.get("trend_score", 0),
                research_data=product_data.get("research_data", {}),
            )
            db.add(product)
            db.commit()
            db.refresh(product)
            logger.info(f"Saved product: {product.name} (id={product.id})")
            return str(product.id)
        except Exception as e:
            db.rollback()
            self._mark_unavailable(e)
            return None
        finally:
            db.close()

    def get_products(
        self,
        category: str = None,
        min_margin: float = None,
        limit: int = 50,
    ) -> List[Dict]:
        db = self.get_session()
        if not db:
            return []
        try:
            q = db.query(Product).filter(Product.is_active == True)
            if category:
                q = q.filter(Product.category.ilike(f"%{category}%"))
            if min_margin is not None:
                q = q.filter(Product.profit_margin >= min_margin)
            rows = q.order_by(Product.trend_score.desc()).limit(limit).all()
            return [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "category": r.category,
                    "cost_price": r.cost_price,
                    "selling_price": r.selling_price,
                    "profit_margin": r.profit_margin,
                    "trend_score": r.trend_score,
                    "supplier_url": r.supplier_url,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]
        except Exception as e:
            self._mark_unavailable(e)
            return []
        finally:
            db.close()

    def find_similar_products(
        self, query_embedding: List[float], limit: int = 5
    ) -> List[Dict]:
        """Vector similarity search using pgvector cosine distance."""
        db = self.get_session()
        if not db:
            return []
        try:
            vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
            result = db.execute(
                text(
                    "SELECT id, name, category, profit_margin, trend_score, "
                    "1 - (product_embedding <=> :vec) AS similarity "
                    "FROM products "
                    "WHERE product_embedding IS NOT NULL AND is_active = TRUE "
                    "ORDER BY product_embedding <=> :vec "
                    "LIMIT :limit"
                ),
                {"vec": vec_str, "limit": limit},
            )
            return [
                {
                    "id": str(row.id),
                    "name": row.name,
                    "category": row.category,
                    "profit_margin": row.profit_margin,
                    "trend_score": row.trend_score,
                    "similarity": round(float(row.similarity), 3),
                }
                for row in result
            ]
        except Exception as e:
            self._mark_unavailable(e)
            return []
        finally:
            db.close()

    # ── User Profiles ─────────────────────────────────────────────────────────

    def get_or_create_profile(self, session_id: str) -> Dict:
        db = self.get_session()
        if not db:
            return {"session_id": session_id, "budget_total": 10000, "budget_spent": 0}
        try:
            profile = (
                db.query(UserProfile)
                .filter(UserProfile.session_id == session_id)
                .first()
            )
            if not profile:
                profile = UserProfile(session_id=session_id)
                db.add(profile)
                db.commit()
                db.refresh(profile)
            return {
                "session_id": profile.session_id,
                "budget_total": profile.budget_total,
                "budget_spent": profile.budget_spent,
                "approval_level": profile.approval_level,
                "preferences": profile.preferences,
            }
        except Exception as e:
            db.rollback()
            self._mark_unavailable(e)
            return {"session_id": session_id, "budget_total": 10000, "budget_spent": 0}
        finally:
            db.close()

    def update_profile(self, session_id: str, updates: Dict) -> bool:
        db = self.get_session()
        if not db:
            return False
        try:
            profile = (
                db.query(UserProfile)
                .filter(UserProfile.session_id == session_id)
                .first()
            )
            if not profile:
                profile = UserProfile(session_id=session_id)
                db.add(profile)
            for key, value in updates.items():
                if hasattr(profile, key):
                    setattr(profile, key, value)
            profile.last_active = datetime.utcnow()
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            self._mark_unavailable(e)
            return False
        finally:
            db.close()

    # ── Budget Transactions ───────────────────────────────────────────────────

    def log_transaction(
        self,
        session_id: str,
        amount: float,
        category: str,
        description: str,
        approved: bool = False,
    ) -> Optional[str]:
        db = self.get_session()
        if not db:
            return None
        try:
            tx = BudgetTransaction(
                session_id=session_id,
                amount=amount,
                category=category,
                description=description,
                approved=approved,
            )
            db.add(tx)
            if approved:
                # Update spent amount on profile
                profile = (
                    db.query(UserProfile)
                    .filter(UserProfile.session_id == session_id)
                    .first()
                )
                if profile:
                    profile.budget_spent = (profile.budget_spent or 0) + amount
            db.commit()
            db.refresh(tx)
            return str(tx.id)
        except Exception as e:
            db.rollback()
            self._mark_unavailable(e)
            return None
        finally:
            db.close()

    def get_transactions(self, session_id: str, limit: int = 50) -> List[Dict]:
        db = self.get_session()
        if not db:
            return []
        try:
            rows = (
                db.query(BudgetTransaction)
                .filter(BudgetTransaction.session_id == session_id)
                .order_by(BudgetTransaction.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": str(r.id),
                    "amount": r.amount,
                    "category": r.category,
                    "description": r.description,
                    "approved": r.approved,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]
        except Exception as e:
            self._mark_unavailable(e)
            return []
        finally:
            db.close()

    # ── Health Check ─────────────────────────────────────────────────────────

    def health_check(self) -> Dict:
        if not self._ensure_initialized():
            return {"status": "disconnected", "message": "Database unavailable"}
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM conversations"))
                count = result.scalar()
            return {"status": "healthy", "conversations": count}
        except Exception as e:
            self._mark_unavailable(e)
            return {"status": "error", "message": str(e)}


# ─── Singleton ───────────────────────────────────────────────────────────────

db_manager = DatabaseManager()
