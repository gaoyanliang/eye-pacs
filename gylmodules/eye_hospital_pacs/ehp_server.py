import json
import logging
import re
import time
from datetime import datetime

from gylmodules import global_config
from gylmodules.eye_hospital_pacs import ehp_config
from gylmodules.utils.db_utils import DbUtil


logger = logging.getLogger(__name__)

"""身份证号校验逻辑"""


def validate_id_card(id_card: str) -> bool:
    # 基本格式校验
    if not isinstance(id_card, str) or len(id_card) != 18:
        return False
    # 前17位数字 第十八位数字或X
    pattern = r'^\d{17}[\dX]$'
    if not re.match(pattern, id_card):
        return False

    # 出生日期校验
    birth_date = id_card[6:14]
    try:
        birth = datetime.strptime(birth_date, '%Y%m%d')
        if birth > datetime.now():
            return False
    except ValueError:
        return False

    # 校验码验证
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_codes = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']
    total = sum(int(id_card[i]) * weights[i] for i in range(17))
    mod = total % 11
    expected_check_code = check_codes[mod]
    if id_card[17] != expected_check_code:
        return False
    return True


"""新建患者"""

def new_patient(json_data):
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)

    # 身份证号可以不传，传了就要保持正确
    record_data = {}
    id_card_no = json_data.get('id_card_no')
    if id_card_no:
        if not validate_id_card(id_card_no):
            del db
            raise Exception('身份证号异常，请输入正确的身份证号')
        birth_str = id_card_no[6:14]
        birth_str = datetime.strptime(birth_str, '%Y%m%d').strftime('%Y/%m/%d')

        if db.query_all("select * from nsyy_gyl.ehp_patients where id_card_no = '{id_card_no}'"):
            del db
            raise Exception('存在重复身份证号，请勿重复创建')
        age = datetime.today().date().year - datetime.strptime(id_card_no[6:14], '%Y%m%d').date().year

        record_data['id_card_no'] = id_card_no
        record_data['birth_date'] = birth_str
        record_data['age'] = age

    record_data['name'] = json_data.get('name')
    count = db.query_one("select count(*) from nsyy_gyl.ehp_patients")
    record_data['register_id'] = count.get('count(*)') + 100000000

    record_data['gender'] = json_data.get('gender', '')
    record_data['phone_num'] = json_data.get('phone_num', '')
    record_data['visit_dept'] = json_data.get('visit_dept', '')
    record_data['doc_name'] = json_data.get('doc_name', '')
    record_data['last_visit_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    record_data['visit_date'] = datetime.now().strftime('%Y-%m-%d')
    record_data['home_addr'] = json_data.get('home_addr', '')

    try:

        insert_sql = f"INSERT INTO nsyy_gyl.ehp_patients ({','.join(record_data.keys())}) " \
                     f"VALUES {str(tuple(record_data.values()))}"
        record_id = db.execute(sql=insert_sql, need_commit=True)
        if record_id == -1:
            del db
            raise Exception("新患者创建失败! ", insert_sql)

        del db
    except Exception as e:
        raise Exception("新患者创建失败! ", e)


"""删除自己创建的患者"""


def delete_patient(register_id):
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)
    delete_sql = f"update nsyy_gyl.ehp_patients set is_deleted = 1 where register_id = {register_id} "
    db.execute(delete_sql, need_commit=True)
    del db


"""创建/更新病历"""


def create_medical_record(json_data):
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

            if json_data.get('data'):
                data =  json_data.get('data')
                data = data[0]
                record_data['table_id'] = data.get('table_id')
                record_data['table_name'] = data.get('table_name')
                record_data['table_value'] = json.dumps(data, default=str, ensure_ascii=False)

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

        del db
    except Exception as e:
        raise Exception("新增病历异常! ", e)


"""更新创建过的tab表单"""


def update_medical_record_detail(json_data):
    record_detail_id = json_data.get('record_detail_id')
    table_value = json_data.get('table_value')
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)
    try:
        update_sql = f"""UPDATE nsyy_gyl.ehp_medical_record_list 
        SET table_value = '{json.dumps(table_value, default=str, ensure_ascii=False)}' where record_id = {record_detail_id}"""
        db.execute(update_sql, need_commit=True)
        del db
    except Exception as e:
        del db
        raise Exception("新增/更新病历异常! ", e)


"""删除病历"""


def delete_medical_record(json_data):
    record_detail_id = json_data.get('record_detail_id')
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)
    try:
        update_sql = f"""delete from nsyy_gyl.ehp_medical_record_list where record_id = {record_detail_id}"""
        db.execute(update_sql, need_commit=True)
        del db
    except Exception as e:
        del db
        raise Exception("删除病历异常! ", e)


"""查询病历列表"""


def query_medical_list(register_id):
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)

    record_data = db.query_all(f"SELECT register_id, record_id, record_id as record_detail_id, record_name, "
                               f"record_status, table_id, table_name FROM nsyy_gyl.ehp_medical_record_list "
                               f"WHERE register_id = '{register_id}'")
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


"""查询病历详情"""


def query_medical_record(record_detail_id):
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)
    record_data = db.query_all(f"SELECT * FROM nsyy_gyl.ehp_medical_record_list WHERE record_id = {record_detail_id}")
    del db

    for d in record_data:
        d['table_value'] = json.loads(d['table_value']) if d['table_value'] else {}
    return record_data


"""根据身份证号获取出生日期"""


def get_birthday_from_id(id_number):
    if len(id_number) == 18:
        birthday = id_number[6:14]  # 截取第7位到第14位
        return birthday[:4] + birthday[4:6] + birthday[6:]
    else:
        return ''


"""查询报告列表"""


def query_report_list(register_id):
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)
    report_list = db.query_all(f"SELECT *, YEAR(report_time) as year FROM nsyy_gyl.ehp_reports where register_id = '{register_id}' "
                               f"or ((register_id is null or register_id = '') and  DATE(report_time) = CURRENT_DATE())")
    del db

    merged_dict = {}
    report_group = {}
    other_report = []
    for report in report_list:
        if report.get('register_id'):
            if report.get('year') not in report_group:
                report_group[report.get('year')] = []
            report_group[report.get('year')].append(report)

            if report.get("report_value"):
                report_value = json.loads(report.pop('report_value'))
                merged_dict = {**merged_dict, **report_value}
        else:
            other_report.append(report)

    return {"report_list": {
                        'bind_report': report_group,
                        'other_report': other_report,
                    },
                "手术安全核查表": ehp_config.verification_form,
                "屈光手术风险评估": ehp_config.risk_assessment,
                "术前眼部检查": {
                    "corneal_thick": {
                        "od": merged_dict.get('r_thinnest_point', ''),
                        "os": merged_dict.get('l_thinnest_point', '')
                    },
                    "tbut": {
                        "od": merged_dict.get('r_first_rupture_time', ''),
                        "os": merged_dict.get('l_first_rupture_time', '')
                    },
                    "curvature_radius": {
                        "od": merged_dict.get('r_rm', ''),
                        "os": merged_dict.get('l_rm', ''),
                    },
                    "corneal_curvature": {
                        "k1_od": merged_dict.get('r_k1', ''),
                        "k1_os": merged_dict.get('l_k1', ''),
                        "k2_od": merged_dict.get('r_k2', ''),
                        "k2_os": merged_dict.get('l_k2', ''),
                    },
                    "eye_axis": {
                        "od": merged_dict.get('r_al', ''),
                        "os": merged_dict.get('l_al', ''),
                    },
                    "kappa_angle": {
                        "od": merged_dict.get('r_cw_chord', ''),
                        "os": merged_dict.get('l_cw_chord', ''),
                    }
                },
                "硬性角膜接触镜验配病历": {
                    "axis_od": merged_dict.get('r_al', ''),
                    "axis_os": merged_dict.get('l_al', ''),
                    "corneal_para": {
                        "inner_od": merged_dict.get('r_cd', ''),
                        "inner_os": merged_dict.get('l_cd', ''),
                        "evalue_od": merged_dict.get('r_pe', ''),
                        "evalue_os": merged_dict.get('l_pe', ''),
                        "diameter_od": merged_dict.get('r_wtw', ''),
                        "diameter_os": merged_dict.get('l_wtw', ''),
                        "thickness_od": merged_dict.get('r_cct', ''),
                        "thickness_os": merged_dict.get('l_cct', ''),
                        "curvature_k1_od": merged_dict.get('r_pk1', ''),
                        "curvature_k1_os": merged_dict.get('l_pk1', ''),
                        "curvature_k2_od": merged_dict.get('r_xk2', ''),
                        "curvature_k2_os": merged_dict.get('l_xk2', ''),
                    }
                },
                "TransPRK/FS_LASIK手术记录": {
                    "corneal_curvate_od": merged_dict.get('corneal_curvate_od', ''),
                    "corneal_curvate_os": merged_dict.get('corneal_curvate_os', ''),
                    "diopter_od": merged_dict.get('diopter_od', ''),
                    "diopter_os": merged_dict.get('diopter_os', ''),
                    "corneal_thick_od": merged_dict.get('corneal_thick_od', ''),
                    "corneal_thick_os": merged_dict.get('corneal_thick_os', ''),
                    "flap_thick_od": merged_dict.get('flap_thick_od', ''),
                    "flap_thick_os": merged_dict.get('flap_thick_os', ''),
                    "light_area_od": merged_dict.get('light_area_od', ''),
                    "light_area_os": merged_dict.get('light_area_os', ''),
                    "cut_depth_od": merged_dict.get('cut_depth_od', ''),
                    "cut_depth_os": merged_dict.get('cut_depth_os', ''),
                    "cut_time_od": merged_dict.get('cut_time_od', ''),
                    "cut_time_os": merged_dict.get('cut_time_os', ''),
                },
                "双眼角膜胶原交联术-手术风险评估表": {"er": "0分 P1：正常的患者；除局部病变，无系统性疾病", "yi": "0分 I类手术切口(清洁手术)", "san": "0分 T1：手术在3小时内完成", "total": 0, "operator": "", "table_id": "双眼角膜胶原交联术-手术风险评估表", "nnis_score": 0, "table_name": "双眼角膜胶原交联术-手术风险评估表", "is_emergent": "", "unsign_check": "", "wound_infect": "", "wound_status": True, "operation_eye": "", "operation_time": "", "operation_type": ["器管手术"], "signature_nurse": "", "operation_method": [], "record_detail_id": None, "anesthesia_method": "", "signature_operator": "", "signature_anesthetist": ""},
                "双眼角膜胶原交联术-手术安全核查": {"operator": "", "table_id": "双眼角膜胶原交联术-手术安全核查", "table_name": "双眼角膜胶原交联术-手术安全核查", "operation_eye": "", "operation_time": "", "after_operation": {"other": "", "skin_check": "是", "basic_check": "是", "patient_way": "离院", "operation_mark": "", "pipeline_check": [], "signature_nurse": "", "operation_method": "是", "operation_sample": "是", "operation_supply": "是", "operation_medical": "是", "signature_operator": "", "signature_anesthetist": ""}, "before_operation": {"other": "", "addon_check": "", "basic_check": "是", "nurse_other": "", "estimated_time": True, "operation_mark": "是", "operation_risk": "", "operator_other": "", "estimated_blood": True, "operation_focus": True, "signature_nurse": "", "special_medical": True, "anesthesia_focus": ["其他"], "anesthesia_other": "", "operation_method": "是", "instrument_status": True, "antibacterial_test": True, "signature_anesthetist": ""}, "operation_method": [], "record_detail_id": None, "anesthesia_method": "", "before_anesthesia": {"other": "", "skin_check": "是", "addon_check": [], "basic_check": "是", "blood_check": "否", "mskin_check": "是", "venous_access": "否", "operation_mark": "是", "signature_nurse": "", "allergic_history": "是", "anesthesia_check": "是", "operation_method": "是", "anesthesia_method": "是", "antibacterial_test": "否", "signature_operator": "", "signature_anesthetist": "", "operation_consent_form": "是", "anesthesia_consent_form": "是"}},
                "晶体植入术前眼部检查": {
                    "eyeExam": {
                        "acd": {
                            "od": merged_dict.get('r_depth', ''),
                            "os": merged_dict.get('l_depth', ''),
                        },
                        "wtw": {
                            "master": {
                                "od": merged_dict.get('r_wtw', ''),
                                "os": merged_dict.get('l_wtw', ''),
                            },
                            "pentacam": {
                                "od": merged_dict.get('r_distance', ''),
                                "os": merged_dict.get('l_distance', '')
                            }
                        },
                        "endothelialCells": {
                            "od": merged_dict.get('r_cd', ''),
                            "os": merged_dict.get('l_cd', ''),
                        }
                    }

                },
                "眼视光门诊病历": {
                            "other_check": {
                                "addon": {
                                    "axial_od": merged_dict.get('r_al', ''),
                                    "axial_os": merged_dict.get('l_al', ''),
                                    "map_od_c": merged_dict.get('r_dk3', ''),
                                    "map_od_h": merged_dict.get('r_xk2', ''),
                                    "map_od_v": merged_dict.get('r_pk1', ''),
                                    "map_os_c": merged_dict.get('l_dk3', ''),
                                    "map_os_h": merged_dict.get('l_xk2', ''),
                                    "map_os_v": merged_dict.get('l_pk1', '')
                                }
                            }
                }
            }


"""查询历史未绑定报告"""


def query_history_reports():
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)
    report_list = db.query_all(f"SELECT * FROM nsyy_gyl.ehp_reports where register_id is null or register_id = ''")
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
    db.execute(insert_sql, need_commit=True)
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


"""中文姓名转拼音，自动处理多音字（按常用姓氏优先）。 输出结果为小写、空格分隔。"""


def name_to_pinyin(name: str) -> str:
    from pypinyin import pinyin, lazy_pinyin, Style
    if not name:
        return ""

    # 处理姓氏
    first_char = name[0]
    if first_char in ehp_config.surname_pinyin_map:
        first_pinyin = ehp_config.surname_pinyin_map[first_char]
    else:
        first_pinyin = lazy_pinyin(first_char, style=Style.NORMAL, strict=False)[0]

    # 处理名字
    if len(name) > 1:
        other_pinyin = lazy_pinyin(name[1:], style=Style.NORMAL, strict=False)
    else:
        other_pinyin = []

    return "".join([first_pinyin] + other_pinyin)


"""查询患者信息 / 当日挂号列表"""


def query_patient_info(key, guahao_id, date_str):
    start_time = time.time()
    if guahao_id and len(str(guahao_id)) == 9:
        db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                    global_config.DB_DATABASE_GYL)
        query_sql = (f"select register_id 挂号id, register_id 病人id, register_id 门诊号, name AS 患者姓名, "
                      f"gender 性别, age 年龄, visit_dept AS 就诊科室, doc_name AS 医生姓名, last_visit_time as 就诊日期, "
                      f"birth_date as 出生日期, phone_num 联系电话, id_card_no 身份证号  "
                      f"from nsyy_gyl.ehp_patients where is_deleted = 0 and register_id = {int(guahao_id)}")
        patients = db.query_all(query_sql)
        del db
        for item in patients:
            item['姓名拼音'] = name_to_pinyin(item['患者姓名'])
        return patients

    # 查询自主添加的患者
    local_record = []
    if not guahao_id:
        condition_sql = "and (name like '%{key}%' or id_card_no like '%{key}%' or phone_num like '%{key}%' or home_addr like '%{key}%')" if key else ""
        db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                    global_config.DB_DATABASE_GYL)
        query_sql = (f"select register_id 挂号id, register_id 病人id, register_id 门诊号, name AS 患者姓名, "
                     f"gender 性别, age 年龄, visit_dept AS 就诊科室, doc_name AS 医生姓名, last_visit_time as 就诊日期, "
                     f"birth_date as 出生日期, phone_num 联系电话, id_card_no 身份证号  "
                     f"from nsyy_gyl.ehp_patients where visit_date = '{date_str}' and is_deleted = 0 {condition_sql}" )
        local_record = db.query_all(query_sql)
        del db
        if not local_record:
            local_record = []
        for item in local_record:
            item['姓名拼音'] = name_to_pinyin(item['患者姓名'])

    # 数据库连接配置（实际应用中应该从环境变量或配置文件中读取）
    db_config = {'user': 'ZLHIS', 'password': "DAE42", 'dsn': '192.168.190.254:1521/orcl'}

    if key:
        sql = f"""SELECT a.id 挂号id, a.病人id, a.门诊号, a.姓名 AS 患者姓名, a.性别, a.年龄, b.名称 AS 就诊科室, 
                a.执行人 AS 医生姓名, a.发生时间 as 就诊日期, TO_CHAR(c.出生日期, 'YYYY/MM/DD') as 出生日期, c.家庭电话 联系电话, c.身份证号, c.家庭地址 现住址
                FROM 病人挂号记录 a LEFT JOIN 部门表 b ON a.执行部门id = b.id 
                join 病人信息 c on a.病人id = c.病人id WHERE a.记录状态 = 1 and (c.姓名 like '%{key}%' or 
                c.身份证号 like '%{key}%' or c.家庭电话 like '%{key}%') order by a.发生时间 desc """
        params = {}
    else:
        # 根据是否有挂号ID决定查询类型
        if not guahao_id:
            # 查询当日所有挂号记录
            sql = f"""SELECT a.id 挂号id, a.病人id, a.门诊号, a.姓名 AS 患者姓名, a.性别, a.年龄, b.名称 AS 就诊科室, 
                a.执行人 AS 医生姓名, a.发生时间 as 就诊日期, TO_CHAR(t2.出生日期, 'YYYY/MM/DD') as 出生日期, t2.家庭电话 联系电话, t2.身份证号 , t2.家庭地址 现住址
            FROM 病人挂号记录 a LEFT JOIN 部门表 b ON a.执行部门id = b.id JOIN 病人信息 t2 ON a.病人id = t2.病人id
            WHERE TRUNC(a.发生时间) = TO_DATE('{date_str}', 'YYYY-MM-DD') AND a.记录状态 = 1"""
            params = {}
        else:
            # 查询特定挂号ID的详细信息
            sql = """SELECT t.id 挂号ID, t.no, t.门诊号, t2.就诊卡号, t2.住院号 病案号, t.姓名 AS 患者姓名, t.性别, 
                            TO_CHAR(t2.出生日期, 'YYYY/MM/DD') as 出生日期, \
                         t2.婚姻状况, t2.国籍, t2.民族, '身份证' 证件类型, t2.身份证号 证件号码, \
                         t2.家庭地址 现住址, t2.家庭电话 联系电话, t.登记时间 挂号时间, t.登记时间 报道时间, \
                         t.执行时间 就诊时间, fy.执行部门 就诊科室, t.执行人, ry.专业技术职务 职称,
                         CASE WHEN fy.执行部门 LIKE '%急诊%' THEN '急诊' ELSE '门诊' END 就诊类型, 
                         DECODE(t.复诊, 1, '是', '否') 是否复诊
                FROM 病人挂号记录 t JOIN 病人信息 t2 ON t.病人id = t2.病人id
                LEFT JOIN 人员表 ry ON ry.姓名 = t.执行人 LEFT JOIN (SELECT t10.病人id, t10.no, t11.名称 执行部门 \
                FROM 门诊费用记录 t10 JOIN 部门表 t11 ON t10.执行部门id = t11.id \
                WHERE 记录性质 = 4 AND 记录状态 = 1) fy ON t.病人id = fy.病人id AND t.no = fy.no WHERE t.id = :guahao_id \
                  """
            params = {'guahao_id': guahao_id}

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

                for item in results:
                    item['姓名拼音'] = name_to_pinyin(item['患者姓名'])

                logger.info(f"查询耗时： {time.time() - start_time}")
                return results[0] if guahao_id else results + local_record

    except cx_Oracle.Error as error:
        print(f"数据库查询出错: {error}")
        return []
    except Exception as e:
        print(f"发生错误: {e}")
        return []


"""根据名字查询患者 内部使用 用于将报告绑定患者"""


def query_patient_by_name(name):
    patients = query_patient_info('', '', datetime.now().strftime('%Y-%m-%d'))
    if not patients:
        return None
    for item in patients:
        if item.get('患者姓名') == name or item.get('姓名拼音').lower() == name.lower():
            return [item]
    return None


