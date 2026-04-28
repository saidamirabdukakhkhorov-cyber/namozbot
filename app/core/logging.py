import logging, sys, structlog
def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=getattr(logging, level.upper(), logging.INFO))
    structlog.configure(processors=[structlog.contextvars.merge_contextvars, structlog.processors.TimeStamper(fmt="iso", utc=True), structlog.processors.add_log_level, structlog.processors.format_exc_info, structlog.processors.JSONRenderer(ensure_ascii=False)], cache_logger_on_first_use=True)
def get_logger(name: str): return structlog.get_logger(name)
