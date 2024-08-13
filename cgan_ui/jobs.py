import sys
import os
import time
import schedule
from pathlib import Path
from cgan_ui.download import (
    syncronize_open_ifs_forecast_data,
    syncronize_post_processed_ifs_data,
)
from cgan_ui.utils import set_data_sycn_status
from loguru import logger

logger_opts = dict(
    enqueue=True,
    backtrace=True,
    diagnose=True,
    format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
)

config = {
    "handlers": [
        {"sink": sys.stdout, "colorize": True, **logger_opts},
        {
            "sink": Path(os.getenv("LOGS_DIR", "./")) / "cgan-jobs.log",
            "serialize": True,
            **logger_opts,
        },
    ],
    "extra": {"app": "cgan-jobs"},
}
logger.configure(**config)

logger.info("executing jobs warm-up tasks on scripts initialization!")
set_data_sycn_status(source="cgan", status=0)
set_data_sycn_status(source="ecmwf", status=0)
syncronize_post_processed_ifs_data()
syncronize_open_ifs_forecast_data(dateback=1)
# syncronize_post_processed_ifs_data()

for hour in range(11, 24, 1):
    schedule.every().day.at(f"{str(hour).rjust(2, '0')}:00", "Africa/Nairobi").do(
        syncronize_post_processed_ifs_data
    )
    schedule.every().day.at(f"{str(hour).rjust(2, '0')}:00", "Africa/Nairobi").do(
        syncronize_open_ifs_forecast_data, dateback=1
    )


for job in schedule.get_jobs():
    logger.info(f"scheduled forecasts data download task {job}")

while True:
    all_jobs = schedule.get_jobs()
    schedule.run_pending()
    time.sleep(30 * 60)
