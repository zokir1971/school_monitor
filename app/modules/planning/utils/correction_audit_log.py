"""Bounded detailed audit file; console receives only the service summary."""
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def write_audit(audit):
    try:
        logger=logging.getLogger('school_monitor.monthly_correction_audit')
        if not logger.handlers:
            directory=Path(__file__).resolve().parents[4]/'logs'
            directory.mkdir(parents=True,exist_ok=True)
            handler=RotatingFileHandler(directory/'monthly_corrections.log',maxBytes=5*1024*1024,backupCount=3,encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
            logger.addHandler(handler)
        logger.propagate=False
        logger.setLevel(logging.INFO)
        logger.info('%s',json.dumps(audit,ensure_ascii=False,default=str))
    except Exception:
        # The database is already committed: logging must not turn a successful save into an error.
        logging.getLogger(__name__).warning('Detailed monthly-plan audit could not be written')
