import logging
from datetime import datetime, timedelta

import requests
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler


# 配置调度器，设置执行器，ThreadPoolExecutor 管理线程池并发
executors = {'default': ThreadPoolExecutor(10), }
gylmodule_scheduler = BackgroundScheduler(timezone="Asia/Shanghai", executors=executors)

logger = logging.getLogger(__name__)


def mon_task():
    url = "http://127.0.0.1:8080/gyl/ehp/monitor_task"
    response = requests.post(url)
    if response.status_code != 200:
        logger.error("监控任务执行失败", response.text)


def analy_task():
    url = "http://127.0.0.1:8080/gyl/ehp/analysis_task"
    response = requests.post(url)
    if response.status_code != 200:
        logger.error("解析任务执行失败", response.text)


def schedule_task():
    # ====================== 危机值系统定时任务 ======================
    logger.info("=============== 注册定时任务 =====================")
    gylmodule_scheduler.add_job(mon_task, trigger='date', run_date=datetime.now())
    gylmodule_scheduler.add_job(analy_task, trigger='interval', seconds=10*60)

    # ======================  Start ======================
    gylmodule_scheduler.start()
