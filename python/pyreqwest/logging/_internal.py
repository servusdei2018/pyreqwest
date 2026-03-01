import logging


class Timestamper(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "_pyreqwest_log_timestamp") and hasattr(record, "_pyreqwest_start_time"):
            ct = record._pyreqwest_log_timestamp  # noqa: SLF001
            # Same timestamp handling as in LogRecord init
            record.created = ct / 1e9  # ns to float seconds
            record.msecs = (ct % 1_000_000_000) // 1_000_000 + 0.0
            if record.msecs == 999.0 and int(record.created) != ct // 1_000_000_000:  # noqa: PLR2004
                record.msecs = 0.0
            record.relativeCreated = (ct - record._pyreqwest_start_time) / 1e6  # noqa: SLF001
            record.__dict__["_pyreqwest_timestamper_applied"] = True
        return True
