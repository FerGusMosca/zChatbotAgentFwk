import pyodbc
from business_entities.portfolio import Portfolio


class PortfolioManager:
    """
    Retrieves portfolios using stored procedure [dbo].[get_portfolios].
    Returns: List[Portfolio]
    """
    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    def get_all(self):
        conn = pyodbc.connect(self.connection_string)
        cursor = conn.cursor()

        cursor.execute("EXEC dbo.get_portfolios")
        rows = cursor.fetchall()

        portfolios = [
            Portfolio(
                id=row.id,
                portfolio_code=row.portfolio_code,
                name=row.name,
                description=row.description,
                created_at=row.created_at,
                updated_at=row.updated_at
            )
            for row in rows
        ]

        cursor.close()
        conn.close()
        return portfolios
