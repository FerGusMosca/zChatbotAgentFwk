# ===== inner_file_locator.py =====

from pathlib import Path
from typing import List
from common.config.settings import get_settings


class InnerFileLocator:
    """
    Utility class to recursively locate files under a given path.
    """

    @staticmethod
    def list_files(relative_path: str, pattern: str = "*") -> List[Path]:
        """
        Returns a list of file Paths found recursively under:
        {index_files_root_path}/{bot_profile}/{relative_path}

        :param relative_path: Folder path relative to bot profile root
        :param pattern: Glob pattern (default: all files)
        """
        base_root = (
            Path(get_settings().index_files_root_path)
            / get_settings().bot_profile
        )

        target_path = base_root / relative_path

        if not target_path.exists() or not target_path.is_dir():
            return []

        return [p for p in target_path.rglob(pattern) if p.is_file()]
