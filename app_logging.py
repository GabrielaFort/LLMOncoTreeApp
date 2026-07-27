import logging
import os
from pathlib import Path


def setup_vm_logging(is_vm_environment: bool) -> logging.Logger:
    logger = logging.getLogger("llm_oncotree_app")

    if not is_vm_environment:
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        return logger

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_path = Path(os.getenv("LOG_FILE", "/app/logs/app.log"))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.FileHandler(log_path, mode="a", encoding="utf-8")],
        force=True,
    )

    return logger
