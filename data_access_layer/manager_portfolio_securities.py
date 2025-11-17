import pyodbc
from business_entities.portfolio_security import PortfolioSecurity
from common.dto.portfolio_security_page import PortfolioSecurityPage


class PortfolioSecuritiesManager:

    def __init__(self, connection_string: str):
        self.connection_string = connection_string

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
