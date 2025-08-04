import logging

from flask import Blueprint

from gylmodules import global_config
from gylmodules.eye_hospital_pacs.ehp_router import ehp_system
from gylmodules.global_tools import setup_logging

# 初始化日志
if global_config.run_in_local:
    setup_logging(log_file='my_app.log', level=logging.DEBUG)  # 可按需调整参数
else:
    setup_logging(log_file='my_app.log', level=logging.INFO)  # 可按需调整参数
logger = logging.getLogger(__name__)
logger.info("==================== 应用启动 =========================")

gylroute = Blueprint('gyl', __name__)


# ============================
# === 注册眼科医院pacs系统路由 ===
# ============================
logger.info('注册眼科医院pacs系统路由')
gylroute.register_blueprint(ehp_system)


logger.info("=============== End 路由注册完成 =====================")
