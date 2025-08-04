# This is a sample Python script.

# Press ⌃R to execute it or replace it with your code.
# Press Double ⇧ to search everywhere for classes, files, tool windows, actions, and settings.

# -*- coding: utf-8 -*-
import os
import time

from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

from gylmodules.app import gylroute
from gylmodules import gylschedule_task, global_config

server_app = Flask(__name__)
server_app.register_blueprint(gylroute, url_prefix='/gyl')

CORS(server_app, supports_credentials=True)
# 需要安装 eventlet， （pip3 install eventlet） 否则 ValueError: Invalid async_mode specified
async_mode = "eventlet"
socketio = SocketIO()
socketio.init_app(server_app, cors_allowed_origins='*', async_mode=async_mode, subprocess=1000, threaded=True)


def start_schedule_work():
    # 如需修改任务，需关闭程序再重新启动
    import atexit
    import fcntl
    lock_file = os.path.join(os.path.dirname(__file__), "scheduler_eye.lock")
    try:
        f = open(lock_file, "wb")
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError as e:
        print(f"无法创建锁文件: {e}")
        return
    except:
        print("无法获取文件锁，可能是另一实例正在运行")
        return

    def unlock():
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()

    atexit.register(unlock)

    gylschedule_task.schedule_task()
    time.sleep(3)  # 至少3秒 确保aaa被占用


if __name__ == '__main__':
    import threading
    t = threading.Thread(target=start_schedule_work)
    t.setDaemon
    t.start()
    port = 8081 if global_config.run_in_local else 8080
    socketio.run(server_app, host='0.0.0.0', port=port, debug=True, use_reloader=True)
