import json
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "test1234"

JSONL_PATH = r"C:\Projects\Bias\research_apps\Quant_ML_Research_Platform\output\securities_reports\13_F_GRAPHS\13f\2025_Q1\13f_graph.jsonl"  # AJUSTAR
BATCH_SIZE = 1000


def load_batch(tx, rows):
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (m:Manager {name: row.manager})
        MERGE (a:Asset {cusip: row.cusip})
          ON CREATE SET a.name = row.asset_name
        MERGE (m)-[h:HOLDS]->(a)
        SET h.weight = row.weight,
            h.file = row.file
        """,
        rows=rows,
    )


def main():
    driver = GraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS)
    )

    batch = []
    total = 0

    with open(JSONL_PATH, "r", encoding="utf-8") as f, driver.session() as session:
        for line in f:
            obj = json.loads(line)

            batch.append({
                "manager": obj["src"].replace("manager::", ""),
                "cusip": obj["dst"].replace("asset::", ""),
                "asset_name": obj["dst"].replace("asset::", ""),
                "weight": obj.get("weight", 0),
                "file": obj.get("metadata", {}).get("file"),
            })

            if len(batch) >= BATCH_SIZE:
                session.execute_write(load_batch, batch)
                total += len(batch)
                print(f"Inserted {total}")
                batch.clear()

        if batch:
            session.execute_write(load_batch, batch)
            total += len(batch)

    driver.close()
    print(f"Done. Total rows: {total}")


if __name__ == "__main__":
    main()
