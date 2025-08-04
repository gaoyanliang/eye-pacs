import json
import threading
import traceback
import logging
import time
from logging.handlers import RotatingFileHandler

from functools import wraps, lru_cache
from typing import Callable, Any

import requests
from flask import Blueprint, jsonify, request

from gylmodules import global_config


DB_CONFIG = {
    "dbname": "df_his",
    "user": "ogg",
    "password": "nyogg@2024",
    "host": "192.168.8.57",
    "port": "6000"
}


def setup_logging(log_file='app.log', level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    max_bytes=10 * 1024 * 1024,  # 10MB
    backup_count=5
):
    """
    全局日志配置函数
    :param log_file: 日志文件路径
    :param level: 日志级别（默认INFO）
    :param format: 日志格式
    :param max_bytes: 单个日志文件最大大小
    :param backup_count: 备份文件数量
    """
    # 创建根日志器
    logger = logging.getLogger()
    logger.setLevel(level)

    # 避免重复添加Handler（防止多次调用时重复日志）
    if logger.handlers:
        logger.handlers.clear()

    # 控制台Handler
    if global_config.run_in_local:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(format))
        logger.addHandler(console_handler)

    if not global_config.run_in_local:
        # 文件Handler（自动轮转）
        file_handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            delay=False,  # 禁用延迟打开文件（Python 3.6+）
        )
        file_handler.setFormatter(logging.Formatter(format))
        file_handler.flush()  # 立即刷新缓冲区（可选，但建议添加）

        # 添加Handler
        logger.addHandler(file_handler)

    # 关闭第三方库的冗余日志（可选）， INFO 日志（只显示 WARNING 及以上）
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("hpack").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("hyper").setLevel(logging.WARNING)

    return logger


logger = logging.getLogger(__name__)



def call_yangcheng_sign_serve(param: dict, ts_sign: bool = False):
    """
    调用 杨程 部署的签名服务器，进行签名
    :param param:
    :param ts_sign:
    :return:
    """
    max_retries, retry_count, retry_delay = 3, 0, 1
    while retry_count < max_retries:
        try:
            sign_serve_url = "http://192.168.3.45:8087/yun_signer/opera_sign" \
                if not ts_sign else "http://192.168.3.45:8087/signer/opera_sign"
            response = requests.post(sign_serve_url, timeout=10, json=param)
            data = json.loads(response.text)
            if int(data.get('code')) != 20000:
                raise Exception(data)
            return data.get('data')
        except Exception as e:
            retry_count += 1
            if retry_count <= max_retries:
                sleep_time = retry_delay * (2 ** (retry_count - 1))  # 指数退避
                logging.warning(
                    f"签名服务器连接失败，第 {retry_count}/{max_retries} 次重试..."
                    f"错误: {str(e)}，{sleep_time}秒后重试"
                )
                time.sleep(sleep_time)
            else:
                logging.error(f"签名服务器连接失败，已达最大重试次数 {max_retries}。最后错误: {str(e)}\n")
                return {}


def upload_sign_file(base64_str, is_pdf: bool = False):
    """
    将签名后的 pdf 以及图片上传至服务器
    :param base64_str:
    :param is_pdf:
    :return:
    """
    param = {"type": "save", "b64file": base64_str}
    if is_pdf:
        param['fext'] = 'pdf'
    response = requests.post("http://192.168.3.12:6080/b64pic_process", timeout=10, json=param)
    data = json.loads(response.text)
    if int(data.get('code')) != 20000:
        raise Exception(data)
    return data.get('download_path')



def call_new_his(sql: str, sys: str = 'newzt', clobl: list = None):
    """
    调用新 his 查询数据
    :param sql:
    :param sys:
    :param clobl:
    :return:
    """
    param = {"key": "o4YSo4nmde9HbeUPWY_FTp38mB1c", "sys": sys, "sql": sql}
    if clobl:
        param['clobl'] = clobl

    query_oracle_url = "http://127.0.0.1:6080/oracle_sql"
    if global_config.run_in_local:
        query_oracle_url = "http://192.168.124.53:6080/oracle_sql"

    data = []
    err_data = ''
    try:
        response = requests.post(query_oracle_url, json=param, timeout=50)
        err_data = response.text
        if response.status_code != 200 or not response.text.strip():
            logger.info(f"oracle_sql 请求失败，服务器未返回数据：{response.status_code}  {err_data}  {param}")
            return []
        data = json.loads(response.text)
        data = data.get('data', [])
    except Exception as e:
        logger.error(f"调用新 HIS 查询数据失败：{param.get('sql')}  {err_data}  {str(e)}")

    return data


def start_thread(funct, args=None, tl=None):
    """
    start a thread
    :param funct:
    :param args:
    :param tl:
    :return:
    """

    if not tl:
        tl = []
    if not args:
        args = ()
    t = threading.Thread(target=funct, args=args)
    t.setDaemon(True)  # 服务器一直运行，所以子线程不会被关
    tl.append(t)
    t.start()
    return t


# ==========================================
# ============== router 装饰器 ==============
# ==========================================


# 用装饰器处理重复逻辑
def api_response(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        json_data = {}
        try:
            if request.get_data():
                json_data = json.loads(request.get_data().decode('utf-8'))

            # 本地调试时 打印
            logger.debug(f"请求 {request.url} 参数：{json_data}")

            if not json_data:
                result = func(*args, **kwargs)
            else:
                result = func(json_data, *args, **kwargs)
            return jsonify({'code': 20000, 'data': result if result is not None else {}})
        except json.JSONDecodeError:
            error_msg = f"Invalid JSON format"
            return jsonify({'code': 50000, 'res': error_msg})
        except KeyError as e:
            return jsonify({'code': 50000, 'res': f'Missing parameter: {e}'})
        except Exception as e:
            logger.debug(f"{request.url} 系统异常： {str(e)} , param = {json_data} {traceback.print_exc()}")
            return jsonify({'code': 50000, 'res': str(e)})
    return wrapper


# 参数校验
def validate_params(*required_params):
    def decorator(func):
        @wraps(func)
        def wrapper(json_data, *args, **kwargs):
            missing = [param for param in required_params if param not in json_data]
            if missing:
                raise KeyError(f"Missing params: {', '.join(missing)}")
            return func(json_data, *args, **kwargs)
        return wrapper
    return decorator


# def timed_lru_cache(seconds: int, maxsize: int = 128):
#     """
#     自定义带过期时间的缓存装饰器
#     :param seconds:
#     :param maxsize:
#     :return:
#     """
#     def wrapper(func):
#         func = lru_cache(maxsize=maxsize)(func)
#         func.expiration = {}  # {args: expiration_time}
#
#         @wraps(func)
#         def wrapped(*args, **kwargs):
#             now = time()
#             # 清理过期缓存（可选）
#             expired_keys = [k for k, t in func.expiration.items() if t < now]
#             for key in expired_keys:
#                 func.cache_remove(key)
#                 del func.expiration[key]
#             # 调用函数并记录过期时间
#             result = func(*args, **kwargs)
#             func.expiration[args] = now + seconds
#             return result
#         return wrapped
#     return wrapper


def timed_lru_cache(seconds: int, maxsize: int = 128):
    def wrapper_cache(func: Callable) -> Callable:
        func = lru_cache(maxsize=maxsize)(func)
        func.lifetime = seconds
        func.expire_time = time.time() + func.lifetime

        @wraps(func)
        def wrapped_func(*args: Any, **kwargs: Any) -> Any:
            if time.time() > func.expire_time:
                func.cache_clear()
                func.expire_time = time.time() + func.lifetime
            return func(*args, **kwargs)
        return wrapped_func
    return wrapper_cache
