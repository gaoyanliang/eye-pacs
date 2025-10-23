# 每 10 s扫描一次共享目录，将新文件移动到指定目录
# 根据文件代码，重命名文件名字
import logging
import os
import time
import shutil
from datetime import datetime

from gylmodules import global_config, global_tools
from gylmodules.utils.db_utils import DbUtil


logger = logging.getLogger(__name__)


# 配置参数
SOURCE_DIR = "/Users/gaoyanliang/nsyy/eye-pacs/gylmodules/eye_hospital_pacs/1" \
    if global_config.run_in_local else "/srv/samba/shared"  # 监控的共享目录
DEST_BASE_DIR = "/Users/gaoyanliang/nsyy/eye-pacs/gylmodules/eye_hospital_pacs/2" \
    if global_config.run_in_local else "/home/nsyy/pdf-report-catalog"  # 目标基础目录
CHECK_INTERVAL = 20  # 检查间隔（秒）

MAX_RETRIES = 3  # 最大重试次数
FILE_STABILITY_CHECK_INTERVAL = 1  # 文件稳定性检查间隔（秒）
FILE_STABILITY_CHECKS = 3  # 文件稳定性检查次数


"""检查文件是否被其他进程锁定（Linux系统）"""


def is_file_locked(filepath):
    import subprocess
    try:
        output = subprocess.check_output(['lsof', filepath], stderr=subprocess.PIPE)
        return bool(output)
    except subprocess.CalledProcessError:
        return False
    except Exception:
        # 如果lsof不可用，则跳过锁定检查
        return False


"""改进的文件稳定性检查"""


def is_file_stable(filepath):
    sizes, mtimes = [], []
    for _ in range(FILE_STABILITY_CHECKS):
        try:
            sizes.append(os.path.getsize(filepath))
            mtimes.append(os.path.getmtime(filepath))
            time.sleep(FILE_STABILITY_CHECK_INTERVAL)
        except OSError:
            return False

    # 检查文件大小和修改时间是否稳定
    if len(set(sizes)) != 1 or len(set(mtimes)) != 1:
        return False

    # 检查文件是否被锁定
    if is_file_locked(filepath):
        return False

    return True


def get_dated_subdir():
    """获取当天日期的子目录路径，如果不存在则创建"""
    date_str = datetime.now().strftime("%Y%m%d")
    dated_dir = os.path.join(DEST_BASE_DIR, date_str)
    os.makedirs(dated_dir, exist_ok=True)
    return dated_dir


def ensure_dirs_exist():
    """确保基础目录存在"""
    os.makedirs(SOURCE_DIR, exist_ok=True)
    os.makedirs(DEST_BASE_DIR, exist_ok=True)
    logger.debug(f"监控目录: {SOURCE_DIR}")
    logger.debug(f"目标基础目录: {DEST_BASE_DIR}")


def process_file(src_rel_path, retry_count=0):
    """处理文件：保持原始目录结构，移动到当天日期的子目录"""
    try:
        # 源文件完整路径
        src_full_path = os.path.join(SOURCE_DIR, src_rel_path)

        # 基础检查
        if not os.path.exists(src_full_path):
            logger.warning(f"文件不存在: {src_full_path}")
            return False, ''

        # 检查文件稳定性
        if not is_file_stable(src_full_path):
            if retry_count < MAX_RETRIES:
                logger.warning(f"文件不稳定，将重试({retry_count+1}/{MAX_RETRIES}): {src_full_path}")
                time.sleep(5)  # 等待更长时间再重试
                return process_file(src_rel_path, retry_count + 1)
            else:
                logger.warning(f"文件仍不稳定，放弃处理: {src_full_path}")
                return False, ''

        # 分离文件名和扩展名
        dirname, filename = os.path.split(src_rel_path)
        basename, ext = os.path.splitext(filename)
        date_str = datetime.now().strftime("%Y%m%d%H%M%S")
        machine = '未收录设备'
        if str(ext).lower().__contains__('pdf'):
            if filename.startswith("0"):
                basename = "眼表综合检查报告"
                machine = "角膜地形图仪"
            elif filename.startswith("1."):
                basename = "干眼分析1"
                machine = "角膜地形图仪"
            elif filename.startswith("2"):
                basename = "干眼分析2"
                machine = "角膜地形图仪"
            elif filename.startswith("3"):
                basename = "干眼分析3"
                machine = "角膜地形图仪"
            elif (filename == "4.pdf" or filename.startswith("4r") or filename.startswith("4l")
                  or filename.startswith("4R") or filename.startswith("4L") or filename.__contains__("4 Maps Refr")):
                basename = "屈光四图"
                machine = "眼前节分析仪"
            elif (filename == "5.pdf" or filename.startswith("5r") or filename.startswith("5l")
                  or filename.startswith("5R") or filename.startswith("5L")):
                basename = "屈光六图"
                machine = "眼前节分析仪"
            elif (filename == "6.pdf" or filename.startswith("6r") or filename.startswith("6l")
                  or filename.startswith("6R") or filename.startswith("6L")):
                basename = "生物力学"
                machine = "非接触式眼压计"
            elif filename.startswith("7"):
                basename = "眼底照片"
                machine = "眼底照相机"
            if filename.startswith("8"):
                basename = "角膜内皮细胞报告"
                machine = "角膜内皮显微镜"
            elif filename.startswith("9"):
                basename = "角膜地形图"
                machine = "角膜地形图仪Medmont"
            elif filename.startswith("10"):
                basename = "角膜地形图1"
                machine = "角膜地形图仪Medmont"

        new_filename = f"{basename}_{date_str}{ext}"
        # 阿玛仕设备特殊判断
        if basename.__contains__('_'):
            part = basename.split('_')
            if part and len(part) == 4 and len(part[0]) == 10:
                new_filename = f"Master700_{basename}{ext}"
                machine = "蔡司Master700"

        # 获取当天日期目录
        dated_dir = get_dated_subdir()
        # 目标路径（保持原始目录结构）
        dest_full_path = os.path.join(dated_dir, dirname, new_filename)
        dest_dir = os.path.dirname(dest_full_path)

        # 创建目标目录（如果不存在）
        os.makedirs(dest_dir, exist_ok=True)

        # 移动文件
        shutil.move(src_full_path, dest_full_path)
        logger.debug(f"文件已移动: {src_rel_path} -> {dated_dir}/{dirname}/{new_filename}")
        return True, (new_filename, dest_full_path.replace('/', '&'), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), machine)

    except Exception as e:
        logger.error(f"处理文件 {src_rel_path} 失败: {e}")
        return False, ''


def monitor_directory():
    """监控目录及其子目录（改进版）"""
    ensure_dirs_exist()
    current_dated_dir = get_dated_subdir()
    last_check_date = datetime.now().date()

    try:
        while True:
            start_time = time.time()
            # 获取当前日期并检查是否变化
            now = datetime.now()
            if now.date() != last_check_date:
                new_dated_dir = get_dated_subdir()
                logger.debug(f"日期变化，新日期目录: {new_dated_dir}")
                current_dated_dir = new_dated_dir
                last_check_date = now.date()

            # 处理所有现有文件（包括新文件和之前遗留的）
            processed_count = 0
            process_file_list = []
            for root, _, files in os.walk(SOURCE_DIR):
                for filename in files:
                    if str(filename).startswith('.') or not str(filename).endswith('pdf'):
                        continue
                    src_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(src_path, SOURCE_DIR)

                    try:
                        ret, path = process_file(rel_path)
                        if ret:
                            processed_count += 1
                            process_file_list.append(path)
                        else:
                            logger.warning(f"文件处理失败，将重试: {rel_path}")
                    except Exception as e:
                        logger.error(f"处理文件异常: {rel_path} - {str(e)}")

            if process_file_list:
                # 批量插入数据库
                insert_sql = """INSERT INTO nsyy_gyl.ehp_reports 
                                (report_name, report_addr, report_time, report_machine) 
                                VALUES (%s, %s, %s, %s)"""
                db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                            global_config.DB_DATABASE_GYL)
                db.execute_many(insert_sql, args=process_file_list, need_commit=True)
                del db

            # 等待下一次检查
            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        logger.error("监控程序已正常停止")
    except Exception as e:
        logger.error(f"监控发生致命错误: {str(e)}")
        raise


def run_monitor():
    global_tools.start_thread(monitor_directory)

# if __name__ == "__main__":
#     logger.info(f"文件将按日期存储在: {DEST_BASE_DIR}/YYYYMMDD/")
#     monitor_directory()

