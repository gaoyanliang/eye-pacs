# pdf 文件解析，定时执行

import json

import numpy as np
from datetime import datetime
from PIL import Image
from paddleocr import PaddleOCR
import time
import io
import os
from typing import Union, List, Dict
from pdf2image import convert_from_path
import re
import cv2
from typing import Optional

from gylmodules import global_config
from gylmodules.utils.db_utils import DbUtil


def pdf_to_jpg(pdf_path, output_dir=os.path.join(os.path.dirname(__file__), "output_jpg"), dpi=300):
    """
    将 PDF 转换为 JPG 格式图片。
    """
    try:
        # 获取 PDF 文件名（不含扩展名）
        pdf_filename = os.path.splitext(os.path.basename(pdf_path))[0]
        # 确保输出目录存在
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        if global_config.run_in_local:
            poppler_path = "/opt/homebrew/bin"  # 确保与 pdftoppm 路径一致\
            images = convert_from_path(pdf_path, dpi=dpi, fmt='jpg', poppler_path=poppler_path)
        else:
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


def delete_files(file_paths):
    """
    根据给定的文件路径删除文件。
    """
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
        self.language_map = {
            'ch': {'lang': 'ch', 'cls_model_dir': None},  # macOS建议禁用分类器
            'en': {'lang': 'en', 'cls_model_dir': None},
            'multi': {'lang': 'ch_en', 'cls_model_dir': None}
        }

    @property
    def ocr_engine(self):
        """macOS优化版引擎初始化"""
        if self._ocr_engine is None:
            try:
                if global_config.run_in_local:
                    self._ocr_engine = PaddleOCR(lang='ch', use_angle_cls=False,
                                                 use_gpu=False, enable_mkldnn=False, show_log=False,
                                                 det_model_dir='/Users/gaoyanliang/nsyy/eye-pacs/gylmodules/eye_hospital_pacs/inference/ch_ppocr_server_v2.0_det_infer/',
                                                 rec_model_dir='/Users/gaoyanliang/nsyy/eye-pacs/gylmodules/eye_hospital_pacs/inference/ch_ppocr_server_v2.0_rec_infer/',
                                                 rec_char_dict_path='/Users/gaoyanliang/nsyy/eye-pacs/gylmodules/eye_hospital_pacs/inference/ppocr_keys_v1.txt',
                                                 cls_model_dir=None  # 显式禁用分类模型
                                                 )
                else:
                    # self._ocr_engine = PaddleOCR(lang='ch', use_angle_cls=False,
                    #                              use_gpu=False, enable_mkldnn=False, show_log=False,
                    #                              det_model_dir='/home/nsyy/eye-pacs/inference/ch_PP-OCRv4_det_infer/',
                    #                              rec_model_dir='/home/nsyy/eye-pacs/inference/ch_PP-OCRv4_rec_infer/',
                    #                              cls_model_dir=None  # 显式禁用分类模型
                    #                              )
                    self._ocr_engine = PaddleOCR(
                        # 硬件配置
                        lang='ch', use_gpu=True, gpu_mem=7000,  # 7GB显存限制

                        # 模型选择（平衡速度与精度）
                        det_model_dir='/home/nsyy/eye-pacs/inference/ch_PP-OCRv4_det_infer/',
                        rec_model_dir='/home/nsyy/eye-pacs/inference/ch_PP-OCRv4_rec_infer/',
                        cls_model_dir=None,  # 禁用方向分类（PDF通常方向固定）

                        # ===== 性能优化 =====
                        det_limit_side_len=2048,  # 提高分辨率适应高清扫描件
                        rec_batch_num=8,  # 增大批次（RTX 4060显存充足）
                        use_tensorrt=True,  # 启用TensorRT加速（RTX 40系列支持）

                        # ===== 质量参数 =====
                        det_db_score_mode="fast",  # 快速检测模式
                        show_log=False,  # 关闭日志减少I/O
                        use_angle_cls=False,  # 禁用方向分类（提升速度）
                        use_mp=True,  # 启用多进程
                        total_process_num=4,  # 6进程（根据CPU核心数调整）

                        # ===== 高级优化 =====
                        enable_mkldnn=False,  # 禁用Intel加速（GPU优先）
                        cpu_threads=4,  # CPU线程数（若GPU满载可辅助）
                        det_algorithm='DB',  # 使用DB算法（默认最优）
                        rec_algorithm='SVTR_LCNet'  # PP-OCRv4的轻量识别算法
                    )
            except Exception as e:
                print(datetime.now(), f"初始化失败: {str(e)}")
                raise
        return self._ocr_engine

    def load_image(self, image_input: Union[str, np.ndarray, bytes]) -> np.ndarray:
        """macOS专属图像加载方法"""
        try:
            # 处理UNIX路径格式
            if isinstance(image_input, str):
                with open(image_input, 'rb') as f:
                    img = Image.open(io.BytesIO(f.read()))
                    # 处理macOS截图可能带有alpha通道的情况
                    if img.mode in ('RGBA', 'LA'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[-1])
                        img = background
                    else:
                        img = img.convert('RGB')

            # 其他类型处理与Windows版相同
            elif isinstance(image_input, bytes):
                img = Image.open(io.BytesIO(image_input)).convert('RGB')
            elif isinstance(image_input, np.ndarray):
                img = Image.fromarray(image_input)
                if img.mode != 'RGB':
                    img = img.convert('RGB')

            return np.array(img)
        except Exception as e:
            print(datetime.now(), f"图像加载失败: {str(e)}")
            raise


    def preprocess_image(self, image_array: np.ndarray) -> np.ndarray:
        """增强图像质量以提高OCR准确率"""
        # 转换为灰度图
        if len(image_array.shape) == 3:
            gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = image_array

        # 应用锐化滤波器
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        sharpened = cv2.filter2D(gray, -1, kernel)

        # 二值化处理
        _, binary = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        return binary


    def ocr_image(self, image_input: Union[str, np.ndarray, bytes], language: str = 'ch', merge_level: int = 0) -> Dict:
        """优化版OCR方法，merge_level 默认设为 0 以保留原始顺序"""
        ret_data = {"code": 20000, "data": []}

        try:
            # 1. 加载图像
            img_array = self.load_image(image_input)

            # 图像预处理
            processed_img = self.preprocess_image(img_array)

            # 2. 执行OCR
            ocr_result = self.ocr_engine.ocr(processed_img, cls=False)

            # 3. 处理结果
            if ocr_result and ocr_result[0]:
                # 按 Y 坐标分组并排序
                sorted_lines = sorted(ocr_result[0], key=lambda x: (sum(p[1] for p in x[0]) / 4, x[0][0][0]))

                # 按 Y 坐标分组，组内按 X 坐标排序
                current_y = None
                grouped_lines = []
                for line in sorted_lines:
                    avg_y = sum(p[1] for p in line[0]) / 4
                    if current_y is None or abs(avg_y - current_y) > 10:  # 10 像素为 Y 坐标分组阈值，可调整
                        grouped_lines.append([])
                        current_y = avg_y
                    grouped_lines[-1].append(line)

                # 组内按 X 坐标排序
                for group in grouped_lines:
                    group.sort(key=lambda x: x[0][0][0])  # 按左上角 X 坐标排序

                # 展平分组结果
                sorted_lines = [item for sublist in grouped_lines for item in sublist]

                for line in sorted_lines:
                    if len(line) >= 2:
                        points, (text, confidence) = line
                        ret_data["data"].append({
                            "text": text.strip(),
                            "confidence": float(confidence),
                            "position": [list(map(int, p)) for p in points],
                            'y_position': sum(p[1] for p in points) / 4
                        })

                # 仅在需要时合并（merge_level > 0）
                if merge_level > 0:
                    ret_data["data"] = self._mac_merge_lines(ret_data["data"], level=merge_level)

                # # 调试信息（可选）
                # for item in ret_data["data"]:
                #     print(f"Text: {item['text']}, Y: {item['y_position']}, X: {item['position'][0][0]}")

            return ret_data

        except Exception as e:
            print(datetime.now(), f"OCR处理失败: {str(e)}")
            return {"code": 50000, "error": str(e)}

    def _mac_merge_lines(self, text_blocks: List[Dict], level: int = 1) -> List[Dict]:
        """
        macOS专属文本合并策略  level参数: 0 - 不合并  1 - 行合并（默认） 2 - 段落合并（适合多栏文本）
        """
        if level == 0 or len(text_blocks) <= 1:
            return text_blocks

        # 按Y坐标排序（考虑macOS的Retina显示屏高DPI特性）
        sorted_blocks = sorted(
            text_blocks,
            key=lambda x: (sum(p[1] for p in x["position"]) / 4, x["position"][0][0])
        )

        merged = []
        current = sorted_blocks[0]

        for block in sorted_blocks[1:]:
            c_box = np.array(current["position"])
            n_box = np.array(block["position"])

            # 计算垂直重叠（macOS需要更宽松的阈值）
            y_overlap = min(c_box[:, 1].max(), n_box[:, 1].max()) - max(c_box[:, 1].min(), n_box[:, 1].min())
            min_height = min(c_box[:, 1].max() - c_box[:, 1].min(), n_box[:, 1].max() - n_box[:, 1].min())

            # 合并条件判断
            if (y_overlap > min_height * 0.3 and  # 宽松垂直重叠条件
                    (n_box[0, 0] - c_box[1, 0]) < (c_box[1, 0] - c_box[0, 0]) * 2.5):  # 动态水平间距阈值

                # 合并文本框
                new_pos = [
                    [min(c_box[0, 0], n_box[0, 0]), min(c_box[0, 1], n_box[0, 1])],
                    [max(c_box[1, 0], n_box[1, 0]), min(c_box[1, 1], n_box[1, 1])],
                    [max(c_box[2, 0], n_box[2, 0]), max(c_box[2, 1], n_box[2, 1])],
                    [min(c_box[3, 0], n_box[3, 0]), max(c_box[3, 1], n_box[3, 1])]
                ]
                sep = ' ' if level == 1 else '\n'  # 段落合并换行
                current = {
                    "text": current["text"] + sep + block["text"],
                    "confidence": min(current["confidence"], block["confidence"]),
                    "position": new_pos
                }
            else:
                merged.append(current)
                current = block

        merged.append(current)
        return merged



def analysis_pdf(file_path):
    """
    解析pdf文件，并返回患者名字以及需要提取的数据
    非pdf文件不进行解析
    :param file_path:
    :return:
    """
    file_name = os.path.basename(file_path)
    if not file_path.endswith(".pdf") and not (str(file_name).startswith("角膜内皮细胞报告")
                                               or str(file_name).startswith("屈光四图")
                                               or str(file_name).startswith("OD")
                                               or str(file_name).startswith("OS")
                                               or str(file_name).startswith("角膜地形图")):
        return None, {}

    try:
        start_time = time.time()
        # 将pdf文件转换为图片，方便解析, 如果pdf有多页，则会生成多个图片，默认取第一张
        saved_jpgs = pdf_to_jpg(file_path)
        print(datetime.now(), f'{file_path} 已转换为图片，数量 {len(saved_jpgs)}, 耗时 {time.time() - start_time} 秒')
        start_time = time.time()

        # 解析图片，识别患者姓名 & 提取数据
        file_name = os.path.basename(file_path)
        processor = OCRProcessor()

        result = {}
        if str(file_name).startswith("角膜内皮细胞报告"):
            img = Image.open(saved_jpgs[0])
            regions = [
                (330, 430, 2200, 550),
                (1250, 1080, 1650, 1280),
                (1250, 2380, 1650, 2580),
            ]
            ret_str = ""
            for region in regions:
                left, top, right, bottom = region
                crop_box = (left, top, right, bottom)
                try:
                    roi = img.crop(crop_box)
                    ocr_result = processor.ocr_image(np.array(roi))
                    all_texts = [item["text"] for item in ocr_result.get("data", [])]
                    joined_text = " ".join(all_texts)
                    # print(joined_text)
                    ret_str = ret_str + joined_text + '  '
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')

            def extract_name_and_cd(text: str) -> dict:
                """从文本中提取姓名和CD值"""
                result = {"name": '', "r_cd": '', 'l_cd': ''}
                name_match = re.search(r'姓名[：:\s]*([\u4e00-\u9fa5]{2,4})', text)
                if name_match:
                    result["name"] = name_match.group(1)
                # 提取CD值（支持 CD 1234 或 CD:1234 等形式）
                cd_matches = re.findall(r'CD[：:\s]*(\d+)', text, re.IGNORECASE)
                if cd_matches:
                    result['r_cd'] = cd_matches[0]
                    result['l_cd'] = cd_matches[1] if len(cd_matches) > 1 else ''
                return result

            result = extract_name_and_cd(ret_str)

        elif str(file_name).startswith("屈光四图"):
            img = Image.open(saved_jpgs[0])
            regions = [
                (50, 1150, 700, 1450),
                (60, 1450, 700, 1710),
                (60, 2250, 700, 2500),
            ]
            ret_str = ""
            for region in regions:
                left, top, right, bottom = region
                crop_box = (left, top, right, bottom)
                try:
                    roi = img.crop(crop_box)
                    ocr_result = processor.ocr_image(np.array(roi))
                    all_texts = [item["text"] for item in ocr_result.get("data", [])]
                    joined_text = " ".join(all_texts)
                    # print(joined_text)
                    ret_str = ret_str + joined_text + '  '
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')

            def extract_eye_exam_data(text: str) -> Dict[str, Optional[str]]:
                """
                从眼科检查文本中提取关键信息（包含眼睛位置和时间）
                """
                result = {}
                # 1. 提取姓名（姓 + 名）
                surname_match = re.search(r'姓[：:\s]*([A-Za-z]+)', text)
                given_name_match = re.search(r'名[：:\s]*([A-Za-z]+)', text)
                if surname_match and given_name_match:
                    result["name"] = f"{surname_match.group(1)}{given_name_match.group(1)}"

                # 2. 提取眼睛位置

                eye_match = re.search(r'眼睛[：:\s]*(左眼|右眼)', text)
                if eye_match:
                    result["eye"] = eye_match.group(1)

                eye = 'l_' if result["eye"] == '左眼' else 'r_'

                # 4. 提取K1值（字符串格式）
                k1_match = re.search(r'K1[：:\s]*([\d\.]+)\s*D?', text)
                if k1_match:
                    result[f"{eye}k1"] = k1_match.group(1)

                # 5. 提取K2值（字符串格式）
                k2_match = re.search(r'K2[：:\s]*([\d\.]+)\s*D?', text)
                if k2_match:
                    result[f"{eye}k2"] = k2_match.group(1)

                # 6. 提取RM值（字符串格式）
                rm_match = re.search(r'Rm[：:\s]*([\d\.]+)\s*毫?米?', text)
                if rm_match:
                    result[f"{eye}rm"] = rm_match.group(1)

                # 7. 提取最薄点位置（字符串格式）
                thinnest_match = re.search(r'最薄点位置[：:\s]*(\d+)\s*微?米?', text)
                if thinnest_match:
                    result[f"{eye}thinnest_point"] = thinnest_match.group(1)

                return result

            result = extract_eye_exam_data(ret_str)

        elif str(file_name).startswith("角膜地形图"):
            img = Image.open(saved_jpgs[0])
            regions = [
                (50, 150, 1100, 300),
                (50, 1600, 1100, 2000),
                (1750, 1600, 2800, 2000),
            ]

            ret_str = ""
            for region in regions:
                left, top, right, bottom = region
                crop_box = (left, top, right, bottom)
                try:
                    roi = img.crop(crop_box)
                    ocr_result = processor.ocr_image(np.array(roi))
                    all_texts = [item["text"] for item in ocr_result.get("data", [])]
                    joined_text = " ".join(all_texts)
                    # print(joined_text)
                    ret_str = ret_str + joined_text + '  '
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')

            def extract_corneal_data(text: str) -> Dict[str, List[str]]:
                """从角膜地形图文本中提取关键信息"""
                result = {}
                # 1. 提取姓名（中文姓名）
                name_match = re.search(r'^([\u4e00-\u9fa5]{2,4})', text)
                if name_match:
                    result["name"] = name_match.group(1)

                # 2. 提取平K值（多个）
                flat_k_matches = re.findall(r'平K\s*([\d\.]+)', text)
                if flat_k_matches:
                    result['r_pk1'] = flat_k_matches[0]
                    result['l_pk1'] = flat_k_matches[1] if len(flat_k_matches) > 1 else ''

                # 3. 提取陡K值（多个）
                steep_k_matches = re.findall(r'陡K\s*([\d\.]+)', text)
                if steep_k_matches:
                    result["r_xk2"] = steep_k_matches[0]
                    result["l_xk2"] = steep_k_matches[1] if len(steep_k_matches) > 1 else ''

                # 4. 提取平面e值（多个）
                flat_e_matches = re.findall(r'平面e\s*([\d\.]+)', text)
                if flat_k_matches:
                    result["r_pe"] = flat_e_matches[0]
                    result["l_pe"] = flat_e_matches[1] if len(flat_e_matches) > 1 else ''

                return result

            result = extract_corneal_data(ret_str)

        elif str(file_name).__contains__("OD") or str(file_name).__contains__("OS"):
            img = Image.open(saved_jpgs[0])
            regions = [
                (300, 940, 1200, 1100),
                (400, 1350, 1600, 1450),
                (300, 1555, 1200, 1625),
                (1425, 700, 2380, 780),
                (1425, 940, 2380, 1020),
            ]
            ret_str = ""
            for region in regions:
                left, top, right, bottom = region
                crop_box = (left, top, right, bottom)
                try:
                    roi = img.crop(crop_box)
                    ocr_result = processor.ocr_image(np.array(roi))
                    all_texts = [item["text"] for item in ocr_result.get("data", [])]
                    joined_text = " ".join(all_texts)
                    # print(joined_text)
                    ret_str = ret_str + joined_text + '  '
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')

            def extract_corneal_data(text: str) -> Dict[str, List[str]]:
                """从阿玛仕手术报告文本中提取关键信息"""
                result = {}
                eye_type = 'od' if str(file_name).__contains__('OD') else 'os'
                # 角膜曲率
                d_match = re.findall(r"(\d+,\d+)\s+D", text)
                if d_match:
                    d_match = d_match[:2]
                    d_match = ",".join(d_match)
                result[f'corneal_curvate_{eye_type}'] = d_match if d_match else ''

                # 屈光度
                name_match = re.search(r"(-?\d+,\d+\s+D\s+-?\d+,\d+\s+Dx\s*\d+)", text)
                result[f"diopter_{eye_type}"] = name_match.group(1) if name_match else ''
                result[f"light_area_{eye_type}"] = re.search(r"(\d+,\d+\s+mm)", text).group(1) if re.search(r"(\d+,\d+\s+mm)", text) else ''
                result[f"cut_depth_{eye_type}"] = re.search(r"(\d+\s+um)", text).group(1) if re.search(r"(\d+\s+um)", text) else ''
                result[f"cut_time_{eye_type}"]  = re.search(r"(\d+\s+s)", text).group(1) if re.search(r"(\d+\s+s)", text) else ''
                result['name'] = ''
                return result

            result = extract_corneal_data(ret_str)

        delete_files(saved_jpgs)
        return result.get('name', ''), result
    except Exception as e:
        print(datetime.now(), f"解析文件 {file_path} 失败: {e}")
        return None, {}


def regularly_parsing_eye_report():
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)
    report_list = db.query_all(f"SELECT * FROM nsyy_gyl.ehp_reports "
                               f"WHERE report_value is null ORDER BY report_time limit 5")

    try:
        value_list = []
        for report in report_list:
            file_path = report.get('report_addr').replace('&', '/')
            if not os.path.exists(file_path) and not str(file_path).endswith(".pdf"):
                continue

            patient_name, values = analysis_pdf(file_path)

            report_name = f"{patient_name}_{report.get('report_name')}" if patient_name else report.get('report_name')
            report_value = json.dumps(values, ensure_ascii=False, default=str) if values else ''
            db.execute(f"UPDATE nsyy_gyl.ehp_reports SET report_name = '{report_name}', report_value = '{report_value}' "
                       f"WHERE report_id = {report.get('report_id')}", need_commit=True)
    except Exception as e:
        del db
        raise Exception(e)
    del db


# macOS环境检测
if __name__ == "__main__":
    start_time = time.time()

    # pdf_file = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/代码/4.pdf"
    # # pdf_file = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/代码/5.pdf"
    # patient_name, values = analysis_pdf(pdf_file)
    #
    # print("患者姓名: ", patient_name)
    # # print("识别结果: ", values)
    # for k, v in values.items():
    #     print(k, ": ", v)
    # print("PDF 识别完成，耗时:", time.time() - start_time, "秒")

    # pdf_file = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/205-北 眼前节测量评估系统/ODpentacam四图.pdf"  # 替换为你的 PDF 文件路径
    # pdf_file = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/204角膜地形图仪/干眼检查报告1.pdf"  # 替换为你的 PDF 文件路径

    # pdf_file = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/塑形镜验配图.pdf"
    # pdf_file = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/202角膜内皮显微镜/202 角膜内皮细胞报告.pdf"
    pdf_file = "/Users/gaoyanliang/Downloads/bi_qianxi_2025021003_OS_2025-02-10__18-26-12.pdf"
    output_directory = "."  # 替换为你的输出目录
    saved_jpgs = pdf_to_jpg(pdf_file, output_directory)
    print("转换完成的 JPG 文件完整路径:")
    for path in saved_jpgs:
        print(path)

    print("PDF 转换 JPG 完成，耗时:", round(time.time() - start_time, 2), "秒")

    # 使用示例
    processor = OCRProcessor()

    # 示例1: 识别PNG截图（处理透明背景）
    # result = processor.ocr_image(r"/Users/gaoyanliang/Downloads/L角膜OCT.jpg", merge_level=2)
    # result = processor.ocr_image(saved_jpgs[0], merge_level=2)

    # # 示例2: 识别PDF转换的图片
    # with open(saved_jpgs[0], "rb") as f:
    #     result = processor.ocr_image(f.read(), language='en')

    # 方式3 按坐标解析
    img = Image.open(saved_jpgs[0])

    regions = [
        (300, 940, 1200, 1100),
        (400, 1350, 1600, 1450),
        (300, 1555, 1200, 1625),
        (1425, 700, 2380, 780),
        (1425, 940, 2380, 1020),
    ]
    ret_str = ''
    for region in regions:
        left, top, right, bottom = region
        crop_box = (left, top, right, bottom)
        try:
            # 裁剪感兴趣区域
            roi = img.crop(crop_box)
            # OCR识别
            ocr_result = processor.ocr_image(np.array(roi))

            all_texts = [item["text"] for item in ocr_result.get("data", [])]
            joined_text = " ".join(all_texts)
            ret_str = ret_str + joined_text +  "  "

        except Exception as e:
            print(e)

    print(ret_str)

    # # 假设你的感兴趣区域是这段
    # # crop_box = (60, 1160, 700, 1440)  # (left, top, right, bottom)
    # # crop_box = (60, 1600, 1100, 2000)  # (left, top, right, bottom)
    # # crop_box = (1750, 1600, 2800, 2000)  # (left, top, right, bottom)
    # crop_box = (50, 140, 1000, 280)  # (left, top, right, bottom)
    # roi = img.crop(crop_box)
    # # 转成 numpy 数组再 OCR
    # result = processor.ocr_image(np.array(roi))

    # ====== 屈光四图
    # for item in result.get("data", []):
    #     print(f"{item['text']}")
    #
    #     if extract_name_from_text(item['text']):
    #         print('=========== Name: ', extract_name_from_text(item['text']))
    #     print(f"位置坐标:  {item['position']}")
    #     print()
    #     print()


    # all_texts = [item["text"] for item in result.get("data", [])]
    # joined_text = " ".join(all_texts)
    # print(joined_text)
    # fields = extract_quguang(joined_text)
    # print(fields)
    #
    # all_texts = [item["text"] for item in result.get("data", [])]
    # joined_text = " ".join(all_texts)
    # joined_text = joined_text.replace('\n', ' ')
    # print('完整输出: ', joined_text)
    # print("姓名", extract_surname_givenname(joined_text))
    # print(extract_name_from_text(joined_text))
    #
    # fields = extract_k_values(joined_text)
    # print(fields)
    #
    # result = extract_k_values_from_text(joined_text)
    # print(result)
    #
    print("识别完成，耗时:", round(time.time() - start_time, 2), "秒")
    # # delete_files(saved_jpgs)
