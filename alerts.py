import logging

logger = logging.getLogger(__name__)

def send_alerts(portal, url, diff_type, diff_detail):
    logger.info("Alerts disabled — skipping notification for %s", portal)
    pass