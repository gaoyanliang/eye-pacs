import logging
from datetime import datetime, timedelta

from apscheduler.executors.pool import ThreadPoolExecutor

from apscheduler.schedulers.background import BackgroundScheduler

from gylmodules.eye_hospital_pacs.monitor_new_files import monitor_directory
from gylmodules.eye_hospital_pacs.pdf_ocr_analysis import regularly_parsing_eye_report

# 配置调度器，设置执行器，ThreadPoolExecutor 管理线程池并发
executors = {'default': ThreadPoolExecutor(10), }
gylmodule_scheduler = BackgroundScheduler(timezone="Asia/Shanghai", executors=executors)

logger = logging.getLogger(__name__)


def schedule_task():
    # ====================== 危机值系统定时任务 ======================
    logger.info("=============== 注册定时任务 =====================")
    gylmodule_scheduler.add_job(monitor_directory, trigger='date', run_date=datetime.now())
    gylmodule_scheduler.add_job(regularly_parsing_eye_report, trigger='interval', seconds=1*60)

    # ======================  Start ======================
    gylmodule_scheduler.start()
