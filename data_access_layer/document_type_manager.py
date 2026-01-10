import pyodbc

from business_entities.document_type import DocumentType


class DocumentTypeManager:
    """
    Retrieves all document types using stored procedure get_all_document_types.
    """

    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    def get_all(self) -> list[DocumentType]:
        """
        Calls the stored procedure get_all_document_types to fetch all document types.
        """
        conn = pyodbc.connect(self.connection_string)
        cursor = conn.cursor()

        cursor.execute("EXEC get_all_document_types")
        rows = cursor.fetchall()

        result = [
            DocumentType(
                code=row.code,
                name=row.name,
                description=row.description
            )
            for row in rows
        ]

        cursor.close()
        conn.close()

        return result