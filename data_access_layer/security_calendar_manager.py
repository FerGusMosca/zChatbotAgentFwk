import pyodbc

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
