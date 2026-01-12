import json

import pyodbc
from typing import List, Optional

from business_entities.tag_run import TagRun


class TagRunManager:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    def get_paginated(
        self,
        tag_name: Optional[str] = None,
        portfolio: Optional[str] = None,
        year: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[TagRun]:
        """
        Fetches paginated tag runs using the stored procedure dbo.get_tag_runs_paginated
        Ordered by creation_time DESC
        """
        conn = pyodbc.connect(self.connection_string)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                EXEC dbo.get_tag_runs_paginated 
                    @tag_name   = ?,
                    @portfolio  = ?,
                    @year       = ?,
                    @offset     = ?,
                    @limit      = ?
                """,
                (tag_name, portfolio, year, offset, limit)
            )

            rows = cursor.fetchall()

            result = []
            for row in rows:

                run = TagRun(
                    id=row.id,
                    report=row.report,
                    portfolio=row.portfolio,
                    source=row.source,
                    rank_folder=row.rank_folder,
                    year=row.year,
                    tag_model=row.tag_model,
                    doc_type=row.doc_type,
                    tag_json=row.tag_json,
                    tag_file=row.tag_file,
                    status=row.status,
                    creation_time=row.creation_time,
                    last_update_time=row.last_update_time,
                    last_error=row.last_error
                )
                result.append(run)

            return result

        finally:
            cursor.close()
            conn.close()