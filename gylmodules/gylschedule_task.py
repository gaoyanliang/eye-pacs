import logging
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

from gylmodules.eye_hospital_pacs.pdf_ocr_analysis import regularly_parsing_eye_report

# 配置调度器，设置执行器，ThreadPoolExecutor 管理线程池并发
executors = {'default': ThreadPoolExecutor(4), }
gylmodule_scheduler = BackgroundScheduler(timezone="Asia/Shanghai", executors=executors)

logger = logging.getLogger(__name__)


def schedule_task():
    # ====================== 定时任务 ======================
    gylmodule_scheduler.add_job(regularly_parsing_eye_report, trigger='interval', seconds=2*60)

    # ======================  Start ======================
    gylmodule_scheduler.start()
