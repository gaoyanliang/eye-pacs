# pdf 文件解析，定时执行

import json
import re

from pathlib import Path
from datetime import datetime

import numpy as np
from PIL import Image
from paddleocr import PaddleOCR
import time
import io
import os
from typing import Literal
from pdf2image import convert_from_path
import cv2

from gylmodules import global_config
from gylmodules.eye_hospital_pacs import ehp_server, ehp_config
from gylmodules.utils.db_utils import DbUtil


"""将 PDF 转换为 JPG 格式图片"""


def pdf_to_jpg(pdf_path, output_dir=os.path.join(os.path.dirname(__file__), "output_jpg"), dpi=300):
    try:
        # 获取 PDF 文件名（不含扩展名）  确保输出目录存在
        pdf_filename = os.path.splitext(os.path.basename(pdf_path))[0]
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # if global_config.run_in_local:
        #     poppler_path = "/opt/homebrew/bin"  # 确保与 pdftoppm 路径一致\
        #     images = convert_from_path(pdf_path, dpi=dpi, fmt='jpg', poppler_path=poppler_path)
        # else:
        images = convert_from_path(pdf_path, dpi=dpi, fmt='jpg')
    except Exception as e:
        print(datetime.now(), f"ERROR {pdf_path} PDF 转换失败: {e}")
        return []

    # 保存图片并记录完整路径
    jpg_paths = []
    for i, image in enumerate(images):
        # 使用 PDF 文件名作为前缀
        jpg_filename = f"{pdf_filename}_page_{i + 1}.jpg"
        jpg_path = os.path.join(output_dir, jpg_filename)
        try:
            image.save(jpg_path, "JPEG")
            # 获取完整路径
            full_path = os.path.abspath(jpg_path)
            jpg_paths.append(full_path)
        except Exception as e:
            print(datetime.now(), f"ERROR 保存第 {i + 1} 页失败: {e}")

    return jpg_paths


"""根据给定的文件路径删除文件。"""


def delete_files(file_paths):
    # 如果输入是单个路径，转换为列表
    if isinstance(file_paths, str):
        file_paths = [file_paths]

    # 存储删除结果
    results = {}
    for file_path in file_paths:
        try:
            # 检查文件是否存在
            if os.path.exists(file_path):
                os.remove(file_path)
                results[file_path] = True
            else:
                results[file_path] = False
                print(datetime.now(), f"ERROR 文件不存在: {os.path.abspath(file_path)}")
        except Exception as e:
            results[file_path] = False
            print(datetime.now(), f"删除文件失败 ({os.path.abspath(file_path)}): {e}")

    return results


class OCRProcessor:
    def __init__(self):
        self._ocr_engine = None

    @property
    def ocr_engine(self):
        if self._ocr_engine is None:
            try:
                if global_config.run_in_local:
                    self._ocr_engine = PaddleOCR(
                        lang="ch",
                        use_textline_orientation=False,
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                    )
                else:
                    self._ocr_engine = PaddleOCR(
                        # lang="ch",
                        use_textline_orientation=False,
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        text_detection_model_dir="/home/nsyy/paddle_ocr_offline/PP-OCRv5_server_det",
                        text_recognition_model_dir="/home/nsyy/paddle_ocr_offline/PP-OCRv5_server_rec"
                    )
            except Exception as e:
                print(datetime.now(), f"初始化失败: {str(e)}")
                raise
        return self._ocr_engine

    def ocr_image(self, image_path, region):
        try:
            # 读取原图 ===
            img = cv2.imread(image_path)
            if img is None:
                print(datetime.now(), "图像未找到")
                return ''

            # === 3. 批量裁剪 & OCR ===
            x1, y1, x2, y2 = region
            cropped = img[y1:y2, x1:x2]
            if cropped.size == 0:
                print(datetime.now(), "裁剪区域无效")
                return ''

            # 保存裁剪图（可选）
            # save_path = os.path.join('/Users/gaoyanliang/nsyy/eye-pacs/gylmodules/eye_hospital_pacs/output_jpg',
            #                          f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_cropped.jpg")
            # cv2.imwrite(save_path, cropped)

            # OCR 识别
            results = self.ocr_engine.predict(cropped)
            page = results[0]
            # 直接获取 rec_texts
            texts = page["rec_texts"]
            # 如果你只关心文本，可直接拼接
            full_text = " ".join([t for t in texts if t.strip()])
            # print(full_text)
            return full_text
        except Exception as e:
            print(datetime.now(), f"OCR处理失败: {str(e)}")
            return ''

    def captcha(self, img):
        try:
            # OCR 识别
            results = self.ocr_engine.predict(img)
            page = results[0]
            # 直接获取 rec_texts
            texts = page["rec_texts"]
            # 如果你只关心文本，可直接拼接
            full_text = " ".join([t for t in texts if t.strip()])
            return full_text
        except Exception as e:
            print(datetime.now(), f"OCR处理失败: {str(e)}")
            return ''


"""根据图片尺寸判断方向"""


def get_pdf_orientation(image_path: str) -> Literal['portrait', 'landscape', 'square', 'unknown']:
    # 检查文件是否存在
    if not os.path.exists(image_path):
        print(f"图片文件不存在: {image_path}")
        return 'unknown'

    try:
        # 打开图片并获取尺寸
        with Image.open(image_path) as img:
            width, height = img.size

            # 计算宽高比
            ratio = width / height

            # 判断方向
            if ratio > 1.25:  # 横版：宽明显大于高
                return 'landscape'
            elif ratio < 0.8:  # 竖版：高明显大于宽
                return 'portrait'
            else:  # 正方形或接近正方形
                return 'square'

    except Exception as e:
        print(f"图片读取失败: {str(e)}")
        return 'unknown'


"""解析判断报告类型"""


def analysis_report_types(saved_jpgs, processor):
    for name, info in ehp_config.report_logo.items():
        try:
            joined_text = processor.ocr_image(saved_jpgs[0], info.get('logo'))
            if name.__contains__("屈光四图") and (
                    joined_text.__contains__("屈光") or joined_text.__contains__("四")):
                return name, info.get('machine')
            elif name.__contains__("屈光六图") and (
                    joined_text.__contains__("增强") or joined_text.__contains__("分析")):
                # 增强型扩张分析
                return name, info.get('machine')
            elif name.__contains__("角膜地形图") and (
                    joined_text.__contains__("南阳市") or joined_text.__contains__("南石眼科医院")):
                # 南阳市南石眼科医院
                return name, info.get('machine')
            elif name.__contains__("角膜内皮细胞报告") and (
                    joined_text.__contains__("角膜内皮") or joined_text.__contains__("细胞报告")):
                # 南阳瑞视眼科医院角膜内皮细胞报告
                return name, info.get('machine')
            elif name.__contains__("眼表综合检查报告") and (
                    joined_text.__contains__("眼表") or joined_text.__contains__("综合")):
                # 眼表综合检查报告
                return name, info.get('machine')
            elif name.__contains__("比较两次检查") and (
                    joined_text.__contains__("比较") or joined_text.__contains__("两次")):
                # 比较两次检查
                return name, info.get('machine')
            elif name.__contains__("图像总览") and (
                    joined_text.__contains__("图像") or joined_text.__contains__("总览")):
                # 图像总览
                return name, info.get('machine')
            elif name.__contains__("生物力学") and (
                    joined_text.__contains__("Corvis ST") or joined_text.__contains__("Corvis") or joined_text.__contains__("ST")):
                return name, info.get('machine')
            elif name.__contains__("眼底照片") and (
                    joined_text.__contains__("机构") or joined_text.__contains__("机") or joined_text.__contains__("构")):
                return name, info.get('machine')
            elif name.__contains__("Master700") and (
                    joined_text.__contains__("700") or joined_text.__contains__("Master") or
                    joined_text.__contains__("master")):
                # IOLMaster 700
                return name, info.get('machine')
            elif name.__contains__("阿玛仕手术报告") and (
                    joined_text.__contains__("Laser") or joined_text.__contains__("laser") or
                    joined_text.__contains__("number")):
                # Laser serial number
                return name, info.get('machine')
            elif name.__contains__("OCT") and (joined_text.lower().__contains__("intalight") or joined_text.lower().__contains__("intai") or
                    joined_text.lower().__contains__("ght")):
                # Laser serial number
                return name, info.get('machine')
        except Exception as e:
            print(datetime.now(), f'解析 {saved_jpgs[0]} 标识失败: {e}')
    return '', "未收录设备"


"""解析pdf文件，并返回患者名字以及需要提取的数据"""


def analysis_pdf(file_path):
    if not file_path.endswith(".pdf"):
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {file_path} 非pdf报告无法解析")
        return None, {}
    ret_data = {}
    final_file_name = ''
    start_time = time.time()
    machine = '未收录设备'
    try:
        # 将pdf文件转换为图片，方便解析, 如果pdf有多页，则会生成多个图片，默认取第一张
        saved_jpgs = pdf_to_jpg(file_path)
        to_jpg_time = time.time() - start_time

        processor = OCRProcessor()
        # 解析并判断文件类型
        analy_name, machine = analysis_report_types(saved_jpgs, processor)
        final_file_name = analy_name if analy_name else Path(file_path).stem
        if analy_name.__contains__('屈光四图'):
            # 区分横版/竖版
            if analy_name.__contains__('竖'):
                regions = {
                    "xing": (260, 1172, 670, 1215), "ming": (260, 1220, 670, 1255), "eye": (540, 1310, 680, 1345),
                    "k1": (550, 1525, 680, 1560), "k2": (550, 1587, 680, 1623), "rm": (312, 1650, 440, 1685),
                    "thinnest_point": (310, 2378, 445, 2412), "depth": (310, 2620, 440, 2655),
                    "distance": (575, 2499, 680, 2535)
                }
            else:
                regions = {
                    "xing": (538, 519, 980, 563), "ming": (538, 576, 980, 620), "eye": (885, 690, 1020, 735),
                    "k1": (900, 960, 1055, 1000), "k2": (900, 1035, 1055, 1080), "rm": (600, 1113, 765, 1157),
                    "thinnest_point": (603, 2018, 765, 2060), "depth": (600, 2315, 766, 2360),
                    "distance": (927, 2167, 1055, 2210)
                }
            for key, region in regions.items():
                try:
                    ret_data[key] = processor.ocr_image(saved_jpgs[0], region)
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {key} 失败: {e}')

            ret_data['name'] = ret_data.pop("xing", "") + ret_data.pop("ming", "")
            ret_data['name'] = ret_data['name'].replace(' ', '').replace(',', '')\
                .replace('，', '').replace('.', '').replace('。', '')
            if ret_data.get("eye").__contains__('左眼') or ret_data.get("eye").__contains__('左'):
                final_file_name = f"{final_file_name}-左眼"
                ret_data['l_k1'] = ret_data.pop("k1")
                ret_data['l_k2'] = ret_data.pop("k2")
                ret_data['l_rm'] = ret_data.pop("rm")
                ret_data['l_thinnest_point'] = ret_data.pop("thinnest_point")
                ret_data['l_depth'] = ret_data.pop("depth")
                ret_data['l_distance'] = ret_data.pop("distance")
            else:
                final_file_name = f"{final_file_name}-右眼"
                ret_data['r_k1'] = ret_data.pop("k1")
                ret_data['r_k2'] = ret_data.pop("k2")
                ret_data['r_rm'] = ret_data.pop("rm")
                ret_data['r_thinnest_point'] = ret_data.pop("thinnest_point")
                ret_data['r_depth'] = ret_data.pop("depth")
                ret_data['r_distance'] = ret_data.pop("distance")
        elif analy_name.__contains__('屈光六图'):
            # 区分横版/竖版
            if analy_name.__contains__('竖'):
                regions = {"xing": (1430, 1170, 1550, 1210), "ming": (1430, 1210, 1550, 1250),
                                     "eye": (1645, 1284, 1750, 1320)}
            else:
                regions = {"xing": (1995, 515, 2150, 560), "ming": (1995, 567, 2150, 610),
                           "eye": (2260, 655, 2380, 705)}
            for key, region in regions.items():
                try:
                    ret_data[key] = processor.ocr_image(saved_jpgs[0], region)
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {key} 失败: {e}')
            ret_data['name'] = ret_data.pop("xing", "") + ret_data.pop("ming", "")
            ret_data['name'] = ret_data['name'].replace(' ', '').replace(',', '')\
                .replace('，', '').replace('.', '').replace('。', '')
            if ret_data['eye'].__contains__('左眼') or ret_data['eye'].__contains__('左'):
                final_file_name = f"{final_file_name}-左眼"
            else:
                final_file_name = f"{final_file_name}-右眼"
        elif analy_name.__contains__('角膜内皮细胞报告'):
            is_panoramic = False
            is_success = True
            try:
                tmp_text = processor.ocr_image(saved_jpgs[0], (1980, 640, 2155, 690))
                if "panoramic" in tmp_text or "Panoramic" in tmp_text or "Pan" in tmp_text or "amic" in tmp_text:
                    is_panoramic = True
            except Exception as e:
                is_success = False
                print(datetime.now(), f'解析角膜内皮细胞报告失败: {e}')

            if is_success:
                if is_panoramic:
                    regions = {
                        "eye_up": (320, 710, 485, 780), "eye_down": (320, 2010, 485, 2080), "name": (780, 430, 1160, 550),
                        "cd1": (1110, 1210, 1580, 1310), "cd2": (1110, 2500, 1580, 2600)
                    }
                else:
                    regions = {
                        "eye_up": (320, 710, 485, 780), "eye_down": (320, 2010, 485, 2080), "name": (780, 430, 1160, 550),
                        "cd1": (1250, 1180, 1650, 1280), "cd2": (1250, 2480, 1650, 2580)
                    }
                for key, region in regions.items():
                    try:
                        ret_data[key] = processor.ocr_image(saved_jpgs[0], region)
                    except Exception as e:
                        print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {key} 失败: {e}')

                match = re.search(r'[：:]\s*([\u4e00-\u9fa5]{2,4}|[A-Za-z\s]+)', ret_data.get("name", ""))
                if match:
                    ret_data['name'] = match.group(1).strip()
                ret_data['name'] = (ret_data.get("name", "").replace(' ', '').replace(',', '')
                                    .replace('，', '').replace('.', '').replace('。', ''))

                cd_matches = re.findall(r'CD[：:\s]*(\d+)', ret_data.get('cd1', ''), re.IGNORECASE)
                ret_data['cd1'] = cd_matches[0]
                cd_matches = re.findall(r'CD[：:\s]*(\d+)', ret_data.get('cd2', ''), re.IGNORECASE)
                ret_data['cd2'] = cd_matches[0]
                if ret_data.get('eye_up', '').__contains__("OD") or ret_data.get('eye_up', '').__contains__("od") or ret_data.get('eye_up', '').__contains__("R"):
                    ret_data['r_cd'] = ret_data.pop('cd1', '')
                else:
                    ret_data['l_cd'] = ret_data.pop('cd1', '')
                if ret_data.get('eye_down', '').__contains__("OS") or ret_data.get('eye_down', '').__contains__("os") or ret_data.get('eye_down', '').__contains__("L"):
                    ret_data['l_cd'] = ret_data.pop('cd2', '')
                else:
                    ret_data['r_cd'] = ret_data.pop('cd2', '')
        elif analy_name.__contains__('眼表综合检查报告') or analy_name.__contains__('角膜地形图'):
            if analy_name.__contains__('眼表综合检查报告'):
                regions = {
                    "name": (50, 310, 500, 390), "r_first_rupture_time": (620, 500, 1000, 580),
                    "l_first_rupture_time": (1400, 500, 1700, 580)
                }
            else:
                regions = {
                    "name": (55, 150, 700, 220), "r_pk1": (450, 1600, 995, 1670), "r_xk2": (450, 1670, 995, 1735),
                    "r_dk3": (450, 1740, 1080, 1800), "r_pe": (450, 1800, 995, 1870),
                    "l_pk1": (2150, 1600, 2705, 1670),
                    "l_xk2": (2150, 1665, 2705, 1739), "l_dk3": (2150, 1740, 2800, 1800),
                    "l_pe": (2150, 1800, 2705, 1870)
                }
            for key, region in regions.items():
                try:
                    ret_data[key] = processor.ocr_image(saved_jpgs[0], region)
                    # print(key, ret_data[key])
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {key} 失败: {e}')

            match = re.search(r'[：:]\s*([\u4e00-\u9fa5]{2,4}|[A-Za-z\s]+)', ret_data.get("name", ""))
            if match:
                ret_data['name'] = match.group(1).strip()
            ret_data['name'] = ret_data.get("name", "").replace(' ', '').replace(',', '') \
                .replace('，', '').replace('.', '').replace('。', '')

            if 'r_pk1' in ret_data:
                match = re.search(r'([\d.]+)屈光度', ret_data.get('r_pk1', ''))
                ret_data['r_pk1'] = match.group(1) if match else ret_data.get('r_pk1', '')
                if ret_data['r_pk1']:
                    numbers = re.findall(r'(?<!\()\b\d+\.?\d*\b(?!\))', ret_data['r_pk1'])
                    if len(numbers) >= 1:
                        ret_data['r_pk1'] = numbers[0]
                    if len(numbers) >= 2:
                        ret_data['r_pk1_1'] = numbers[1]

                match = re.search(r'([\d.]+)屈光度', ret_data.get('l_pk1', ''))
                ret_data['l_pk1'] = match.group(1) if match else ret_data.get('l_pk1', '')
                if ret_data['l_pk1'] and ret_data['l_pk1'].__contains__("屈光度"):
                    tmp = ret_data['l_pk1']
                    tmp = tmp.replace(' ', '').replace('@', '')
                    tmp = tmp.split('屈光度')
                    if tmp and len(tmp) > 0:
                        ret_data['l_pk1'] = tmp[0]
                    if tmp and len(tmp) > 1:
                        ret_data['l_pk1_1'] = tmp[1]

                match = re.search(r'([\d.]+)屈光度', ret_data.get('r_xk2', ''))
                ret_data['r_xk2'] = match.group(1) if match else ret_data.get('r_xk2', '')
                if ret_data['r_xk2'] and ret_data['r_xk2'].__contains__("屈光度"):
                    tmp = ret_data['r_xk2']
                    tmp = tmp.replace(' ', '').replace('@', '')
                    tmp = tmp.split('屈光度')
                    if tmp and len(tmp) > 0:
                        ret_data['r_xk2'] = tmp[0]
                    if tmp and len(tmp) > 1:
                        ret_data['r_xk2_1'] = tmp[1]

                match = re.search(r'([\d.]+)屈光度', ret_data.get('l_xk2', ''))
                ret_data['l_xk2'] = match.group(1) if match else ret_data.get('l_xk2', '')
                if ret_data['l_xk2'] and ret_data['l_xk2'].__contains__("屈光度"):
                    tmp = ret_data['l_xk2']
                    tmp = tmp.replace(' ', '').replace('@', '')
                    tmp = tmp.split('屈光度')
                    if tmp and len(tmp) > 0:
                        ret_data['l_xk2'] = tmp[0]
                    if tmp and len(tmp) > 1:
                        ret_data['l_xk2_1'] = tmp[1]

                match = re.search(r'^\d+(?:\.\d+)?', ret_data.get('r_pe', ''))
                ret_data['r_pe'] = match.group() if match else ret_data.get('r_pe', '')
                match = re.search(r'^\d+(?:\.\d+)?', ret_data.get('l_pe', ''))
                ret_data['l_pe'] = match.group() if match else ret_data.get('l_pe', '')
            if (not ret_data.get('r_pk1', '') and not ret_data.get('l_pk1', '')
                    and not ret_data.get('r_pe', '') and not ret_data.get('l_pe', '')):
                # 有两种报告，其中一种没有数据 只有图表
                ret_data.pop('r_pk1')
                ret_data.pop('l_pk1')
                ret_data.pop('r_xk2')
                ret_data.pop('l_xk2')
                ret_data.pop('r_pe')
                ret_data.pop('l_pe')
                ret_data.pop('l_dk3')
                ret_data.pop('r_dk3')
        elif analy_name.__contains__('图像总览') or analy_name.__contains__('比较两次检查'):
            if analy_name.__contains__('比较两次检查'):
                regions = {
                    "name": (540, 515, 850, 565), "eye": (850, 605, 940, 655),
                }
            else:
                regions = {
                    "name": (530, 520, 850, 571), "eye": (2850, 520, 3000, 571),
                }
            for key, region in regions.items():
                try:
                    ret_data[key] = processor.ocr_image(saved_jpgs[0], region)
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {key} 失败: {e}')
            ret_data['name'] = ret_data.get("name", "").replace(' ', '').replace(',', '') \
                .replace('，', '').replace('.', '').replace('。', '')
            if ret_data['eye'].__contains__('左眼') or ret_data['eye'].__contains__('左'):
                final_file_name = f"{final_file_name}-左眼"
            else:
                final_file_name = f"{final_file_name}-右眼"
        elif analy_name.__contains__('生物力学'):
            # 区分横版/竖版
            if analy_name.__contains__('竖'):
                regions = {"name": (180, 1210, 430, 1250), "eye": (940, 1250, 1130, 1295)}
            else:
                regions = {"name": (420, 535, 750, 591), "eye": (1370, 591, 1650, 650)}
            for key, region in regions.items():
                try:
                    ret_data[key] = processor.ocr_image(saved_jpgs[0], region)
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {key} 失败: {e}')
            ret_data['name'] = ret_data.get('name', '').replace(' ', '').replace(',', '') \
                .replace('，', '').replace('.', '').replace('。', '')
            if ret_data['eye'].__contains__('OS') or ret_data['eye'].__contains__('os') or \
                    ret_data['eye'].__contains__('Left') or ret_data['eye'].__contains__('left'):
                final_file_name = f"{final_file_name}-左眼"
            else:
                final_file_name = f"{final_file_name}-右眼"
        elif analy_name.__contains__('眼底照片'):
            regions = {"name": (1150, 50, 1600, 115)}
            for key, region in regions.items():
                try:
                    ret_data[key] = processor.ocr_image(saved_jpgs[0], region)
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {key} 失败: {e}')
            ret_data['name'] = ret_data.get('name', '').replace(' ', '').replace(',', '') \
                .replace('，', '').replace('.', '').replace('。', '')
        elif analy_name.__contains__('Master700'):
            index = 0
            is_success = True
            for item in saved_jpgs:
                ret_str = ""
                try:
                    ret_str = processor.ocr_image(item, (950, 930, 1600, 1090))
                    if ret_str.__contains__("生物统计值") or ret_str.__contains__("生物") or ret_str.__contains__("生"):
                        break
                    else:
                        index = index + 1
                except Exception as e:
                    is_success = False
                    print(datetime.now(), f'Master 700 解析标题失败: {e}')
            if is_success:
                regions = {"name": (450, 120, 900, 250),
                           "l_al": (1405, 1360, 1630, 1425), "r_al": (340, 1360, 560, 1425),
                           "l_cct": (1405, 1416, 1630, 1470), "r_cct": (340, 1416, 560, 1470),
                           "l_wtw": (1410, 2710, 1720, 2770), "r_wtw": (340, 2710, 620, 2770),
                           "l_cw_chord": (1910, 2760, 2240, 2820), "r_cw_chord": (840, 2760, 1220, 2820)
                           }
                for key, region in regions.items():
                    try:
                        ret_data[key] = processor.ocr_image(saved_jpgs[index], region)
                    except Exception as e:
                        print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {key} 失败: {e}')
                ret_data['name'] = ret_data.get('name', '').replace(' ', '').replace(',', '') \
                    .replace('，', '').replace('.', '').replace('。', '')

                if 'l_cw_chord' in ret_data:
                    pattern = r'([\d.]+)\s*mm\s*(?:@|\(\d+\)|（\d+）|\d*\s*)?\s*(\d+)\s*°?'
                    match = re.search(pattern, ret_data.get('l_cw_chord', ''))
                    if match:
                        num1 = match.group(1) if match.group(1) else ''
                        num2 = match.group(2) if match.group(2) else ''
                        ret_data['l_cw_chord'] = f"{num1} mm @ {num2}°"
                if 'r_cw_chord' in ret_data:
                    pattern = r'([\d.]+)\s*mm\s*(?:@|\(\d+\)|（\d+）|\d*\s*)?\s*(\d+)\s*°?'
                    match = re.search(pattern, ret_data.get('r_cw_chord', ''))
                    if match:
                        num1 = match.group(1) if match.group(1) else ''
                        num2 = match.group(2) if match.group(2) else ''
                        ret_data['r_cw_chord'] = f"{num1} mm @ {num2}°"
        elif analy_name.__contains__('阿玛仕手术报告'):
            regions = {
                    "xing": (1310, 555, 1600, 625), "ming": (880, 555, 1200, 625), "eye": (300, 500, 430, 630),
                    "p_k1": (680, 960, 1110, 1025), "p_k2": (680, 1025, 1110, 1090), "diopter": (680, 1360, 1280, 1430),
                    "light_area": (1925, 710, 2380, 780), "cut_depth": (1925, 940, 2380, 1020),
                    "cut_time": (700, 1560, 1200, 1625)
                }
            for key, region in regions.items():
                try:
                    ret_data[key] = processor.ocr_image(saved_jpgs[0], region)
                    # print(key, ret_data[key])
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {key} 失败: {e}')
            ret_data['name'] = ret_data.pop('xing', '') + ret_data.pop('ming', '')
            ret_data['name'] = ret_data.get('name', '').replace(' ', '').replace(',', '') \
                .replace('，', '').replace('.', '').replace('。', '')
            eye_type = "os"
            if ret_data.get('eye_type', '').__contains__('OD') or ret_data.get('eye_type', '').__contains__('od'):
                eye_type = "od"

            # 提取数字部分（包括小数和整数）
            numbers = re.findall(r'\d+(?:[.,]\d+)?', ret_data.get('p_k1', ''))
            if len(numbers) > 0:
                ret_data['p_k1'] = f"k1 {numbers[0]}"

            numbers = re.findall(r'\d+(?:[.,]\d+)?', ret_data.get('p_k2', ''))
            if len(numbers) > 0:
                ret_data['p_k2'] = f"k2 {numbers[0]}"

            ret_data[f'corneal_curvate_{eye_type}'] = ret_data.pop('p_k1', '') + " " + ret_data.pop('p_k2', '')
            ret_data[f'diopter_{eye_type}'] = ret_data.pop('diopter', '').replace('X', ' ').replace('x', ' ') + '°'
            ret_data[f'light_area_{eye_type}'] = ret_data.pop('light_area', '')
            ret_data[f'cut_depth_{eye_type}'] = ret_data.pop('cut_depth', '')
            ret_data[f'cut_time_{eye_type}'] = ret_data.pop('cut_time', '')
        elif analy_name.__contains__('OCT'):
            # 区分横版/竖版
            if analy_name.__contains__('竖'):
                regions = {"name": (130, 130, 350, 195), "eye": (20, 20, 250, 125)}
            else:
                regions = {"name": (120, 110, 330, 170), "eye": (20, 20, 230, 105)}
            for key, region in regions.items():
                try:
                    ret_data[key] = processor.ocr_image(saved_jpgs[0], region)
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {key} 失败: {e}')
            ret_data['name'] = ret_data.get('name', '').replace(' ', '').replace(',', '') \
                .replace('，', '').replace('.', '').replace('。', '')
            if ret_data['eye'].__contains__('OS') or ret_data['eye'].__contains__('os') or \
                    ret_data['eye'].__contains__('L'):
                final_file_name = f"{final_file_name}-左眼"
            elif ret_data['eye'].__contains__('OD') or ret_data['eye'].__contains__('od') or \
                    ret_data['eye'].__contains__('R'):
                final_file_name = f"{final_file_name}-右眼"
            else:
                final_file_name = f"{final_file_name}-双眼"
        else:
           print(f"{datetime.now()} {file_path} 暂不支持解析")
    except Exception as e:
        print(f"{datetime.now()} {file_path} 解析报告异常 {e}")

    for k, v in ret_data.items():
        ret_data[k] = str(v).replace('mm', '')
        if str(v).endswith('s') or str(v).endswith('um') or str(v).endswith('mm') or str(v).endswith('μm') \
                or str(v).endswith('毫米') or str(v).endswith('微米') or str(v).endswith('D') \
                or str(v).endswith('x') or str(v).endswith('Dx'):
            ret_data[k] = (str(v).replace('mm', '').replace('μm', '')
                           .replace('毫米', '').replace('微米', '')
                           .replace('D', '').replace('Dx', '')
                           .replace('x', '').replace('um', '').replace('s', ''))

    print(f"{datetime.now()} {file_path} 解析报告成功, to-jpg 耗时 {to_jpg_time}, 总耗时 {time.time() - start_time}")
    return final_file_name, machine, ret_data


def regularly_parsing_eye_report():
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)
    report_list = db.query_all(f"SELECT * FROM nsyy_gyl.ehp_reports "
                               f"WHERE report_value is null ORDER BY report_time limit 5")

    try:
        for report in report_list:
            file_path = report.get('report_addr').replace('&', '/')
            if not os.path.exists(file_path) and not str(file_path).endswith(".pdf") :
                continue

            final_file_name, machine, values = analysis_pdf(file_path)
            patient_name = values.get('name', '')
            if not values:
                values = {"res": "analysis failed"}

            report_name = f"{final_file_name}-{patient_name}-{report.get('report_time').strftime('%Y-%m-%d_%H:%M:%S')}.pdf"
            report_value = json.dumps(values, ensure_ascii=False, default=str) if values else ''

            bind_sql = ""
            if patient_name:
                patients = ehp_server.query_patient_by_name(patient_name)
                if patients:
                    register_id = patients[0].get('挂号id')
                    patient_id = patients[0].get('门诊号')
                    bind_sql = f" , register_id = '{register_id}', patient_id = '{patient_id}'"
            db.execute(f"UPDATE nsyy_gyl.ehp_reports SET report_name = '{report_name}', "
                       f"report_value = '{report_value}', report_machine = '{machine}' {bind_sql} "
                       f"WHERE report_id = {report.get('report_id')}", need_commit=True)
    except Exception as e:
        del db
        raise Exception(e)
    del db


"""解析翻转拍网站验证码"""


def ocr_captcha(base64_str):
    if not base64_str:
        return ''

    try:
        import base64
        if "," in base64_str:
            base64_str = base64_str.split(",")[1]

        img_data = base64.b64decode(base64_str)
        img_array = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        processor = OCRProcessor()
        ret_data = processor.captcha(img)
        return ret_data
    except Exception as e:
        print(e)
        return ''


if __name__ == "__main__":
    start_time = time.time()
    file_path = r"E:\pdf_share\屈光四图-横版.pdf"
    file_path = r"E:\pdf_share\屈光四图-竖版.pdf"
    file_path = r"E:\pdf_share\屈光六图-横版.pdf"
    file_path = r"E:\pdf_share\屈光六图-竖版.pdf"
    file_path = r"E:\pdf_share\角膜内皮细胞报告21.pdf"
    file_path = r"E:\pdf_share\角膜内皮细胞报告22.pdf"
    file_path = r"E:\pdf_share\角膜内皮细胞报告23.pdf"
    file_path = r"E:\pdf_share\角膜内皮细胞报告211.pdf"
    # file_path = r"E:\pdf_share\眼表综合检查报告41.pdf"
    # file_path = r"E:\pdf_share\眼表综合检查报告42.pdf"
    # file_path = r"E:\pdf_share\眼表综合检查报告43.pdf"
    # file_path = r"E:\pdf_share\眼表综合检查报告44.pdf"
    file_path = r"E:\pdf_share\角膜地形图31.pdf"
    # file_path = r"E:\pdf_share\角膜地形图32.pdf"
    # file_path = r"E:\pdf_share\图像总览53.pdf"
    # file_path = r"E:\pdf_share\比较两次检查54.pdf"
    # file_path = r"E:\pdf_share\生物力学-横版.pdf"
    # file_path = r"E:\pdf_share\生物力学-竖版.pdf"
    # file_path = r"E:\pdf_share\眼底照片.pdf"
    file_path = r"E:\pdf_share\Master700.pdf"
    # file_path = r"E:\pdf_share\阿玛仕手术报告.pdf"
    # file_path = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/已经解析的所有病历/屈光四图-横版.pdf"
    # file_path = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/已经解析的所有病历/Master700.pdf"
    # file_path = "/Users/gaoyanliang/Downloads/3 (2)_20251111101643.pdf"

    # file_path = "/Users/gaoyanliang/Downloads/房角OCT-右眼.pdf"
    # file_path = "/Users/gaoyanliang/Downloads/房角OCT-左眼.pdf"
    # file_path = "/Users/gaoyanliang/Downloads/黄斑OCT.pdf"
    # file_path = "/Users/gaoyanliang/Downloads/频域前节OCT拱高测量-右眼.pdf"
    # file_path = "/Users/gaoyanliang/Downloads/频域前节OCT拱高测量-左眼.pdf"
    # file_path = "/Users/gaoyanliang/Downloads/前节OCT-右眼.pdf"
    # file_path = "/Users/gaoyanliang/Downloads/前节OCT-左眼.pdf"
    # file_path = "/Users/gaoyanliang/Downloads/血流OCT-右眼.pdf"
    # file_path = "/Users/gaoyanliang/Downloads/血流OCT-左眼.pdf"
    # file_path = "/Users/gaoyanliang/Downloads/视神经OCT.pdf"
    #
    # final_file_name, machine, values = analysis_pdf(file_path)
    # print(final_file_name)
    # print(machine)
    # print(values)


    # data = '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'
    # print(ocr_captcha(data))




