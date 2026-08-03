"""CLI: ротация payload в llm_requests_log. python -m app.jobs.llm_payload_cron

specs/007 — продуктовая аналитика считается Grafana из SQL-представлений,
поэтому отдельная агрегация-джоба не нужна; остаётся только purge payload.
"""
import logging
import sys

from app.db import SessionLocal
from app.services.llm_payload_retention import purge_old_payloads

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> int:
    db = SessionLocal()
    try:
        purged = purge_old_payloads(db)
        logger.info("llm_payload_cron: purged %s rows", purged)
        return 0
    except Exception:
        logger.exception("llm_payload_cron failed")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
