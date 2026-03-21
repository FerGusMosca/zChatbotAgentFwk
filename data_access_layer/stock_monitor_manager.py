# stock_monitor_manager.py — v3
import pyodbc
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass
class Portfolio:
    id: int; name: str; description: Optional[str]
    created_at: datetime; updated_at: datetime

@dataclass
class PortfolioAsset:
    id: int; portfolio_id: int; symbol: str; added_at: datetime

@dataclass
class AssetComment:
    id: int; portfolio_id: int; symbol: str; comment: str; created_at: datetime

@dataclass
class AssetNote:
    id: int; portfolio_id: int; symbol: str
    note: str; priority: str; notify: bool; created_at: datetime

@dataclass
class ResearchTopic:
    id: int; portfolio_id: int; name: str; created_at: datetime

@dataclass
class ResearchRow:
    id: int; topic_id: int; symbol: str
    news: Optional[str]            = None
    gpa_ratio: Optional[Decimal]   = None
    pe_ratio: Optional[Decimal]    = None
    debt_ratio: Optional[Decimal]  = None
    ta_situation: Optional[str]    = None
    mgmt_sentiment: Optional[str]  = None
    earnings: Optional[str]        = None
    conclusion: Optional[str]      = None
    latest_comments: Optional[str] = None
    updated_at: Optional[datetime] = None

@dataclass
class PortfolioEmail:
    id: int; portfolio_id: int; email: str
    name: Optional[str]; added_at: datetime


class StockMonitorManager:

    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    def _connect(self): return pyodbc.connect(self.connection_string)

    # ── Portfolios ───────────────────────────────────────────
    def get_portfolios(self):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_get_portfolios"); rows = cur.fetchall()
        cur.close(); conn.close()
        return [Portfolio(id=r.id, name=r.name, description=r.description,
                          created_at=r.created_at, updated_at=r.updated_at) for r in rows]

    def create_portfolio(self, name, description=None):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_create_portfolio @name=?, @description=?", name, description)
        row = cur.fetchone(); conn.commit(); cur.close(); conn.close(); return int(row.id)

    def update_portfolio(self, id, name, description=None):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_update_portfolio @id=?, @name=?, @description=?", id, name, description)
        conn.commit(); cur.close(); conn.close()

    def delete_portfolio(self, id):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_delete_portfolio @id=?", id)
        conn.commit(); cur.close(); conn.close()

    # ── Assets ───────────────────────────────────────────────
    def get_assets(self, portfolio_id):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_get_assets @portfolio_id=?", portfolio_id)
        rows = cur.fetchall(); cur.close(); conn.close()
        return [PortfolioAsset(id=r.id, portfolio_id=r.portfolio_id,
                               symbol=r.symbol, added_at=r.added_at) for r in rows]

    def add_asset(self, portfolio_id, symbol):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_add_asset @portfolio_id=?, @symbol=?",
                    portfolio_id, symbol.upper().strip())
        row = cur.fetchone(); conn.commit(); cur.close(); conn.close()
        return PortfolioAsset(id=row.id, portfolio_id=row.portfolio_id,
                              symbol=row.symbol, added_at=row.added_at)

    def add_assets_bulk(self, portfolio_id, symbols):
        return [self.add_asset(portfolio_id, s) for s in symbols if s.strip()]

    def remove_asset(self, portfolio_id, symbol):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_remove_asset @portfolio_id=?, @symbol=?",
                    portfolio_id, symbol.upper().strip())
        conn.commit(); cur.close(); conn.close()

    # ── Comments ─────────────────────────────────────────────
    def get_comments(self, portfolio_id, symbol):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_get_comments @portfolio_id=?, @symbol=?",
                    portfolio_id, symbol.upper().strip())
        rows = cur.fetchall(); cur.close(); conn.close()
        return [AssetComment(id=r.id, portfolio_id=r.portfolio_id, symbol=r.symbol,
                             comment=r.comment, created_at=r.created_at) for r in rows]

    def add_comment(self, portfolio_id, symbol, comment):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_add_comment @portfolio_id=?, @symbol=?, @comment=?",
                    portfolio_id, symbol.upper().strip(), comment.strip())
        row = cur.fetchone(); conn.commit(); cur.close(); conn.close(); return int(row.id)

    def delete_comment(self, comment_id):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_delete_comment @id=?", comment_id)
        conn.commit(); cur.close(); conn.close()

    # ── Asset Notes ──────────────────────────────────────────
    def get_asset_notes(self, portfolio_id, symbol):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_get_asset_notes @portfolio_id=?, @symbol=?",
                    portfolio_id, symbol.upper().strip())
        rows = cur.fetchall(); cur.close(); conn.close()
        return [AssetNote(id=r.id, portfolio_id=r.portfolio_id, symbol=r.symbol,
                          note=r.note, priority=r.priority,
                          notify=bool(r.notify), created_at=r.created_at) for r in rows]

    def add_asset_note(self, portfolio_id, symbol, note, priority='green', notify=False):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_add_asset_note @portfolio_id=?, @symbol=?, @note=?, @priority=?, @notify=?",
                    portfolio_id, symbol.upper().strip(), note.strip(), priority, 1 if notify else 0)
        row = cur.fetchone(); conn.commit(); cur.close(); conn.close(); return int(row.id)

    def delete_asset_note(self, note_id):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_delete_asset_note @id=?", note_id)
        conn.commit(); cur.close(); conn.close()

    # ── Research Topics ──────────────────────────────────────
    def get_research_topics(self, portfolio_id):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_get_research_topics @portfolio_id=?", portfolio_id)
        rows = cur.fetchall(); cur.close(); conn.close()
        return [ResearchTopic(id=r.id, portfolio_id=r.portfolio_id,
                              name=r.name, created_at=r.created_at) for r in rows]

    def create_research_topic(self, portfolio_id, name):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_create_research_topic @portfolio_id=?, @name=?",
                    portfolio_id, name.strip())
        row = cur.fetchone(); conn.commit(); cur.close(); conn.close()
        return ResearchTopic(id=row.id, portfolio_id=row.portfolio_id,
                             name=row.name, created_at=row.created_at)

    def delete_research_topic(self, topic_id):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_delete_research_topic @id=?", topic_id)
        conn.commit(); cur.close(); conn.close()

    # ── Research Rows ────────────────────────────────────────
    def get_research_rows(self, topic_id):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_get_research_rows @topic_id=?", topic_id)
        rows = cur.fetchall(); cur.close(); conn.close()
        return [self._map_row(r) for r in rows]

    def upsert_research_row(self, topic_id, symbol, **fields):
        allowed = ['news','gpa_ratio','pe_ratio','debt_ratio','ta_situation',
                   'mgmt_sentiment','earnings','conclusion','latest_comments']
        params = {k: fields.get(k) for k in allowed}
        conn = self._connect(); cur = conn.cursor()
        cur.execute(
            """EXEC dbo.sm_upsert_research_row
                @topic_id=?, @symbol=?,
                @news=?, @gpa_ratio=?, @pe_ratio=?, @debt_ratio=?,
                @ta_situation=?, @mgmt_sentiment=?, @earnings=?,
                @conclusion=?, @latest_comments=?""",
            topic_id, symbol.upper().strip(),
            params['news'], params['gpa_ratio'], params['pe_ratio'], params['debt_ratio'],
            params['ta_situation'], params['mgmt_sentiment'], params['earnings'],
            params['conclusion'], params['latest_comments']
        )
        row = cur.fetchone(); conn.commit(); cur.close(); conn.close()
        return self._map_row(row)

    def delete_research_row(self, topic_id, symbol):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_delete_research_row @topic_id=?, @symbol=?",
                    topic_id, symbol.upper().strip())
        conn.commit(); cur.close(); conn.close()

    def _map_row(self, r):
        return ResearchRow(
            id=r.id, topic_id=r.topic_id, symbol=r.symbol,
            news=r.news, gpa_ratio=r.gpa_ratio, pe_ratio=r.pe_ratio,
            debt_ratio=r.debt_ratio, ta_situation=r.ta_situation,
            mgmt_sentiment=r.mgmt_sentiment, earnings=r.earnings,
            conclusion=r.conclusion, latest_comments=r.latest_comments,
            updated_at=r.updated_at)

    # ── Email Subscribers ────────────────────────────────────
    def get_portfolio_emails(self, portfolio_id):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_get_portfolio_emails @portfolio_id=?", portfolio_id)
        rows = cur.fetchall(); cur.close(); conn.close()
        return [PortfolioEmail(id=r.id, portfolio_id=r.portfolio_id,
                               email=r.email, name=r.name, added_at=r.added_at) for r in rows]

    def add_portfolio_email(self, portfolio_id, email, name=None):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_add_portfolio_email @portfolio_id=?, @email=?, @name=?",
                    portfolio_id, email.strip().lower(), name)
        row = cur.fetchone(); conn.commit(); cur.close(); conn.close()
        return PortfolioEmail(id=row.id, portfolio_id=row.portfolio_id,
                              email=row.email, name=row.name, added_at=row.added_at)

    def remove_portfolio_email(self, email_id):
        conn = self._connect(); cur = conn.cursor()
        cur.execute("EXEC dbo.sm_remove_portfolio_email @id=?", email_id)
        conn.commit(); cur.close(); conn.close()

    def log_notification(self, portfolio_id, event_type, payload=None, recipients=None, status='sent'):
        try:
            conn = self._connect(); cur = conn.cursor()
            cur.execute("EXEC dbo.sm_log_notification @portfolio_id=?, @event_type=?, @payload=?, @recipients=?, @status=?",
                        portfolio_id, event_type, payload, recipients, status)
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            import logging; logging.getLogger(__name__).error(f"log_notification failed: {e}")