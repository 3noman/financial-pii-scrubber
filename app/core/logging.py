import logging
import re
import sys


class PrivacyRedactionFilter(logging.Filter):
    """Safety filter that redacts potential long numeric sequences or emails

    from log records so raw PII never appears in console or file logs.
    """

    _DIGIT_SEQUENCE_RE = re.compile(r"\b(?:\d[ -]*?){8,19}\b")
    _EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        msg = self._EMAIL_RE.sub("<REDACTED_EMAIL_IN_LOG>", msg)
        msg = self._DIGIT_SEQUENCE_RE.sub("<REDACTED_DIGITS_IN_LOG>", msg)
        record.msg = msg
        record.args = ()
        return True


def get_logger(name: str) -> logging.Logger:
    """Returns a configured logger with the PrivacyRedactionFilter attached."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(PrivacyRedactionFilter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger
