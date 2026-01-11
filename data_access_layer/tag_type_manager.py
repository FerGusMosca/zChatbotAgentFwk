import pyodbc

from business_entities.tag_type import TagType


class TagTypeManager:
    """
    Retrieves all tag types using stored procedure get_tag_types.
    """

    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    def get_all(self) -> list[TagType]:
        """
        Calls the stored procedure get_tag_types to fetch all tag types.
        """
        conn = pyodbc.connect(self.connection_string)
        cursor = conn.cursor()

        cursor.execute("EXEC get_tag_types")
        rows = cursor.fetchall()

        result = [
            TagType(
                code=row.code,
                name=row.name,
                description=row.description
            )
            for row in rows
        ]

        cursor.close()
        conn.close()

        return result