# pdf 文件解析，定时执行

import json
from datetime import datetime

import numpy as np
from PIL import Image
from paddleocr import PaddleOCR
import time
import io
import os
from typing import Union, List, Dict
from pdf2image import convert_from_path
import re
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
        print(datetime.now(), f"{pdf_path} PDF 转换失败: {e}")
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
            print(datetime.now(), f"保存第 {i + 1} 页失败: {e}")

    return jpg_paths


def delete_files(file_paths):
    print("正在删除文件...", file_paths)
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
                print(datetime.now(), f"文件不存在: {os.path.abspath(file_path)}")
        except Exception as e:
            results[file_path] = False
            print(datetime.now(), f"删除文件失败 ({os.path.abspath(file_path)}): {e}")

    return results


def extract_name_from_text(text: str) -> Optional[str]:
    """
    修复版姓名提取函数，适配更多格式变体
    支持格式：
    - "姓名 袁翼航 ID号：2025032804"
    - "姓袁翼航 ID号：2025032804"
    - "姓名: 张三 年龄：30"
    - "姓: 张三 年龄：30"
    - "Name: John Smith Age: 25"
    - "袁翼航 检查日期：28-03-2025"
    - "Patient: 李四 ID: 12345"
    """
    # 定义修复后的匹配模式（按优先级排序）
    patterns = [
        # 中文格式（带"姓名"前缀，支持空格或冒号分隔）
        r'(?:姓名|名字|姓)[\s:：]*([^\s\d：:]{2,4})(?=\s|$|ID|年龄|性别|检查日期)',
        # 英文格式
        r'(?:Name|Patient)[\s:：]*([A-Za-z]+\s+[A-Za-z]+)(?=\s|$|Age|ID|Gender)',
        # 前缀后直接接姓名（如"姓袁翼航"）
        r'(?:姓名|名字|姓)([^\s\d：:]{2,4})(?=\s|$|ID|年龄|性别|检查日期)',
    ]

    for pattern in patterns:
        try:
            match = re.search(pattern, text)
            if match:
                name = match.group(1).strip()
                """验证是否为有效姓名 2-4个中文字符 英文名（2-3个单词，首字母大写）"""
                if (re.fullmatch(r'[\u4e00-\u9fa5]{2,4}', name) or
                        re.fullmatch(r'([A-Z][a-z]+\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)?)', name)):
                    return name
        except re.error:
            continue  # 跳过有问题的正则模式

    return None


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
                                                 cls_model_dir=None  # 显式禁用分类模型
                                                 )
                else:
                    self._ocr_engine = PaddleOCR(lang='ch', use_angle_cls=False,
                                                 use_gpu=False, enable_mkldnn=False, show_log=False,
                                                 det_model_dir='/home/nsyy/eye-pacs/inference/ch_PP-OCRv4_det_infer/',
                                                 rec_model_dir='/home/nsyy/eye-pacs/inference/ch_PP-OCRv4_rec_infer/',
                                                 cls_model_dir=None  # 显式禁用分类模型
                                                 )
                    # TODO 驱动有问题 暂时不使用GPU
                    # self._ocr_engine = PaddleOCR(
                    #     # 硬件配置
                    #     lang='ch', use_gpu=True, gpu_mem=7000,  # 7GB显存限制
                    #
                    #     # 模型选择（平衡速度与精度）
                    #     det_model_dir='/home/nsyy/eye-pacs/inference/ch_PP-OCRv4_det_infer/',
                    #     rec_model_dir='/home/nsyy/eye-pacs/inference/ch_PP-OCRv4_rec_infer/',
                    #     cls_model_dir=None,  # 禁用方向分类（PDF通常方向固定）
                    #
                    #     # # 性能参数
                    #     # det_limit_side_len=1600,  # 适应A4文档300dpi扫描件
                    #     # rec_batch_num=12,  # 根据显存调整
                    #     # use_tensorrt=False,  # GTX 10系列不支持TensorRT加速
                    #     #
                    #     # # 质量参数
                    #     # det_db_score_mode="fast",  # 平衡速度与精度
                    #     # show_log=False, use_angle_cls=True,  # 服务器建议启用方向分类
                    #     # cls_batch_num=10, use_mp=True,  # 多进程
                    #     # total_process_num=4,  # 4个进程
                    #     # enable_mkldnn=False  # Linux服务器可改为True（Intel CPU加速）
                    # )
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

    def ocr_image(self, image_input: Union[str, np.ndarray, bytes], language: str = 'ch', merge_level: int = 1) -> Dict:
        """macOS优化版OCR方法, merge_level 0:不合并 1:行合并 2:段落合并"""
        ret_data = {"code": 20000, "data": []}

        try:
            # 1. 加载图像
            img_array = self.load_image(image_input)

            # 2. 执行OCR（macOS特定参数）
            ocr_result = self.ocr_engine.ocr(img_array, cls=False)  # 禁用分类

            # 3. 处理结果
            if ocr_result and ocr_result[0]:
                for line in ocr_result[0]:
                    if len(line) >= 2:
                        points, (text, confidence) = line
                        ret_data["data"].append({
                            "text": text.strip(),
                            "confidence": float(confidence),
                            "position": [list(map(int, p)) for p in points]
                        })

                # macOS特有的合并策略
                if merge_level > 0:
                    ret_data["data"] = self._mac_merge_lines(ret_data["data"], level=merge_level)

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


def extract_k_value(text, label, unit):
    """
    提取支持两种格式：
    1) K1:43.2D
    2) 43.2D K1
    """
    # 前缀
    m = re.search(rf'{label}[:：]?\s*([\d\.]+){unit}', text)
    if m:
        return float(m.group(1))

    # 后缀
    m = re.search(rf'([\d\.]+){unit}\s*{label}', text)
    if m:
        return float(m.group(1))

    return None


def extract_k_values_from_text(ocr_text):
    """
    主函数，从 OCR 的整段文本里抽取两组表面参数
    """
    result = {"角膜前表面": {}, "角膜后表面": {}}

    # ------ 分段 ------
    # 找到 角膜前表面 和 角膜后表面
    pattern = r"(角膜前表面)(.*?)(角膜后表面|$)"
    m = re.search(pattern, ocr_text, re.DOTALL)
    if m:
        front_block = m.group(2).strip()
    else:
        front_block = ""

    pattern2 = r"(角膜后表面)(.*)$"
    m2 = re.search(pattern2, ocr_text, re.DOTALL)
    if m2:
        back_block = m2.group(2).strip()
    else:
        back_block = ""

    def parse_surface_block(text_block):
        """
        从一个「角膜前/后表面」块里提取 K1、K2、Rm、Km
        """
        return {
            "K1": extract_k_value(text_block, "K1", unit="D"),
            "K2": extract_k_value(text_block, "K2", unit="D"),
            "Rm": extract_k_value(text_block, "Rm", unit="毫米"),
            "Km": extract_k_value(text_block, "Km", unit="D")
        }

    # ------ 分别解析 ------
    result["角膜前表面"] = {k: v for k, v in parse_surface_block(front_block).items() if v is not None}
    result["角膜后表面"] = {k: v for k, v in parse_surface_block(back_block).items() if v is not None}

    return result


def fix_vertical_ocr_name(name: str) -> str:
    """
    修复竖排导致的首字母+名字拼接错误，比如 ILong → Long
    """
    if len(name) >= 2 and name[0].isupper() and name[1:].isalpha():
        # 如果后面也是个首字母大写的英文名
        m = re.match(r'([A-Z][a-z]+)', name[1:])
        if m:
            return m.group(1)
    return name


def extract_quguang(text: str):
    """
    解析屈光四图/六图
    :param text:
    :return:
    """
    result = {}
    lines = text.splitlines()

    # ---- 1. 解析姓名
    def extract_name(text):
        # 方法1：匹配"姓+英文名+名+英文名"模式
        name_match = re.search(r"姓\s*([A-Za-z]+)\s*名\s*[:：]\s*([A-Za-z]+)", text)
        if name_match:
            return f"{name_match.group(1)} {name_match.group(2)}"

        # 方法2：匹配连续的英文单词（作为姓名）
        name_match = re.search(r"(?:姓名|Name)[:：]\s*([A-Za-z]+\s+[A-Za-z]+)", text)
        if name_match:
            return name_match.group(1)

        # 方法3：匹配文本中连续的两个英文单词（最后手段）
        names = re.findall(r"\b([A-Z][a-z]+)\b", text)
        if len(names) >= 2:
            return " ".join(names[:2])

        return ""

    result["姓名"] = extract_name(text)
    # ---- 2. 出生日期、眼睛、检查日期、时间
    normalized_text = text.replace("：", ":")
    birth_date_match = re.search(
        r"(?:(\d{4}/\d{2}/\d{2})\s*出生日期:\s*|出生日期:\s*(\d{4}/\d{2}/\d{2}))",
        normalized_text
    )
    if birth_date_match:
        result["出生日期"] = birth_date_match.group(1) or birth_date_match.group(2)

    # 提取检查日期（同样逻辑）
    exam_date_match = re.search(
        r"(?:(\d{4}/\d{2}/\d{2})\s*检查日期:\s*|检查日期:\s*(\d{4}/\d{2}/\d{2}))",
        normalized_text
    )
    if exam_date_match:
        result["检查日期"] = exam_date_match.group(1) or exam_date_match.group(2)

    eye_match = re.search(r"眼睛[:：]?\s*([^\s\n]+)", text)
    if eye_match:
        result["眼睛"] = eye_match.group(1)

    time_match = re.search(r"时间[:：]?\s*([0-9:]+)", text)
    if time_match:
        result["时间"] = time_match.group(1)

    # ---- 3. 分段提取前表面和后表面
    pre_match = re.search(r"(角膜前表面.*?)(角膜后表面|$)", text, re.DOTALL)
    post_match = re.search(r"(角膜后表面.*)", text, re.DOTALL)

    def extract_corneal_surface(block):
        res = {}
        if not block:
            return res

        # 平坦
        flat = re.search(r"平坦\s*([0-9.]+)", block)
        if flat:
            res["平坦"] = float(flat.group(1))

        # K1
        k1_candidates = re.findall(r"K1[:：]?\s*([0-9.]+)", block)
        if not k1_candidates:
            k1_candidates = re.findall(r"([0-9.]+)\s*K1", block)
        if k1_candidates:
            res["K1"] = float(k1_candidates[0])

        # K2
        k2_candidates = re.findall(r"K2[:：]?\s*([0-9.]+)", block)
        if not k2_candidates:
            k2_candidates = re.findall(r"([0-9.]+)\s*K2", block)
        if k2_candidates:
            res["K2"] = float(k2_candidates[0])

        # Rm
        rm_match = re.search(r"Rm[:：]?\s*([0-9.]+)", block)
        if rm_match:
            res["Rm"] = float(rm_match.group(1))

        # Km
        km_match = re.search(r"Km[:：]?\s*([0-9.]+)", block)
        if km_match:
            res["Km"] = float(km_match.group(1))

        eccentric_match = re.search(r"偏[^\d]*([0-9.]+)", block)
        if eccentric_match:
            res["偏心率"] = float(eccentric_match.group(1))

        return res

    if pre_match:
        result["前表面"] = extract_corneal_surface(pre_match.group(1))
    if post_match:
        result["后表面"] = extract_corneal_surface(post_match.group(1))

    # ---- 5. 新增 瞳孔中心
    pupil_match = re.search(r"瞳孔中心[:：]?\s*\+?([0-9.]+)", text)
    if pupil_match:
        result["瞳孔中心"] = float(pupil_match.group(1))

    return result


def analysis_pdf(file_path):
    """
    解析pdf文件，并返回患者名字以及需要提取的数据
    非pdf文件不进行解析
    :param file_path:
    :return:
    """
    try:
        start_time = time.time()
        # 将pdf文件转换为图片，方便解析, 如果pdf有多页，则会生成多个图片，默认取第一张
        jpg_paths = pdf_to_jpg(file_path)
        print(datetime.now(), f'{file_path} 已转换为图片，数量 {len(jpg_paths)}, 耗时 {time.time() - start_time} 秒')
        start_time = time.time()

        # 解析图片，识别患者姓名 & 提取数据
        file_name = os.path.basename(file_path)
        processor = OCRProcessor()
        values = {}
        if str(file_name).startswith("屈光四图"):
            # 屈光四图
            img = Image.open(jpg_paths[0])
            # 只解析数据部分
            crop_box = (0, 0, int(img.size[1] / 3), img.size[1])
            # 转成 numpy 数组再 OCR
            result = processor.ocr_image(np.array(img.crop(crop_box)))
            delete_files(jpg_paths)

            all_texts = [item["text"] for item in result.get("data", [])]
            joined_text = " ".join(all_texts)
            values = extract_quguang(joined_text)
            patient_name = values.get('姓名', '')
            print(f"{jpg_paths[0]} 解析完成 耗时 {time.time() - start_time} 秒")
            return patient_name, values

        result = processor.ocr_image(jpg_paths[0], merge_level=2)
        all_texts = [item["text"].replace('\n', ' ') for item in result.get("data", [])]
        joined_text = " ".join(all_texts)
        delete_files(jpg_paths)

        if str(file_name).startswith("角膜内皮细胞报告"):
            # 如果是 角膜内皮细胞报告 提取所有 CD 值
            cd_values = re.findall(r'CD\s*(\d+)\s*', joined_text)
            if len(cd_values) >= 2:
                values["left_eye_cd"] = cd_values[0]
                values["right_eye_cd"] = cd_values[1]
            elif len(cd_values) == 1:
                values["left_eye_cd"] = cd_values[0]
                values["right_eye_cd"] = cd_values[0]
        if str(file_name).startswith("干眼分析2"):
            # 干眼分析 2 提取 破裂时间
            matches = re.findall(r'破裂时间[（(]第一次[）)]\s*(\d+\.\d+)(?:s|秒)', joined_text)
            if len(matches) >= 2:
                values['right_eye_time'] = matches[0]
                values['left_eye_time'] = matches[1]

        print(f"{jpg_paths[0]} 解析完成 耗时 {time.time() - start_time} 秒")
        patient_name = extract_name_from_text(joined_text)
        values['姓名'] = patient_name if patient_name else ''
        return patient_name, values

    except Exception as e:
        print(datetime.now(), f"解析文件 {file_path} 失败: {e}")
        return None, {}


def regularly_parsing_eye_report():
    db = DbUtil(global_config.DB_HOST, global_config.DB_USERNAME, global_config.DB_PASSWORD,
                global_config.DB_DATABASE_GYL)
    report_list = db.query_all(f"SELECT * FROM nsyy_gyl.ehp_reports "
                               f"WHERE report_value is null ORDER BY report_time limit 5")

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

    del db


# macOS环境检测
# if __name__ == "__main__":
#     start_time = time.time()
#
#     pdf_file = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/代码/4.pdf"
#     # pdf_file = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/代码/5.pdf"
#     patient_name, values = analysis_pdf(pdf_file)
#
#     print("患者姓名: ", patient_name)
#     # print("识别结果: ", values)
#     for k, v in values.items():
#         print(k, ": ", v)
#     print("PDF 识别完成，耗时:", time.time() - start_time, "秒")
#
#     # # pdf_file = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/205-北 眼前节测量评估系统/ODpentacam四图.pdf"  # 替换为你的 PDF 文件路径
#     # pdf_file = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/204角膜地形图仪/干眼检查报告1.pdf"  # 替换为你的 PDF 文件路径
#     # output_directory = "."  # 替换为你的输出目录
#     # saved_jpgs = pdf_to_jpg(pdf_file, output_directory)
#     # print("转换完成的 JPG 文件完整路径:")
#     # for path in saved_jpgs:
#     #     print(path)
#     #
#     # print("PDF 转换 JPG 完成，耗时:", round(time.time() - start_time, 2), "秒")
#     #
#     # # 使用示例
#     # processor = OCRProcessor()
#     #
#     # # 示例1: 识别PNG截图（处理透明背景）
#     # # result = processor.ocr_image(r"/Users/gaoyanliang/Downloads/L角膜OCT.jpg", merge_level=2)
#     # result = processor.ocr_image(saved_jpgs[0], merge_level=2)
#
#     # # 示例2: 识别PDF转换的图片
#     # with open(saved_jpgs[0], "rb") as f:
#     #     result = processor.ocr_image(f.read(), language='en')
#
#     # image_file = saved_jpgs[0]
#     # img = Image.open(image_file)
#     #
#     # # 假设你的感兴趣区域是这段
#     # crop_box = (0, 0, 700, 3509)
#     # roi = img.crop(crop_box)
#     #
#     # # 转成 numpy 数组再 OCR
#     # result = processor.ocr_image(np.array(roi))
#
#     # # ====== 屈光四图
#     # for item in result.get("data", []):
#     #     if item['confidence'] < 0.90:
#     #         print(f"{item['text']} | 置信度: {item['confidence']:.2f}")
#     #     else:
#     #         print(f"{item['text']}")
#     #
#     #     if extract_name_from_text(item['text']):
#     #         print('=========== Name: ', extract_name_from_text(item['text']))
#     #     # print("位置坐标:  {item['position']}")
#     #
#     # all_texts = [item["text"] for item in result.get("data", [])]
#     # joined_text = " ".join(all_texts)
#     # print(joined_text)
#     # fields = extract_quguang(joined_text)
#     # print(fields)
#     #
#     # all_texts = [item["text"] for item in result.get("data", [])]
#     # joined_text = " ".join(all_texts)
#     # joined_text = joined_text.replace('\n', ' ')
#     # print('完整输出: ', joined_text)
#     # print("姓名", extract_surname_givenname(joined_text))
#     # print(extract_name_from_text(joined_text))
#     #
#     # fields = extract_k_values(joined_text)
#     # print(fields)
#     #
#     # result = extract_k_values_from_text(joined_text)
#     # print(result)
#     #
#     # print("识别完成，耗时:", round(time.time() - start_time, 2), "秒")
#     # # delete_files(saved_jpgs)
