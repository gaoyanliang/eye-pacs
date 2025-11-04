# # 每 10 s扫描一次共享目录，将新文件移动到指定目录
# # 根据文件代码，重命名文件名字
# import os
# import time
# import shutil
# from datetime import datetime
#
# from gylmodules.eye_hospital_pacs.ehp_server import query_patient_by_name
# from gylmodules.eye_hospital_pacs.pdf_ocr_analysis import analysis_pdf
#
# # 配置参数
# SOURCE_DIR = "/srv/samba/shared"  # 监控的共享目录
# DEST_BASE_DIR = "/home/nsyy/pdf-report-catalog"  # 目标基础目录
# CHECK_INTERVAL = 20  # 检查间隔（秒）
#
# MAX_RETRIES = 3  # 最大重试次数
# FILE_STABILITY_CHECK_INTERVAL = 1  # 文件稳定性检查间隔（秒）
# FILE_STABILITY_CHECKS = 3  # 文件稳定性检查次数
#
#
# """检查文件是否被其他进程锁定（Linux系统）"""
#
#
# def is_file_locked(filepath):
#     import subprocess
#     try:
#         output = subprocess.check_output(['lsof', filepath], stderr=subprocess.PIPE)
#         return bool(output)
#     except subprocess.CalledProcessError:
#         return False
#     except Exception:
#         # 如果lsof不可用，则跳过锁定检查
#         return False
#
#
# """改进的文件稳定性检查"""
#
#
# def is_file_stable(filepath):
#     sizes, mtimes = [], []
#     for _ in range(FILE_STABILITY_CHECKS):
#         try:
#             sizes.append(os.path.getsize(filepath))
#             mtimes.append(os.path.getmtime(filepath))
#             time.sleep(FILE_STABILITY_CHECK_INTERVAL)
#         except OSError:
#             return False
#
#     # 检查文件大小和修改时间是否稳定
#     if len(set(sizes)) != 1 or len(set(mtimes)) != 1:
#         return False
#
#     # 检查文件是否被锁定
#     if is_file_locked(filepath):
#         return False
#
#     return True
#
#
# def get_dated_subdir():
#     """获取当天日期的子目录路径，如果不存在则创建"""
#     date_str = datetime.now().strftime("%Y%m%d")
#     dated_dir = os.path.join(DEST_BASE_DIR, date_str)
#     os.makedirs(dated_dir, exist_ok=True)
#     return dated_dir
#
#
# def ensure_dirs_exist():
#     """确保基础目录存在"""
#     os.makedirs(SOURCE_DIR, exist_ok=True)
#     os.makedirs(DEST_BASE_DIR, exist_ok=True)
#     print(f"监控目录: {SOURCE_DIR}")
#     print(f"目标基础目录: {DEST_BASE_DIR}")
#
#
# def process_file(src_rel_path, retry_count=0):
#     """处理文件：保持原始目录结构，移动到当天日期的子目录"""
#     try:
#         # 源文件完整路径
#         src_full_path = os.path.join(SOURCE_DIR, src_rel_path)
#
#         # 基础检查
#         if not os.path.exists(src_full_path):
#             print(f"文件不存在: {src_full_path}")
#             return False, ''
#
#         # 检查文件稳定性
#         if not is_file_stable(src_full_path):
#             if retry_count < MAX_RETRIES:
#                 print(f"文件不稳定，将重试({retry_count+1}/{MAX_RETRIES}): {src_full_path}")
#                 time.sleep(5)  # 等待更长时间再重试
#                 return process_file(src_rel_path, retry_count + 1)
#             else:
#                 print(f"文件仍不稳定，放弃处理: {src_full_path}")
#                 return False, ''
#
#         # 分离文件名和扩展名
#         dirname, filename = os.path.split(src_rel_path)
#         basename, ext = os.path.splitext(filename)
#         date_str = datetime.now().strftime("%Y%m%d%H%M%S")
#         machine = '未收录设备'
#         if str(ext).lower().__contains__('pdf'):
#             if filename.startswith("202."):
#                 basename = "角膜内皮细胞报告"
#                 machine = "角膜内皮显微镜"
#             elif filename.startswith("203."):
#                 basename = "角膜地形图"
#                 machine = "Medmont"
#             elif filename.startswith("204."):
#                 basename = "蔡司检查"
#                 machine = "蔡司"
#             elif filename.startswith("205."):
#                 basename = "生物力学"
#                 machine = "非接触式眼压计"
#             elif filename.startswith("4."):
#                 basename = "屈光四图"
#                 machine = "眼前节分析仪"
#             elif filename.startswith("5."):
#                 basename = "屈光六图"
#                 machine = "眼前节分析仪"
#             elif filename.startswith("1."):
#                 basename = "干眼分析1"
#                 machine = "角膜地形图仪"
#             elif filename.startswith("2."):
#                 basename = "干眼分析2"
#                 machine = "角膜地形图仪"
#             elif filename.startswith("3."):
#                 basename = "干眼分析3"
#                 machine = "角膜地形图仪"
#
#         new_filename = f"{basename}_{date_str}{ext}"
#
#         print(f'发现文件 {new_filename} 来自 {machine}')
#
#         # 获取当天日期目录
#         dated_dir = get_dated_subdir()
#         # 目标路径（保持原始目录结构）
#         dest_full_path = os.path.join(dated_dir, dirname, new_filename)
#         dest_dir = os.path.dirname(dest_full_path)
#
#         # 创建目标目录（如果不存在）
#         os.makedirs(dest_dir, exist_ok=True)
#
#         # 移动文件
#         shutil.move(src_full_path, dest_full_path)
#         print(f"文件已移动: {src_rel_path} -> {dated_dir}/{dirname}/{new_filename}")
#         return True, (new_filename, dest_full_path.replace('/', '&'), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), machine)
#
#     except Exception as e:
#         print(f"处理文件 {src_rel_path} 失败: {e}")
#         # return False, ''
#
#
# def monitor_directory():
#     """监控目录及其子目录（改进版）"""
#     ensure_dirs_exist()
#     current_dated_dir = get_dated_subdir()
#     last_check_date = datetime.now().date()
#
#     try:
#         start_time = time.time()
#         # 获取当前日期并检查是否变化
#         now = datetime.now()
#         if now.date() != last_check_date:
#             new_dated_dir = get_dated_subdir()
#             print(f"日期变化，新日期目录: {new_dated_dir}")
#             current_dated_dir = new_dated_dir
#             last_check_date = now.date()
#
#         # 处理所有现有文件（包括新文件和之前遗留的）
#         processed_count = 0
#         process_file_list = []
#         for root, _, files in os.walk(SOURCE_DIR):
#             for filename in files:
#                 if str(filename).startswith('.') or not str(filename).endswith('pdf'):
#                     continue
#                 src_path = os.path.join(root, filename)
#                 rel_path = os.path.relpath(src_path, SOURCE_DIR)
#
#                 try:
#                     process_file(rel_path)
#                     # ret, path = process_file(rel_path)
#                     # if ret:
#                     #     processed_count += 1
#                     #     process_file_list.append(path)
#                     # else:
#                     #     print(f"文件处理失败，将重试: {rel_path}")
#                 except Exception as e:
#                     print(f"处理文件异常: {rel_path} - {str(e)}")
#
#         # if process_file_list:
#         #     # 批量插入数据库
#         #     insert_sql = """INSERT INTO nsyy_gyl.ehp_reports
#         #                     (report_name, report_addr, report_time, report_machine)
#         #                     VALUES (%s, %s, %s, %s)"""
#         #     db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
#         #                 global_config.DB_DATABASE_GYL)
#         #     db.execute_many(insert_sql, args=process_file_list, need_commit=True)
#         #     del db
#
#     except KeyboardInterrupt:
#         print("监控程序已正常停止")
#     except Exception as e:
#         print(f"监控发生致命错误: {str(e)}")
#         raise
#
#
# if __name__ == "__main__":
#     # logger.info(f"文件将按日期存储在: {DEST_BASE_DIR}/YYYYMMDD/")
#     # monitor_directory()
#     pdf_file = r"E:\pdf_share\屈光四图_20251021153203.pdf"
#
#     patient_name, values = analysis_pdf(pdf_file)
#
#     if patient_name:
#         patients = query_patient_by_name(patient_name)
#         if patients:
#             register_id = patients[0].get('挂号id')
#             patient_id = patients[0].get('门诊号')
#             bind_sql = f" , register_id = '{register_id}', patient_id = '{patient_id}'"
#
#AL: 22.36 mm  CW-chord: 0.3 mm @ 57  WTW: 11.4 mm  CCT: 537 μm
# AL: 22.47 mm  CW-chord: 0.3 mm d 2138°  WTW: 11.4 mm  CCT: 531 μm
# 2025-10-30 15:08:54.620315 E:\pdf_share\Master700.pdf 解析成功， 耗时 4.63805890083313 s


import re

text = "AL: 22.47 mm  CW-chord: 0.3 mm d 2138°  WTW: 11.4 mm  CCT： 531 μm"

# 直接匹配 CCT: 后面的数字（整数或小数）
pattern = r'CCT[:：]\s*(\d+\.?\d*)'
match = re.search(pattern, text)

if match:
    cct_value = match.group(1)
    print(cct_value)  # 输出: 537



def query_patient_info(date_str):

    # 查询当日所有挂号记录
    sql = f"""SELECT a.id 挂号id, a.病人id, a.门诊号, a.姓名 AS 患者姓名, a.性别, a.年龄, b.名称 AS 就诊科室, 
        a.执行人 AS 医生姓名, a.发生时间 as 就诊日期, TO_CHAR(t2.出生日期, 'YYYY/MM/DD') as 出生日期, t2.家庭电话 联系电话, t2.身份证号 , t2.家庭地址 现住址
    FROM 病人挂号记录 a LEFT JOIN 部门表 b ON a.执行部门id = b.id JOIN 病人信息 t2 ON a.病人id = t2.病人id
    WHERE TRUNC(a.发生时间) = TO_DATE('{date_str}', 'YYYY-MM-DD') AND a.记录状态 = 1"""
    params = {}
    sql = """SELECT t.id                                                            挂号ID, \
                    t.no, \
                    t.门诊号, \
                    t2.就诊卡号, \
                    t2.住院号                                                       病案号, \
                    t.姓名                             AS                           患者姓名, \
                    t.性别,
                    TO_CHAR(t2.出生日期, 'YYYY/MM/DD') as                           出生日期, \
                    t2.婚姻状况, \
                    t2.国籍, \
                    t2.民族, \
                    '身份证'                                                        证件类型, \
                    t2.身份证号                                                     证件号码, \
                    t2.家庭地址                                                     现住址, \
                    t2.家庭电话                                                     联系电话, \
                    t.登记时间                                                      挂号时间, \
                    t.登记时间                                                      报道时间, \
                    t.执行时间                                                      就诊时间, \
                    fy.执行部门                                                     就诊科室, \
                    t.执行人, \
                    ry.专业技术职务                                                 职称,
                    CASE WHEN fy.执行部门 LIKE '%急诊%' THEN '急诊' ELSE '门诊' END 就诊类型,
                    DECODE(t.复诊, 1, '是', '否')                                   是否复诊
             FROM 病人挂号记录 t \
                      JOIN 病人信息 t2 ON t.病人id = t2.病人id \
                      LEFT JOIN 人员表 ry ON ry.姓名 = t.执行人 \
                      LEFT JOIN (SELECT t10.病人id, t10.no, t11.名称 执行部门 \
                                 FROM 门诊费用记录 t10 \
                                          JOIN 部门表 t11 ON t10.执行部门id = t11.id \
                                 WHERE 记录性质 = 4 \
                                   AND 记录状态 = 1) fy ON t.病人id = fy.病人id AND t.no = fy.no \
             WHERE t.id = 2511030008 \
          """

    db_config = {'user': 'ZLHIS', 'password': "DAE42", 'dsn': '192.168.190.254:1521/orcl'}

    try:
        import cx_Oracle
        # 建立数据库连接
        with cx_Oracle.connect(**db_config) as connection:
            # 创建游标
            with connection.cursor() as cursor:
                # 执行查询
                cursor.execute(sql, params)

                # 获取列名
                columns = [col[0].lower() for col in cursor.description]  # 统一转为小写

                # 获取所有结果并转换为字典列表
                results = []
                for row in cursor:
                    # 处理NULL值，将cx_Oracle的NULL转为Python的None
                    row_dict = {}
                    for i, col in enumerate(columns):
                        row_dict[col] = row[i] if row[i] is not None else None
                    results.append(row_dict)


                # logger.info(f"查询耗时： {time.time() - start_time}")
                return results

    except cx_Oracle.Error as error:
        print(f"数据库查询出错: {date_str} {error}")
        return []
    except Exception as e:
        print(f"发生错误: {e}")
        return []


data = query_patient_info("2025-11-03")
for d in data:
    print(d)

