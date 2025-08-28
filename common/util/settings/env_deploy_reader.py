# utils/env_deploy_reader.py
from pathlib import Path
import os

class EnvDeployReader:
    _config = {}
    _path = None

    @classmethod
    def _find_file(cls, env_file: str):
        cwd = Path.cwd()
        for p in [cwd, *cwd.parents]:
            f = p / env_file
            if f.exists():
                return f
        here = Path(__file__).resolve()
        for p in [here.parent, *here.parents]:
            f = p / env_file
            if f.exists():
                return f
        return None

    @classmethod
    def load(cls, env_file: str = ".env_deploy"):
        path = cls._find_file(env_file)
        if not path:
            raise FileNotFoundError(f"Config '{env_file}' not found from CWD {Path.cwd()} or module path")
        cls._path = path
        cls._config.clear()
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                # quitar comentario inline y espacios
                v = v.split("#", 1)[0].strip()
                cls._config[k.strip()] = v

    @classmethod
    def get(cls, key: str, default=None):
        if not cls._config:
            cls.load()
        if key in os.environ:
            return os.environ[key]
        if key in cls._config:
            return cls._config[key]
        if default is not None:
            return default
        raise KeyError(f"Missing config key '{key}' in {cls._path}; present: {sorted(cls._config)}")
