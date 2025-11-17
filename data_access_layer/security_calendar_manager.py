import pyodbc

from business_entities.sec_security import SECSecurity


class SecurityCalendarManager:
    """
    Retrieves SEC filing calendar data using stored procedure
    [dbo].[get_securities_reports_calendar].
    """

    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    def get(self, symbol: str, year: int):
        """
        Calls the stored procedure to fetch the filings calendar for a single symbol and year.
        """
        conn = pyodbc.connect(self.connection_string)
        cursor = conn.cursor()

        cursor.execute(
            "EXEC dbo.get_securities_reports_calendar @symbol=?, @year=?",
            (symbol, year)
        )
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description]

        data = [dict(zip(columns, row)) for row in rows]

        cursor.close()
        conn.close()

        return data

    def search(self, query: str):
        conn = pyodbc.connect(self.connection_string)
        cursor = conn.cursor()

        cursor.execute(
            "EXEC dbo.search_securities @query=?",
            (query,)
        )

        rows = cursor.fetchall()
        cols = [c[0] for c in cursor.description]

        result = []
        for row in rows:
            data = dict(zip(cols, row))
            result.append(
                SECSecurity(
                    id=data["id"],
                    ticker=data["ticker"],
                    name=data["name"],
                    cik=data["cik"]
                )
            )

        cursor.close()
        conn.close()

        return result

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

