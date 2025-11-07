# pdf 文件解析，定时执行

import json
import re

from pathlib import Path
import numpy as np
from datetime import datetime
from PIL import Image
from paddleocr import PaddleOCR
import time
import io
import os
from typing import Union, List, Dict, Literal
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
        self.language_map = {
            'ch': {'lang': 'ch', 'cls_model_dir': None},  # macOS建议禁用分类器
            'en': {'lang': 'en', 'cls_model_dir': None},
            'multi': {'lang': 'ch_en', 'cls_model_dir': None}
        }

    """macOS优化版引擎初始化"""
    @property
    def ocr_engine(self):
        if self._ocr_engine is None:
            try:
                if global_config.run_in_local:
                    self._ocr_engine = PaddleOCR(lang='ch', use_angle_cls=False,
                                                 use_gpu=False, enable_mkldnn=False, show_log=False,
                                                 det_model_dir=r'C:\Users\Administrator\Desktop\eye-pacs\gylmodules\eye_hospital_pacs\inference\ch_ppocr_server_v2.0_det_infer',
                                                 rec_model_dir=r'C:\Users\Administrator\Desktop\eye-pacs\gylmodules\eye_hospital_pacs\inference\ch_ppocr_server_v2.0_rec_infer',
                                                 rec_char_dict_path=r'C:\Users\Administrator\Desktop\eye-pacs\gylmodules\eye_hospital_pacs\inference\ppocr_keys_v1.txt',
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
                        rec_char_dict_path='/home/nsyy/eye-pacs/inference/ppocr_keys_v1.txt',
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

    """macOS专属图像加载方法"""

    def load_image(self, image_input: Union[str, np.ndarray, bytes]) -> np.ndarray:
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

    """增强图像质量以提高OCR准确率"""
    def preprocess_image(self, image_array: np.ndarray) -> np.ndarray:
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

        # 降噪处理
        # deionised = cv2.medianBlur(binary, 3)

        return binary

    """优化版OCR方法，merge_level 默认设为 0 以保留原始顺序"""
    def ocr_image(self, image_input: Union[str, np.ndarray, bytes], language: str = 'ch', merge_level: int = 0) -> Dict:
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
                    ret_data["data"] = self._merge_lines(ret_data["data"], level=merge_level)

                # # 调试信息（可选）
                # for item in ret_data["data"]:
                #     print(f"Text: {item['text']}, Y: {item['y_position']}, X: {item['position'][0][0]}")

            return ret_data

        except Exception as e:
            print(datetime.now(), f"OCR处理失败: {str(e)}")
            return {"code": 50000, "error": str(e)}

    """macOS专属文本合并策略  level参数: 0 - 不合并  1 - 行合并（默认） 2 - 段落合并（适合多栏文本）"""
    def _merge_lines(self, text_blocks: List[Dict], level: int = 1) -> List[Dict]:
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
    img = Image.open(saved_jpgs[0])
    for name, info in ehp_config.report_logo.items():
        region = info.get('logo')
        left, top, right, bottom = region
        crop_box = (left, top, right, bottom)
        try:
            roi = img.crop(crop_box)
            ocr_result = processor.ocr_image(np.array(roi))
            all_texts = [item["text"] for item in ocr_result.get("data", [])]
            joined_text = " ".join(all_texts)
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
        except Exception as e:
            print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
    return '', "未收录设备"


"""解析pdf文件，并返回患者名字以及需要提取的数据"""


def analysis_pdf(file_path):
    if not file_path.endswith(".pdf"):
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {file_path} 非pdf报告无法解析")
        return None, {}
    try:
        start_time = time.time()
        # 将pdf文件转换为图片，方便解析, 如果pdf有多页，则会生成多个图片，默认取第一张
        saved_jpgs = pdf_to_jpg(file_path)
        to_jpg_time = time.time() - start_time

        # 解析图片，识别患者姓名 & 提取数据
        processor = OCRProcessor()

        # 解析并判断文件类型
        ret_data = {}
        analy_name, machine = analysis_report_types(saved_jpgs, processor)
        final_file_name = analy_name if analy_name else Path(file_path).stem
        if analy_name.__contains__('屈光四图'):
            # 区分横版/竖版
            if analy_name.__contains__('竖'):
                regions = {
                    "xing": (260, 1172, 670, 1215), "ming": (260, 1220, 670, 1255), "eye": (540, 1310, 680, 1345),
                    "k1": (550, 1525, 680, 1560), "k2": (550, 1587, 680, 1623), "rm": (312, 1650, 440, 1685),
                    "thinnest_point": (310, 2378, 445, 2412), "depth": (575, 2499, 680, 2535),
                    "distance": (310, 2620, 440, 2655)
                }
            else:
                regions = {
                    "xing": (538, 519, 980, 563), "ming": (538, 576, 980, 620), "eye": (885, 690, 1020, 735),
                    "k1": (900, 960, 1055, 1000), "k2": (900, 1035, 1055, 1080), "rm": (600, 1113, 765, 1157),
                    "thinnest_point": (603, 2018, 765, 2060), "depth": (600, 2315, 766, 2360),
                    "distance": (927, 2167, 1055, 2210)
                }
            for key, region in regions.items():
                left, top, right, bottom = region
                crop_box = (left, top, right, bottom)
                try:
                    img = Image.open(saved_jpgs[0])
                    roi = img.crop(crop_box)
                    ocr_result = processor.ocr_image(np.array(roi))
                    all_texts = [item["text"] for item in ocr_result.get("data", [])]
                    ret_data[key] = " ".join(all_texts)
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')

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
                left, top, right, bottom = region
                crop_box = (left, top, right, bottom)
                try:
                    img = Image.open(saved_jpgs[0])
                    roi = img.crop(crop_box)
                    ocr_result = processor.ocr_image(np.array(roi))
                    all_texts = [item["text"] for item in ocr_result.get("data", [])]
                    ret_data[key] = " ".join(all_texts)
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
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
                crop_box = (1980, 640, 2155, 690)
                img = Image.open(saved_jpgs[0])
                ocr_result = processor.ocr_image(np.array(img.crop(crop_box)))
                all_texts = [item["text"] for item in ocr_result.get("data", [])]
                tmp_text = " ".join(all_texts).replace(" ", "")
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
                    left, top, right, bottom = region
                    crop_box = (left, top, right, bottom)
                    try:
                        img = Image.open(saved_jpgs[0])
                        roi = img.crop(crop_box)
                        ocr_result = processor.ocr_image(np.array(roi))
                        all_texts = [item["text"] for item in ocr_result.get("data", [])]
                        ret_data[key] = " ".join(all_texts)
                    except Exception as e:
                        print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')

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
                    "name": (55, 150, 700, 220), "r_pk1": (450, 1600, 1080, 1670), "r_xk2": (450, 1670, 1080, 1735),
                    "r_dk3": (450, 1740, 1080, 1800), "r_pe": (450, 1800, 1080, 1870),
                    "l_pk1": (2150, 1600, 2800, 1670),
                    "l_xk2": (2150, 1670, 2800, 1735), "l_dk3": (2150, 1740, 2800, 1800),
                    "l_pe": (2150, 1800, 2800, 1870)
                }
            for key, region in regions.items():
                left, top, right, bottom = region
                crop_box = (left, top, right, bottom)
                try:
                    img = Image.open(saved_jpgs[0])
                    roi = img.crop(crop_box)
                    ocr_result = processor.ocr_image(np.array(roi))
                    all_texts = [item["text"] for item in ocr_result.get("data", [])]
                    ret_data[key] = " ".join(all_texts)
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')

            match = re.search(r'[：:]\s*([\u4e00-\u9fa5]{2,4}|[A-Za-z\s]+)', ret_data.get("name", ""))
            if match:
                ret_data['name'] = match.group(1).strip()
            ret_data['name'] = ret_data.get("name", "").replace(' ', '').replace(',', '') \
                .replace('，', '').replace('.', '').replace('。', '')

            if 'r_pk1' in ret_data:
                match = re.search(r'([\d.]+)屈光度', ret_data.get('r_pk1', ''))
                ret_data['r_pk1'] = match.group(1) if match else ret_data.get('r_pk1', '')
                match = re.search(r'([\d.]+)屈光度', ret_data.get('l_pk1', ''))
                ret_data['l_pk1'] = match.group(1) if match else ret_data.get('l_pk1', '')
                match = re.search(r'([\d.]+)屈光度', ret_data.get('r_xk2', ''))
                ret_data['r_xk2'] = match.group(1) if match else ret_data.get('r_xk2', '')
                match = re.search(r'([\d.]+)屈光度', ret_data.get('l_xk2', ''))
                ret_data['l_xk2'] = match.group(1) if match else ret_data.get('l_xk2', '')
                match = re.search(r'([\d.]+)\s*@', ret_data.get('r_pe', ''))
                ret_data['r_pe'] = match.group(1) if match else ret_data.get('r_pe', '')
                match = re.search(r'([\d.]+)\s*@', ret_data.get('l_pe', ''))
                ret_data['l_pe'] = match.group(1) if match else ret_data.get('l_pe', '')
            if not ret_data.get('r_pk1', '') and  not ret_data.get('l_pk1', '') and not ret_data.get('r_pe', '') and  not ret_data.get('l_pe', ''):
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
                left, top, right, bottom = region
                crop_box = (left, top, right, bottom)
                try:
                    img = Image.open(saved_jpgs[0])
                    roi = img.crop(crop_box)
                    ocr_result = processor.ocr_image(np.array(roi))
                    all_texts = [item["text"] for item in ocr_result.get("data", [])]
                    ret_data[key] = " ".join(all_texts)
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
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
                left, top, right, bottom = region
                crop_box = (left, top, right, bottom)
                try:
                    img = Image.open(saved_jpgs[0])
                    roi = img.crop(crop_box)
                    ocr_result = processor.ocr_image(np.array(roi))
                    all_texts = [item["text"] for item in ocr_result.get("data", [])]
                    ret_data[key] = " ".join(all_texts)
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
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
                left, top, right, bottom = region
                crop_box = (left, top, right, bottom)
                try:
                    img = Image.open(saved_jpgs[0])
                    roi = img.crop(crop_box)
                    ocr_result = processor.ocr_image(np.array(roi))
                    all_texts = [item["text"] for item in ocr_result.get("data", [])]
                    ret_data[key] = " ".join(all_texts)
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
            ret_data['name'] = ret_data.get('name', '').replace(' ', '').replace(',', '') \
                .replace('，', '').replace('.', '').replace('。', '')
        elif analy_name.__contains__('Master700'):
            index = 0
            is_success = True
            for item in saved_jpgs:
                img = Image.open(item)
                ret_str = ""
                try:
                    roi = img.crop((950, 930, 1600, 1090))
                    ocr_result = processor.ocr_image(np.array(roi))
                    all_texts = [item["text"] for item in ocr_result.get("data", [])]
                    joined_text = " ".join(all_texts)
                    ret_str = ret_str + joined_text + '  '
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
                    left, top, right, bottom = region
                    crop_box = (left, top, right, bottom)
                    try:
                        img = Image.open(saved_jpgs[index])
                        roi = img.crop(crop_box)
                        ocr_result = processor.ocr_image(np.array(roi))
                        all_texts = [item["text"] for item in ocr_result.get("data", [])]
                        ret_data[key] = " ".join(all_texts)
                    except Exception as e:
                        print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
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
                    "p_k1": (680, 960, 1110, 1025), "p_k2": (680, 1025, 1110, 1090), "diopter": (680, 1360, 1330, 1430),
                    "light_area": (1925, 710, 2380, 780), "cut_depth": (1925, 940, 2380, 1020),
                    "cut_time": (700, 1560, 1200, 1625)
                }
            for key, region in regions.items():
                left, top, right, bottom = region
                crop_box = (left, top, right, bottom)
                try:
                    img = Image.open(saved_jpgs[0])
                    roi = img.crop(crop_box)
                    ocr_result = processor.ocr_image(np.array(roi))
                    all_texts = [item["text"] for item in ocr_result.get("data", [])]
                    ret_data[key] = " ".join(all_texts)
                except Exception as e:
                    print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
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
            ret_data[f'diopter_{eye_type}'] = ret_data.pop('diopter', '')
            ret_data[f'light_area_{eye_type}'] = ret_data.pop('light_area', '')
            ret_data[f'cut_depth_{eye_type}'] = ret_data.pop('cut_depth', '')
            ret_data[f'cut_time_{eye_type}'] = ret_data.pop('cut_time', '')
        else:
           print(f"{datetime.now()} {file_path} 暂不支持解析")
    except Exception as e:
        print(f"{datetime.now()} {file_path} 解析报告异常 {e}")

    for k,v in ret_data.items():
        if str(v).endswith('s') or str(v).endswith('um') or str(v).endswith('mm') or str(v).endswith('μm') or str(v).endswith('毫米') or str(v).endswith('微米') or str(v).endswith('D')  or str(v).endswith('x') or str(v).endswith('Dx'):
            ret_data[k] = (str(v).replace('mm', '').replace('μm', '')
                           .replace('毫米', '').replace('微米', '')
                           .replace('D', '').replace('Dx', '')
                           .replace('x', '').replace('um', '').replace('s', ''))

    print(f"{datetime.now()} {file_path} 解析报告成功, to-jpg 耗时 {to_jpg_time}, 总耗时 {time.time() - start_time}")
    return final_file_name, machine, ret_data


# def analysis_pdf11(file_path):
#     if not file_path.endswith(".pdf"):
#         print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {file_path} 非pdf报告无法解析")
#         return None, {}
#     try:
#         start_time = time.time()
#         file_name = os.path.basename(file_path)
#         # 将pdf文件转换为图片，方便解析, 如果pdf有多页，则会生成多个图片，默认取第一张
#         saved_jpgs = pdf_to_jpg(file_path)
#         to_jpg_time = time.time() - start_time
#
#         # 解析图片，识别患者姓名 & 提取数据
#         file_name = os.path.basename(file_path)
#         processor = OCRProcessor()
#
#         result = {}
#         if str(file_name).startswith("角膜内皮细胞报告"):
#             img = Image.open(saved_jpgs[0])
#             if str(file_name).startswith("角膜内皮细胞报告2"):
#                 regions = [
#                     (330, 430, 2200, 550),
#                     (1110, 1120, 1580, 1310),
#                     (1110, 2400, 1580, 2600),
#                 ]
#             else:
#                 regions = [
#                     (330, 430, 2200, 550),
#                     (1250, 1080, 1650, 1280),
#                     (1250, 2380, 1650, 2580),
#                 ]
#             ret_str = ""
#             for region in regions:
#                 left, top, right, bottom = region
#                 crop_box = (left, top, right, bottom)
#                 try:
#                     roi = img.crop(crop_box)
#                     ocr_result = processor.ocr_image(np.array(roi))
#                     all_texts = [item["text"] for item in ocr_result.get("data", [])]
#                     joined_text = " ".join(all_texts)
#                     # print(joined_text)
#                     ret_str = ret_str + joined_text + '  '
#                 except Exception as e:
#                     print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
#
#             def extract_name_and_cd(text: str) -> dict:
#                 """从文本中提取姓名和CD值"""
#                 result = {"name": '', "r_cd": '', 'l_cd': ''}
#                 name_match = re.search(r'姓名[：:\s]*([\u4e00-\u9fa5]{2,4})', text)
#                 if name_match:
#                     result["name"] = name_match.group(1)
#                 # 提取CD值（支持 CD 1234 或 CD:1234 等形式）
#                 cd_matches = re.findall(r'CD[：:\s]*(\d+)', text, re.IGNORECASE)
#                 if cd_matches:
#                     result['r_cd'] = cd_matches[0]
#                     result['l_cd'] = cd_matches[1] if len(cd_matches) > 1 else ''
#                 return result
#
#             result = extract_name_and_cd(ret_str)
#
#         elif ((str(file_name).__contains__("_OD_20") or str(file_name).__contains__("_OS_20"))
#               and not str(file_name).__contains__("Maps Refr")):
#             # 阿玛仕手术报告
#             img = Image.open(saved_jpgs[0])
#             regions = [
#                 (300, 940, 1200, 1100),
#                 (400, 1350, 1600, 1450),
#                 (300, 1555, 1200, 1625),
#                 (1425, 700, 2380, 780),
#                 (1425, 940, 2380, 1020),
#             ]
#             ret_str = ""
#             for region in regions:
#                 left, top, right, bottom = region
#                 crop_box = (left, top, right, bottom)
#                 try:
#                     roi = img.crop(crop_box)
#                     ocr_result = processor.ocr_image(np.array(roi))
#                     all_texts = [item["text"] for item in ocr_result.get("data", [])]
#                     joined_text = " ".join(all_texts)
#                     # print(joined_text)
#                     ret_str = ret_str + joined_text + '  '
#                 except Exception as e:
#                     print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
#
#             def extract_corneal_data(text: str) -> Dict[str, List[str]]:
#                 """从阿玛仕手术报告文本中提取关键信息"""
#                 result = {}
#                 eye_type = 'od' if str(file_name).__contains__('OD') else 'os'
#                 # 角膜曲率
#                 d_match = re.findall(r"(\d+,\d+)\s+D", text)
#                 if d_match:
#                     d_match = d_match[:2]
#                     d_match = ",".join(d_match)
#                 result[f'corneal_curvate_{eye_type}'] = d_match if d_match else ''
#
#                 # 屈光度
#                 name_match = re.search(r"(-?\d+,\d+\s+D\s+-?\d+,\d+\s+Dx\s*\d+)", text)
#                 result[f"diopter_{eye_type}"] = name_match.group(1) if name_match else ''
#                 result[f"light_area_{eye_type}"] = re.search(r"(\d+,\d+\s+mm)", text).group(1) if re.search(r"(\d+,\d+\s+mm)", text) else ''
#                 result[f"cut_depth_{eye_type}"] = re.search(r"(\d+\s+um)", text).group(1) if re.search(r"(\d+\s+um)", text) else ''
#                 result[f"cut_time_{eye_type}"]  = re.search(r"(\d+\s+s)", text).group(1) if re.search(r"(\d+\s+s)", text) else ''
#                 result['name'] = ''
#                 return result
#
#             result = extract_corneal_data(ret_str)
#
#         elif str(file_name).startswith("屈光四图") or ((str(file_name).__contains__("OD") or
#                                                         str(file_name).__contains__("OS"))
#                                                        and str(file_name).__contains__("4 Maps Refr")):
#             orientation = get_pdf_orientation(saved_jpgs[0])
#             if orientation == 'portrait':
#                 regions = [
#                     (50, 1150, 700, 1450),
#                     (60, 1450, 700, 1710),
#                     (60, 2250, 700, 2500),
#                     (60, 2480, 700, 2670),
#                 ]
#             else:
#                 regions = [
#                     (280, 500, 1080, 860),
#                     (290, 890, 1080, 1350),
#                     (290, 1800, 1080, 2150),
#                     (290, 2150, 1080, 2370),
#                 ]
#
#             img = Image.open(saved_jpgs[0])
#             ret_str = ""
#             for region in regions:
#                 left, top, right, bottom = region
#                 crop_box = (left, top, right, bottom)
#                 try:
#                     roi = img.crop(crop_box)
#                     ocr_result = processor.ocr_image(np.array(roi))
#                     all_texts = [item["text"] for item in ocr_result.get("data", [])]
#                     joined_text = " ".join(all_texts)
#                     # print(joined_text)
#                     ret_str = ret_str + joined_text + '  '
#                 except Exception as e:
#                     print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
#
#             def extract_eye_exam_data(text: str, last_text: str) -> Dict[str, Optional[str]]:
#                 """
#                 从眼科检查文本中提取关键信息（包含眼睛位置和时间）
#                 """
#                 result = {}
#                 # 1. 提取姓名（姓 + 名）
#                 surname_match = re.search(r'姓[：:\s]*([A-Za-z]+)', text)
#                 given_name_match = re.search(r'名[：:\s]*([A-Za-z]+)', text)
#                 if surname_match and given_name_match:
#                     result["name"] = f"{surname_match.group(1)}{given_name_match.group(1)}"
#
#                 # 2. 提取眼睛位置
#
#                 eye_match = re.search(r'眼睛[：:\s]*(左眼|右眼)', text)
#                 if eye_match:
#                     result["eye"] = eye_match.group(1)
#
#                 eye = 'l_' if result["eye"] == '左眼' else 'r_'
#
#                 # 4. 提取K1值（字符串格式）
#                 k1_match = re.search(r'K1[。.：:\s]*([\d\.]+)\s*D?', text)
#                 if k1_match:
#                     result[f"{eye}k1"] = k1_match.group(1)
#
#                 # 5. 提取K2值（字符串格式）
#                 k2_match = re.search(r'K2[。.：:\s]*([\d\.]+)\s*D?', text)
#                 if k2_match:
#                     result[f"{eye}k2"] = k2_match.group(1)
#
#                 # 6. 提取RM值（字符串格式）
#                 rm_match = re.search(r'Rm[。.：:\s]*([\d\.]+)\s*毫?米?', text)
#                 if rm_match:
#                     result[f"{eye}rm"] = rm_match.group(1)
#
#                 # 7. 提取最薄点位置（字符串格式）
#                 thinnest_match = re.search(r'最薄点位置[。.：:\s]*(\d+)\s*微?米?', text)
#                 if thinnest_match:
#                     result[f"{eye}thinnest_point"] = thinnest_match.group(1)
#
#                 # 8. 提取前房深度  水平方向白到白距离
#                 # items = re.findall(r'([\d.]+)\s*(毫米3|毫米|度?)', last_text)
#                 pattern = r'([\d.]+)\s*(毫米3|毫米\.3|毫米|度?)'
#                 items = re.findall(pattern, last_text)
#                 result[f"{eye}distance"] = f"{items[1][0]}{items[1][1]}" if len(items) > 1 and len(items[1]) > 1 else ''
#                 result[f"{eye}depth"] = f"{items[4][0]}{items[4][1]}" if len(items) > 4 and len(items[4]) > 1 else ''
#                 return result
#
#             result = extract_eye_exam_data(ret_str, joined_text)
#
#         elif str(file_name).startswith("角膜地形图"):
#             img = Image.open(saved_jpgs[0])
#             regions = [
#                 (50, 150, 1100, 300),
#                 (50, 1600, 1100, 2000),
#                 (1750, 1600, 2800, 2000),
#             ]
#
#             ret_str = ""
#             for region in regions:
#                 left, top, right, bottom = region
#                 crop_box = (left, top, right, bottom)
#                 try:
#                     roi = img.crop(crop_box)
#                     ocr_result = processor.ocr_image(np.array(roi))
#                     all_texts = [item["text"] for item in ocr_result.get("data", [])]
#                     joined_text = " ".join(all_texts)
#                     # print(joined_text)
#                     ret_str = ret_str + joined_text + '  '
#                 except Exception as e:
#                     print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
#
#             def extract_corneal_data(text: str) -> Dict[str, List[str]]:
#                 """从角膜地形图文本中提取关键信息"""
#                 result = {}
#                 # 1. 提取姓名（中文姓名）
#                 name_match = re.search(r'^([\u4e00-\u9fa5]{2,4})', text)
#                 if name_match:
#                     result["name"] = name_match.group(1)
#
#                 # 2. 提取平K值（多个）
#                 flat_k_matches = re.findall(r'平K\s*([\d\.]+)', text)
#                 if flat_k_matches:
#                     result['r_pk1'] = flat_k_matches[0]
#                     result['l_pk1'] = flat_k_matches[1] if len(flat_k_matches) > 1 else ''
#
#                 # 3. 提取陡K值（多个）
#                 steep_k_matches = re.findall(r'陡K\s*([\d\.]+)', text)
#                 if steep_k_matches:
#                     result["r_xk2"] = steep_k_matches[0]
#                     result["l_xk2"] = steep_k_matches[1] if len(steep_k_matches) > 1 else ''
#
#                 # 匹配模式：△K 后跟数字和单位D
#                 k_matches = re.findall(r'△K\s*([\d.]+)\s*D', text)
#                 if k_matches:
#                     result["r_dk3"] = k_matches[0]
#                     result["l_dk3"] = k_matches[1] if len(steep_k_matches) > 1 else ''
#
#                 # 4. 提取平面e值（多个）
#                 flat_e_matches = re.findall(r'平面e\s*([\d\.]+)', text)
#                 if flat_k_matches:
#                     result["r_pe"] = flat_e_matches[0]
#                     result["l_pe"] = flat_e_matches[1] if len(flat_e_matches) > 1 else ''
#
#                 return result
#
#             result = extract_corneal_data(ret_str)
#
#         elif str(file_name).startswith("Master700"):
#             # Master 700 报告
#             for item in saved_jpgs:
#                 img = Image.open(item)
#                 ret_str = ""
#                 crop_box = (950, 930, 1600, 1090)
#                 try:
#                     roi = img.crop(crop_box)
#                     ocr_result = processor.ocr_image(np.array(roi))
#                     all_texts = [item["text"] for item in ocr_result.get("data", [])]
#                     joined_text = " ".join(all_texts)
#                     ret_str = ret_str + joined_text + '  '
#                 except Exception as e:
#                     print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {crop_box} 失败: {e}')
#                 if ret_str.__contains__("生物统计值") or ret_str.__contains__("生物") or ret_str.__contains__("生"):
#                     regions = [
#                         (250, 1360, 560, 1425),
#                         (650, 2760, 1220, 2820),
#                         (220, 2710, 600, 2770),
#                         (250, 1416, 560, 1470),
#                     ]
#                     r_ret_str = ""
#                     for region in regions:
#                         left, top, right, bottom = region
#                         crop_box = (left, top, right, bottom)
#                         try:
#                             roi = img.crop(crop_box)
#                             ocr_result = processor.ocr_image(np.array(roi))
#                             all_texts = [item["text"] for item in ocr_result.get("data", [])]
#                             joined_text = " ".join(all_texts)
#                             # print(joined_text)
#                             r_ret_str = r_ret_str + joined_text + '  '
#                         except Exception as e:
#                             print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
#
#                     regions = [
#                         (1330, 1360, 1630, 1425),
#                         (1720, 2760, 2240, 2820),
#                         (1290, 2710, 1700, 2770),
#                         (1310, 1416, 1630, 1470),
#                     ]
#                     l_ret_str = ""
#                     for region in regions:
#                         left, top, right, bottom = region
#                         crop_box = (left, top, right, bottom)
#                         try:
#                             roi = img.crop(crop_box)
#                             ocr_result = processor.ocr_image(np.array(roi))
#                             all_texts = [item["text"] for item in ocr_result.get("data", [])]
#                             joined_text = " ".join(all_texts)
#                             # print(joined_text)
#                             l_ret_str = l_ret_str + joined_text + '  '
#                         except Exception as e:
#                             print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
#
#                     def parse_biometry_data(data_string, is_left):
#                         # print(data_string)
#                         """从字符串中解析AL值和CW-chord值"""
#                         # 初始化结果字典
#                         # 初始化结果字典
#                         ret = { 'AL': [], 'CW_chord': [], "WTW": [], "CCT": []}
#
#                         # 支持中英文的AL值正则表达式
#                         al_patterns = [
#                             r'AL:\s*(\d+\.\d+)\s*mm',  # 英文格式: AL: 26.21 mm
#                             r'AL[：:]\s*(\d+\.\d+)\s*mm',  # 中文冒号: AL：26.21 mm
#                         ]
#
#                         # 支持中英文的CW-chord值正则表达式
#                         cw_patterns = [
#                             r'(?:CW-chord|角膜直径)[：:]\s*([\d\.]+)\s*(?:mm|毫米|厘米|cm)?\s*(?:@|在|角度)?\s*(\d+)(?:°|度)?'
#                         ]
#
#                         wtw_patterns = [
#                             r'WTW:\s*(\d+\.\d+)\s*mm',  # 英文格式: WTW: 26.21 mm
#                             r'WTW[：:]\s*(\d+\.\d+)\s*mm',  # 中文冒号: WTW：26.21 mm
#                         ]
#
#                         cct_patterns = [
#                             r'CCT[:：]\s*(\d+\.?\d*)'
#                         ]
#
#                         # 解析AL值
#                         for pattern in al_patterns:
#                             al_matches = re.findall(pattern, data_string)
#                             for match in al_matches:
#                                 ret['AL'].append(match)
#
#                         # 解析CW-chord值
#                         for pattern in cw_patterns:
#                             cw_matches = re.findall(pattern, data_string)
#                             for value, angle in cw_matches:
#                                 ret['CW_chord'].append(f"{value} mm @ {angle}°")
#
#                         # 解析WTW值
#                         for pattern in wtw_patterns:
#                             wtw_matches = re.findall(pattern, data_string)
#                             for match in wtw_matches:
#                                 ret['WTW'].append(match)
#
#                         # 解析CCT值
#                         for pattern in cct_patterns:
#                             cct_matches = re.findall(pattern, data_string)
#                             for match in cct_matches:
#                                 ret['CCT'].append(match)
#
#                         als = list(set(ret['AL']))
#                         cws = list(set(ret['CW_chord']))
#                         wtw = list(set(ret['WTW']))
#                         cct = list(set(ret['CCT']))
#                         if is_left:
#                             result['l_al'] = als[0] if len(als) >0 else ''
#                             result['l_cct'] = cct[0] if len(cct) >0 else ''
#                             result['l_wtw'] = wtw[0] if len(wtw) >0 else ''
#                             result['l_cw_chord'] = cws[0] if len(cws) >0 else ''
#                         else:
#                             result['r_al'] = als[0] if len(als) > 0 else ''
#                             result['r_cct'] = cct[0] if len(cct) > 0 else ''
#                             result['r_wtw'] = wtw[0] if len(wtw) > 0 else ''
#                             result['r_cw_chord'] = cws[0] if len(cws) > 0 else ''
#                         return result
#
#                     dict1 = parse_biometry_data(l_ret_str, True)
#                     dict2 = parse_biometry_data(r_ret_str, False)
#                     result = {**dict1, **dict2}
#
#                     break
#
#         elif str(file_name).startswith("眼表综合检查报告"):
#             # 眼表综合检查报告
#             img = Image.open(saved_jpgs[0])
#             regions = [
#                 (50, 310, 500, 390),
#                 (620, 500, 1000, 580),
#                 (1400, 500, 1700, 580),
#             ]
#             i = 0
#             for region in regions:
#                 left, top, right, bottom = region
#                 crop_box = (left, top, right, bottom)
#                 d = ''
#                 try:
#                     roi = img.crop(crop_box)
#                     ocr_result = processor.ocr_image(np.array(roi))
#                     all_texts = [item["text"] for item in ocr_result.get("data", [])]
#                     joined_text = "".join(all_texts)
#                     # print(joined_text)
#                     if i == 0:
#                         # 匹配中文姓名（2-4个汉字）或英文姓名（字母和空格）
#                         match = re.search(r'[：:]\s*([\u4e00-\u9fa5]{2,4}|[A-Za-z\s]+)', joined_text)
#                         if match:
#                             d = match.group(1).strip()
#                     else:
#                         d = joined_text
#                 except Exception as e:
#                     print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
#                     d = ''
#
#                 if i == 0:
#                     result["name"] = d.replace(' ', '')
#                 if i == 1:
#                     result["r_first_rupture_time"] = d
#                 if i == 2:
#                     result["l_first_rupture_time"] = d
#                 i = i + 1
#
#         elif str(file_name).startswith("比较两次检查"):
#             img = Image.open(saved_jpgs[0])
#             regions = [
#                 (540, 515, 850, 565),
#             ]
#             for region in regions:
#                 left, top, right, bottom = region
#                 crop_box = (left, top, right, bottom)
#                 try:
#                     roi = img.crop(crop_box)
#                     ocr_result = processor.ocr_image(np.array(roi))
#                     all_texts = [item["text"] for item in ocr_result.get("data", [])]
#                     d = "".join(all_texts)
#                     # print(joined_text)
#                 except Exception as e:
#                     print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
#                     d = ''
#                 result["name"] = d.replace(' ', '').replace(',', '').replace('，', '').replace('.', '').replace('。', '')
#
#         elif str(file_name).startswith("Scheimpflug图像总览"):
#             img = Image.open(saved_jpgs[0])
#             regions = [
#                 (530, 520, 850, 571),
#             ]
#             for region in regions:
#                 left, top, right, bottom = region
#                 crop_box = (left, top, right, bottom)
#                 try:
#                     roi = img.crop(crop_box)
#                     ocr_result = processor.ocr_image(np.array(roi))
#                     all_texts = [item["text"] for item in ocr_result.get("data", [])]
#                     d = "".join(all_texts)
#                     # print(joined_text)
#                 except Exception as e:
#                     print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
#                     d = ''
#                 result["name"] = d.replace(' ', '').replace(',', '').replace('，', '').replace('.', '').replace('。', '')
#
#         elif str(file_name).startswith("生物力学"):
#             orientation = get_pdf_orientation(saved_jpgs[0])
#             if orientation == 'portrait':
#                 # 竖版
#                 regions = [(180, 1210, 430, 1250)]
#             else:
#                 regions = [(420, 535, 750, 591)]
#             img = Image.open(saved_jpgs[0])
#             for region in regions:
#                 left, top, right, bottom = region
#                 crop_box = (left, top, right, bottom)
#                 try:
#                     roi = img.crop(crop_box)
#                     ocr_result = processor.ocr_image(np.array(roi))
#                     all_texts = [item["text"] for item in ocr_result.get("data", [])]
#                     joined_text = "".join(all_texts)
#                     # print(joined_text)
#                 except Exception as e:
#                     print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
#             result["name"] = joined_text.replace(' ', '').replace(',', '').replace('，', '').replace('.', '').replace('。', '')
#
#         elif str(file_name).startswith("屈光六图"):
#             orientation = get_pdf_orientation(saved_jpgs[0])
#             if orientation == 'portrait':
#                 # 竖版
#                 regions = [(1430, 1170, 1550, 1250)]
#             else:
#                 regions = [(1990, 515, 2150, 610)]
#
#             img = Image.open(saved_jpgs[0])
#             for region in regions:
#                 left, top, right, bottom = region
#                 crop_box = (left, top, right, bottom)
#                 try:
#                     roi = img.crop(crop_box)
#                     ocr_result = processor.ocr_image(np.array(roi))
#                     all_texts = [item["text"] for item in ocr_result.get("data", [])]
#                     joined_text = "".join(all_texts)
#                     # print(joined_text)
#                 except Exception as e:
#                     print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
#             result["name"] = joined_text.replace(' ', '').replace(',', '').replace('，', '').replace('.', '').replace('。', '')
#
#         elif str(file_name).startswith("眼底照片"):
#             regions = [(1150, 50, 1600, 115)]
#             img = Image.open(saved_jpgs[0])
#             for region in regions:
#                 left, top, right, bottom = region
#                 crop_box = (left, top, right, bottom)
#                 try:
#                     roi = img.crop(crop_box)
#                     ocr_result = processor.ocr_image(np.array(roi))
#                     all_texts = [item["text"] for item in ocr_result.get("data", [])]
#                     joined_text = "".join(all_texts)
#                     # print(joined_text)
#                 except Exception as e:
#                     print(datetime.now(), f'解析 {saved_jpgs[0]} 坐标区域 {region} 失败: {e}')
#             result["name"] = joined_text.replace(' ', '').replace(',', '').replace('，', '').replace('.', '').replace('。', '')
#
#         delete_files(saved_jpgs)
#         if not result.get('name'):
#             name = extract_patient_name(file_name)
#             result['name'] = name
#         print(datetime.now(), f"{file_path} 解析成功， 耗时 {time.time() - start_time} s")
#         return result.get('name', ''), result
#     except Exception as e:
#         print(datetime.now(), f"解析文件 {file_path} 失败: {e}")
#         return None, {}


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

            report_name = f"{final_file_name}-{patient_name}.pdf"
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
    # file_path = r"E:\pdf_share\角膜地形图31.pdf"
    # file_path = r"E:\pdf_share\角膜地形图32.pdf"
    # file_path = r"E:\pdf_share\图像总览53.pdf"
    # file_path = r"E:\pdf_share\比较两次检查54.pdf"
    # file_path = r"E:\pdf_share\生物力学-横版.pdf"
    # file_path = r"E:\pdf_share\生物力学-竖版.pdf"
    # file_path = r"E:\pdf_share\眼底照片.pdf"
    file_path = r"E:\pdf_share\Master700.pdf"
    file_path = r"E:\pdf_share\阿玛仕手术报告.pdf"


    # final_file_name, machine, values = analysis_pdf(file_path)
    # print(final_file_name)
    # print(machine)
    # print(values)
    # #
    # # for k,v in values.items():
    # #     values[k] = str(v).replace('mm', '').replace('μm', '').replace('mm', '')
    #
    # for k,v in values.items():
    #     print(k, v)






