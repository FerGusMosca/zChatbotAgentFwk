import pyodbc
from business_entities.portfolio_security import PortfolioSecurity
from common.dto.portfolio_security_page import PortfolioSecurityPage
from common.dto.security_search_result import SecuritySearchResult


class PortfolioSecuritiesManager:

    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    # =========================
    # PAGED
    # =========================
    def get_paged(self, portfolio_id: int, page: int, page_size: int):
        conn = pyodbc.connect(self.connection_string)
        cursor = conn.cursor()

        cursor.execute(
            "EXEC dbo.get_portfolio_securities_paged @portfolio_id=?, @page=?, @page_size=?",
            (portfolio_id, page, page_size)
        )

        rows = cursor.fetchall()
        items = [
            PortfolioSecurity(
                id=r.id,
                portfolio_id=r.portfolio_id,
                security_id=r.security_id,
                ticker=r.ticker,
                name=r.name,
                cik=r.cik,
                added_at=r.added_at,
                is_active=r.is_active,
                weight=r.weight
            )
            for r in rows
        ]

        cursor.nextset()
        total_row = cursor.fetchone()
        total_count = total_row.total_count

        cursor.close()
        conn.close()

        return PortfolioSecurityPage(
            items=items,
            total_count=total_count,
            page=page,
            page_size=page_size
        )

    # =========================
    # FULL LIST
    # =========================
    def get_full(self, portfolio_id: int):
        conn = pyodbc.connect(self.connection_string)
        cursor = conn.cursor()

        cursor.execute("EXEC dbo.get_portfolio_securities @portfolio_id=?", (portfolio_id,))
        rows = cursor.fetchall()

        items = [
            PortfolioSecurity(
                id=r.id,
                portfolio_id=r.portfolio_id,
                security_id=r.security_id,
                ticker=r.ticker,
                name=r.name,
                cik=r.cik,
                added_at=r.added_at,
                is_active=r.is_active,
                weight=r.weight
            )
            for r in rows
        ]

        cursor.close()
        conn.close()
        return items

    # =========================
    # SEARCH
    # =========================
    def search(self, query: str):
        conn = pyodbc.connect(self.connection_string)
        cursor = conn.cursor()

        like = f"%{query}%"
        cursor.execute("""
            SELECT TOP 20 id, ticker, name, cik
            FROM SEC_Securities
            WHERE ticker LIKE ? OR name LIKE ?
            ORDER BY ticker
        """, (like, like))

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        return [
            SecuritySearchResult(
                id=r.id,
                ticker=r.ticker,
                name=r.name,
                cik=r.cik
            )
            for r in rows
        ]

    # =========================
    # ADD SINGLE (SP)
    # =========================
    def add_single(self, portfolio_id: int, security_id: int):
        conn = pyodbc.connect(self.connection_string)
        cursor = conn.cursor()

        cursor.execute(
            "EXEC dbo.persist_portfolio_security @portfolio_id=?, @security_id=?",
            (portfolio_id, security_id)
        )

        conn.commit()
        cursor.close()
        conn.close()

    # =========================
    # IMPORT CSV (SP)
    # =========================
    def import_csv(self, portfolio_id: int, csv_text: str):
        lines = [x.strip() for x in csv_text.split("\n") if x.strip()]

        inserted = 0
        updated = 0
        not_found = []

        conn = pyodbc.connect(self.connection_string)
        cursor = conn.cursor()

        for ln in lines:
            parts = ln.split(",")
            ticker = parts[0].strip().upper()

            cursor.execute("SELECT id FROM SEC_Securities WHERE ticker=?", ticker)
            row = cursor.fetchone()

            if not row:
                not_found.append(ticker)
                continue

            security_id = row[0]

            # check existence BEFORE calling SP
            cursor.execute("""
                SELECT COUNT(*) 
                FROM portfolio_securities
                WHERE portfolio_id=? AND security_id=?
            """, (portfolio_id, security_id))
            existed = cursor.fetchone()[0] > 0

            # call SP (insert if needed)
            cursor.execute(
                "EXEC dbo.persist_portfolio_security @portfolio_id=?, @security_id=?",
                (portfolio_id, security_id)
            )

            if existed:
                updated += 1
            else:
                inserted += 1

        conn.commit()
        cursor.close()
        conn.close()

        return {
            "inserted": inserted,
            "updated": updated,
            "not_found": not_found
        }
