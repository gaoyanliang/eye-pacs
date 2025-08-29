import json
from datetime import datetime

from gylmodules import global_config, global_tools
from gylmodules.utils.db_utils import DbUtil


def create_medical_record(json_data):
    """
    创建病历
    :param json_data:
    :return:
    """
    record_data = {}
    record_id = json_data.get('record_id')

    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)

    try:
        if not record_id:
            # 新增病历
            record_data['register_id'] = json_data.get('register_id')
            if json_data.get('patient_id'):
                record_data['patient_id'] = json_data.get('patient_id')
            record_data['patient_name'] = json_data.get('patient_name')
            record_data['record_name'] = json_data.get('record_name')
            record_data['record_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            record_data['last_update_time'] = record_data['record_time']

            record_sql = f"INSERT INTO nsyy_gyl.ehp_medical_record_list ({','.join(record_data.keys())}) " \
                         f"VALUES {str(tuple(record_data.values()))}"
            record_id = db.execute(sql=record_sql, need_commit=True)
            if record_id == -1:
                del db
                raise Exception("患者病历创建失败! ", record_sql)
        else:
            db.execute(f"UPDATE nsyy_gyl.ehp_medical_record_list "
                       f"SET last_update_time = '{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}' "
                       f"WHERE record_id = {record_id}", need_commit=True)

        # 新增病历详情
        values = [(int(json_data.get('register_id')), int(record_id), item.get('table_id'), item.get('table_name'),
                   json.dumps(item, default=str, ensure_ascii=False), datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                  for item in json_data.get('data')]

        insert_sql = """INSERT INTO nsyy_gyl.ehp_medical_record_detail (register_id, record_id, table_id,
                                                                        table_name, table_value, create_time) \
                        VALUES (%s, %s, %s, %s, %s, %s)"""
        last_row = db.execute_many(insert_sql, args=values, need_commit=True)
        if last_row == -1:
            del db
            raise Exception("急救表单入库失败! ", insert_sql)
        del db
    except Exception as e:
        raise Exception("新增病历异常! ", e)


def update_medical_record_detail(json_data):
    """
    更新创建过的tab表单
    :param json_data:
    :return:
    """
    record_detail_id = json_data.get('record_detail_id')
    table_value = json_data.get('table_value')
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)
    try:
        update_sql = f"""UPDATE nsyy_gyl.ehp_medical_record_detail 
        SET table_value = '{json.dumps(table_value, default=str, ensure_ascii=False)}' where id = {record_detail_id}"""
        db.execute(update_sql, need_commit=True)
        del db
    except Exception as e:
        del db
        raise Exception("新增/更新病历异常! ", e)


def query_medical_list(register_id):
    """
    查询病历列表
    :param register_id:
    :return:
    """
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)

    record_data = db.query_all(f"SELECT r.register_id, r.record_id, r.record_name, r.record_status, "
                               f"rd.id as record_detail_id,rd.table_id, rd.table_name FROM nsyy_gyl.ehp_medical_record_list r "
                               f"join nsyy_gyl.ehp_medical_record_detail rd on r.register_id = rd.register_id "
                               f"and r.record_id = rd.record_id WHERE r.register_id = '{register_id}'")
    del db

    merged = {}
    for record in record_data:
        key = (record["register_id"], record["record_id"])

        if key not in merged:
            # 初始化合并后的记录
            merged[key] = {
                "register_id": record["register_id"],
                "record_id": record["record_id"],
                "record_name": record["record_name"],
                "record_status": record["record_status"],
                "tabs": []  # 存储 {table_id, table_name} 字典
            }

        # 添加 tab 信息
        merged[key]["tabs"].append({
            "record_detail_id": record["record_detail_id"],
            "table_id": record["table_id"],
            "table_name": record["table_name"]
        })

    return list(merged.values())


def query_medical_record(record_detail_id):
    """
    查询病历详情
    :param record_detail_id:
    :return:
    """
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)
    record_data = db.query_all(f"SELECT * FROM nsyy_gyl.ehp_medical_record_detail WHERE id = {record_detail_id}")
    del db

    for d in record_data:
        d['table_value'] = json.loads(d['table_value']) if d['table_value'] else {}
    return record_data


def get_birthday_from_id(id_number):
    """根据身份证号获取出生日期"""
    if len(id_number) == 18:
        birthday = id_number[6:14]  # 截取第7位到第14位
        return birthday[:4] + birthday[4:6] + birthday[6:]
    else:
        return ''


def query_report_list(register_id):
    """
    查询报告列表
    :param register_id: 病人挂号id
    :return:
    """
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)
    report_list = db.query_all(f"SELECT * FROM nsyy_gyl.ehp_reports "
                               f"WHERE register_id = '{register_id}' or register_id is null or register_id = '' ")
    del db
    return report_list


def bind_report(report_id, register_id, patient_id):
    """
    将位置报告和患者绑定起来
    :param report_id: 报告id
    :param register_id: 病人挂号id
    :param patient_id: 病人挂号id
    :return:
    """
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)
    if register_id:
        db.execute(f"UPDATE nsyy_gyl.ehp_reports SET register_id = '{register_id}', patient_id = '{patient_id}' "
                   f"WHERE report_id = {report_id}", need_commit=True)
    else:
        db.execute(f"UPDATE nsyy_gyl.ehp_reports SET register_id = null, patient_id = null "
                   f"WHERE report_id = {report_id}", need_commit=True)

    del db


def update_and_bind_report(file_name, file_path, register_id, patient_id):
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)

    insert_sql = f"""INSERT INTO nsyy_gyl.ehp_reports (report_name, report_addr, report_time, 
    patient_id, register_id, report_machine) VALUES ('{file_name}', '{file_path}', 
    '{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', '{patient_id}', '{register_id}', '人工上传')"""
    report_id = db.execute(insert_sql, need_commit=True)
    del db


def place_on_file(patient_id, register_id, is_complete):
    """
    病历归档，归档之后不允许再修改
    :param register_id:
    :param patient_id:
    :param is_complete: true = 归档 false = 撤销
    :return:
    """

    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)
    record_status = 2 if is_complete else 1
    update_sql = f"""UPDATE nsyy_gyl.ehp_medical_record_list SET record_status = {record_status} 
                    WHERE register_id = '{register_id}' and patient_id = '{patient_id}' """
    db.execute(update_sql, need_commit=True)
    del db


"""查询患者信息 / 当日挂号列表"""


def query_patient_info(key, guahao_id, date_str):
    import cx_Oracle
    # 数据库连接配置（实际应用中应该从环境变量或配置文件中读取）
    db_config = {'user': 'ZLHIS', 'password': "DAE42", 'dsn': '192.168.190.254:1521/orcl'}

    if key:
        sql = f"""SELECT a.id 挂号id, a.病人id, a.门诊号, a.姓名 AS 患者姓名, a.性别, a.年龄, b.名称 AS 就诊科室, 
                a.执行人 AS 医生姓名, a.发生时间 as 就诊日期 FROM 病人挂号记录 a LEFT JOIN 部门表 b ON a.执行部门id = b.id 
                join 病人信息 c on a.病人id = c.病人id WHERE a.记录状态 = 1 and (c.姓名 like '%{key}%' or 
                c.身份证号 like '%{key}%' or c.家庭电话 like '%{key}%') order by a.发生时间 desc """
        params = {}
    else:
        # 根据是否有挂号ID决定查询类型
        if not guahao_id:
            # 查询当日所有挂号记录
            sql = f"""SELECT a.id 挂号id, a.病人id, a.门诊号, a.姓名 AS 患者姓名, a.性别, a.年龄, b.名称 AS 就诊科室, 
            a.执行人 AS 医生姓名, a.发生时间 as 就诊日期 FROM 病人挂号记录 a LEFT JOIN 部门表 b ON a.执行部门id = b.id 
            WHERE TRUNC(a.发生时间) = TO_DATE('{date_str}', 'YYYY-MM-DD') AND a.记录状态 = 1"""
            params = {}
        else:
            # 查询特定挂号ID的详细信息
            sql = """
                  SELECT t.id                                                            挂号ID, \
                         t.no, \
                         t.门诊号, \
                         t2.就诊卡号, \
                         t2.住院号                                                       病案号, \
                         t.姓名, \
                         t.性别,
                         t2.出生日期, \
                         t2.婚姻状况, \
                         t2.国籍, \
                         t2.民族, \
                         '身份证'                                                        证件类型,
                         t2.身份证号                                                     证件号码, \
                         t2.家庭地址                                                     现住址, \
                         t2.家庭电话                                                     联系电话,

                         t.登记时间                                                      挂号时间, \
                         t.登记时间                                                      报道时间, \
                         t.执行时间                                                      就诊时间,
                         fy.执行部门                                                     就诊科室, \
                         t.执行人, \
                         ry.专业技术职务                                                 职称,
                         CASE WHEN fy.执行部门 LIKE '%急诊%' THEN '急诊' ELSE '门诊' END 就诊类型,
                         DECODE(t.复诊, 1, '是', '否')                                   是否复诊
                  FROM 病人挂号记录 t
                           JOIN 病人信息 t2 ON t.病人id = t2.病人id
                           LEFT JOIN 人员表 ry ON ry.姓名 = t.执行人
                           LEFT JOIN (SELECT t10.病人id, t10.no, t11.名称 执行部门 \
                                      FROM 门诊费用记录 t10 \
                                               JOIN 部门表 t11 ON t10.执行部门id = t11.id \
                                      WHERE 记录性质 = 4 \
                                        AND 记录状态 = 1) fy ON t.病人id = fy.病人id AND t.no = fy.no

                  WHERE t.id = :guahao_id \
                  """
            params = {'guahao_id': guahao_id}

    try:
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

                return results[0] if guahao_id else results

    except cx_Oracle.Error as error:
        print(f"数据库查询出错: {error}")
        return []
    except Exception as e:
        print(f"发生错误: {e}")
        return []
