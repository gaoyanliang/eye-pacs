import os
from datetime import datetime

from flask import Blueprint, jsonify, request, send_from_directory, send_file, make_response, abort

from gylmodules import global_config
from gylmodules.eye_hospital_pacs.monitor_new_files import DEST_BASE_DIR
from gylmodules.global_tools import api_response, validate_params
from gylmodules.eye_hospital_pacs import ehp_server, monitor_new_files, pdf_ocr_analysis

ehp_system = Blueprint('Eye Hospital Pacs', __name__, url_prefix='/ehp')


@ehp_system.route('/medical_record', methods=['POST'])
@api_response
@validate_params('register_id')
def create_medical_record(json_data):
    ehp_server.create_medical_record(json_data)


@ehp_system.route('/update_medical_record', methods=['POST'])
@api_response
def update_medical_record(json_data):
    ehp_server.update_medical_record_detail(json_data)


@ehp_system.route('/query_medical_list', methods=['POST', 'GET'])
@api_response
@validate_params('register_id')
def query_medical_list(json_data):
    return ehp_server.query_medical_list(json_data.get('register_id'))


@ehp_system.route('/query_medical_record', methods=['POST', 'GET'])
@api_response
def query_medical_record(json_data):
    return ehp_server.query_medical_record(json_data.get('record_detail_id'))


@ehp_system.route('/query_reports', methods=['POST', 'GET'])
@api_response
def query_report_list(json_data):
    return ehp_server.query_report_list(json_data.get('register_id'))


@ehp_system.route('/bind_report', methods=['POST', 'GET'])
@api_response
def bind_report(json_data):
    return ehp_server.bind_report(json_data.get('report_id'), json_data.get('register_id', ''),
                                  json_data.get('patient_id', ''))


@ehp_system.route('/place_on_file', methods=['POST', 'GET'])
@api_response
def place_on_file(json_data):
    return ehp_server.place_on_file(json_data.get('patient_id'), json_data.get('register_id'), json_data.get('is_complete'))


@ehp_system.route('/report/<file_path>', methods=['POST', 'GET'])
def show_report(file_path):
    file_path = file_path.replace("&", "/")
    parts = file_path.split("/")
    file_name = parts[-1]
    dir_path = "/".join(parts[:-1])

    return send_from_directory(dir_path, file_name)


@ehp_system.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return {'code': 50000, 'res': 'No file part'}

    file = request.files['file']
    if file.filename == '':
        return {'code': 50000, 'res': 'No selected file'}

    if file:
        try:
            # 确保上传目录存在
            path = "/Users/gaoyanliang/nsyy/nsyy-project/gylmodules/eye_hospital_pacs/downloaded_files" \
                if global_config.run_in_local else f"{DEST_BASE_DIR}/{datetime.now().strftime('%Y%m%d')}"
            if not os.path.exists(path):
                os.makedirs(path)

            # 安全保存文件
            file_path = os.path.join(path, file.filename)
            file.save(file_path)

            register_id = request.form.get("register_id")
            patient_id = request.form.get("patient_id")
            ehp_server.update_and_bind_report(file.filename, file_path.replace('/', '&'), register_id, patient_id)
            return {'code': 20000, 'res': 'File uploaded successfully'}
        except Exception as e:
            return {'code': 50000, 'res': str(e)}


@ehp_system.route('/monitor_task', methods=['POST', 'GET'])
@api_response
def monitor_task():
    monitor_new_files.monitor_directory()


@ehp_system.route('/analysis_task', methods=['POST', 'GET'])
@api_response
def analysis_task():
    pdf_ocr_analysis.regularly_parsing_eye_report()


