# FILE: utils/retrieval_logger.py
# All comments in English.

import os
import datetime


class RetrievalLogger:

    def __init__(self, dump_on_logs: bool, dump_log_file: str):
        """
        :param dump_on_logs: enable or disable dumping logs to file
        :param dump_log_file: folder where the log file will be created
        """
        self.dump_on_logs = dump_on_logs
        self.dump_log_file = dump_log_file
        self.filepath = None
        self.fh = None

    # ---------------------------------------------------------
    def init_log_dump_file(self, source: str):
        """
        If dump_on_logs=True:
        - Create log file if not exists → query_<timestamp>.log
        - If exists → append
        - Write a header indicating that this section is from <source>
        """

        if not self.dump_on_logs:
            return

        # Create folder if not exists
        os.makedirs(self.dump_log_file, exist_ok=True)

        # Reuse same file if already created
        if self.filepath is None:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"{source}_query_{ts}.log"
            self.filepath = os.path.join(self.dump_log_file, fname)

        # Open in append mode
        self.fh = open(self.filepath, "a", encoding="utf-8")

        # Section header
        self.fh.write("\n\n")
        self.fh.write(f"=== APPENDING {source.upper()} SECTION ===\n")

    # ---------------------------------------------------------
    def print_to_file_query_(self, query: str):
        """Write query string to file."""
        if not self.dump_on_logs or not self.fh:
            return

        self.fh.write("\n=== QUERY USED ===\n")
        self.fh.write(query + "\n")

    # ---------------------------------------------------------
    def print_to_file_chunk_(self, source: str, folder: str, rank: int, text: str, pdf: str = None):
        """
        Write single chunk preview to file.
        """
        if not self.dump_on_logs or not self.fh:
            return

        preview = text.replace("\n", " ").strip()[:120]
        if len(text) > 120:
            preview += "..."

        if pdf:
            self.fh.write(f"[KEEP] {source} | {folder} | pdf={pdf} | rank={rank} | {preview}\n")
        else:
            self.fh.write(f"[KEEP] {source} | {folder} | rank={rank} | {preview}\n")

    def print_cross_encoding_comp(self, folder: str, query: str, text: str, score: float):
        """
        Log cross-encoder result: folder, short query, chunk preview and score.
        """
        if not self.dump_on_logs or not self.fh:
            return

        # Short query (first 80 chars)
        short_query = query.strip()[:10]
        if len(query) > 10:
            short_query += "..."

        # Chunk preview (first 120 chars)
        preview = text.replace("\n", " ").strip()[:120]
        if len(text) > 120:
            preview += "..."

        # Write log line
        self.fh.write(
            f"[CROSS] Folder: {folder} | Query: {short_query} | "
            f"Chunk: {preview} | Score: {score:.4f}\n"
        )

    # ---------------------------------------------------------
    def close_log_dump_file(self):
        """Close file handle if opened."""
        if self.fh:
            try:
                self.fh.close()
            except:
                pass
        self.fh = None
