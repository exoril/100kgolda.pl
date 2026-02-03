import logging
import os
from logging.handlers import RotatingFileHandler

def _rotating_file(path: str) -> RotatingFileHandler:
    return RotatingFileHandler(
        filename=path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )

def setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ROOT: aplikacja (konsola + logs/app.log)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)

    app_fh = _rotating_file("logs/app.log")
    app_fh.setLevel(logging.INFO)
    app_fh.setFormatter(fmt)

    root.addHandler(sh)
    root.addHandler(app_fh)

    # PB logger: tylko do logs/pb.log (bez propagacji do root)
    pb_logger = logging.getLogger("pb")
    pb_logger.setLevel(logging.INFO)
    pb_logger.propagate = False
    pb_logger.handlers.clear()

    pb_fh = _rotating_file("logs/pb.log")
    pb_fh.setLevel(logging.INFO)
    pb_fh.setFormatter(fmt)

    pb_logger.addHandler(pb_fh)

    # opcjonalnie przycisz szum
    logging.getLogger("httpx").setLevel(logging.WARNING)
