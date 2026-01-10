import pyodbc

from business_entities.tag_model import TagModel


class TagModelManager:
    """
    Retrieves all tag models using stored procedure get_all_tag_models.
    """

    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    def get_all(self) -> list[TagModel]:
        """
        Calls the stored procedure get_all_tag_models to fetch all tag models.
        """
        conn = pyodbc.connect(self.connection_string)
        cursor = conn.cursor()

        cursor.execute("EXEC get_all_tag_models")
        rows = cursor.fetchall()

        result = [
            TagModel(
                code=row.code,
                name=row.name,
                description=row.description
            )
            for row in rows
        ]

        cursor.close()
        conn.close()

        return result