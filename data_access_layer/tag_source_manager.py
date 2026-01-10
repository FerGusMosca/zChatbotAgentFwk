import pyodbc

from business_entities.tag_source import TagSource


class TagSourceManager:
    """
    Retrieves all tag sources using a simple SELECT query.
    """

    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    def get_all(self) -> list[TagSource]:
        """
        Returns all records from tag_sources table as TagSource objects.
        """
        conn = pyodbc.connect(self.connection_string)
        cursor = conn.cursor()

        cursor.execute("SELECT code, name, description FROM tag_sources ORDER BY code ASC")
        rows = cursor.fetchall()

        result = [
            TagSource(
                code=row.code,
                name=row.name,
                description=row.description
            )
            for row in rows
        ]

        cursor.close()
        conn.close()

        return result