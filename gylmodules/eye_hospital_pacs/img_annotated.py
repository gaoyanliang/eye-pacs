import PyPDF2
import fitz  # PyMuPDF
import numpy as np
import os
from datetime import datetime

from paddleocr import PaddleOCR
from pdf2image import convert_from_path
from gylmodules import global_config

from PIL import Image, ImageDraw


def draw_rectangle_on_image(image_path, coordinates, save_path=None):
    """
    在图片指定坐标位置绘制矩形框
    :param image_path: 图片路径
    :param coordinates: 矩形框坐标 [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
    :param save_path: 保存路径(可选)
    :return: 带矩形框的图片数组
    """
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    # 绘制矩形框
    draw.polygon([tuple(p) for p in coordinates], outline="red", width=5)

    if save_path:
        img.save(save_path)
        print(f"标注图已保存: {save_path}")

    return np.array(img)


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




def get_pdf_orientation(pdf_path):
    """
    判断PDF页面方向
    :param pdf_path: PDF文件路径
    :return: 'portrait'(竖版), 'landscape'(横版), 'square'(正方形)
    """
    try:
        # 方法1: 使用PyPDF2
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            if len(reader.pages) > 0:
                page = reader.pages[0]
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)

                # 计算宽高比
                ratio = width / height
                if ratio > 1.2:  # 宽明显大于高
                    return 'landscape'
                elif ratio < 0.8:  # 高明显大于宽
                    return 'portrait'
                else:
                    return 'square'

    except Exception as e:
        print(f"PyPDF2读取失败: {e}")
        try:
            # 方法2: 使用PyMuPDF (更可靠)
            doc = fitz.open(pdf_path)
            if len(doc) > 0:
                page = doc[0]
                rect = page.rect
                width = rect.width
                height = rect.height

                ratio = width / height
                if ratio > 1.2:
                    return 'landscape'
                elif ratio < 0.8:
                    return 'portrait'
                else:
                    return 'square'
            doc.close()

        except Exception as e2:
            print(f"PyMuPDF读取失败: {e2}")

    return 'unknown'


def get_pdf_page_size(pdf_path):
    """
    获取PDF页面具体尺寸
    """
    try:
        doc = fitz.open(pdf_path)
        if len(doc) > 0:
            page = doc[0]
            rect = page.rect
            print(f"PDF页面尺寸: {rect.width} x {rect.height}")
            return {
                'width': rect.width,
                'height': rect.height,
                'ratio': rect.width / rect.height,
                'orientation': 'A4竖版' if rect.height > rect.width else 'A4横版'
            }
        doc.close()
    except:
        pass
    return None





# pdf_file = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/204角膜地形图仪/干眼检查报告1.pdf"  # 替换为你的 PDF 文件路径
#
# pdf_file = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/201视光角膜地形图/201视光角膜地形图.pdf"
#
#
# pdf_file = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/202角膜内皮显微镜/202 角膜内皮细胞报告.pdf"
# pdf_file = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/代码/4.pdf"
#
# pdf_file = "/Users/gaoyanliang/各个系统文档整理/眼科医院/眼科医院仪器检查报告和病历/塑形镜验配图.pdf"
#
#
# pdf_file = "/Users/gaoyanliang/Downloads/bi_qianxi_2025021003_OS_2025-02-10__18-26-12.pdf"


pdf_file = r"C:\Users\Administrator\Desktop\eye-pacs\gylmodules\eye_hospital_pacs\Wang_Honglei_OS_11092025_110222_4 Maps Refr_20250911161528.pdf"

pdf_file = r"C:\Users\Administrator\Desktop\Master700_1918372191_白_雪_20190801152407.pdf"

output_directory = "."  # 替换为你的输出目录
saved_jpgs = pdf_to_jpg(pdf_file, output_directory)
print("转换完成的 JPG 文件完整路径:")
for path in saved_jpgs:
    print(path)



# 使用示例 屈光四图  竖版
# coordinates = [[50, 1150], [700, 1150], [700, 1450], [50, 1450]]  # 左上角 患者信息
# coordinates = [[60, 1450], [700, 1450], [700, 1710], [60, 1710]]  # 左侧 角膜前表面
# coordinates = [[60, 1600], [1100, 1600], [1100, 2000], [60, 2000]]  # 左侧 角膜后表面
# coordinates = [[60, 2250], [700, 2250], [700, 2500], [60, 2500]]  # 左侧 最薄点位置
# 使用示例 屈光四图  横版
coordinates = [[280, 500], [1080, 500], [1080, 860], [280, 860]]  # 左上角 患者信息
coordinates = [[290, 890], [1080, 890], [1080, 1350], [290, 1350]]  # 左侧 角膜前表面
coordinates = [[290, 1800], [1080, 1800], [1080, 2150], [290, 2150]]  # 左侧 最薄点位置


# 角膜内皮细胞报告
# coordinates = [[330, 430], [2200, 430], [2200, 550], [330, 550]]  # 患者信息
# coordinates = [[1250, 1080], [1650, 1080], [1650, 1280], [1250, 1280]]  # cd1
# coordinates = [[1250, 2380], [1650, 2380], [1650, 2580], [1250, 2580]]  # cd2


# 塑形镜验配图
# coordinates = [[50, 150], [1100, 150], [1100, 300], [50, 300]]  # 顶部患者信息
# coordinates = [[50, 1600], [1100, 1600], [1100, 2000], [50, 2000]]  # 左侧
# coordinates = [[1750, 1600], [2800, 1600], [2800, 2000], [1750, 2000]]  # 右侧


# 阿玛仕 全激光 设备报告
# 角膜曲率 k1  k2
# coordinates = [[300, 940], [1200, 940], [1200, 1100], [300, 1100]]
# # 屈光度
# coordinates = [[400, 1350], [1600, 1350], [1600, 1450], [400, 1450]]

# # 切削时间
# coordinates = [[300, 1555], [1200, 1555], [1200, 1625], [300, 1625]]
# # 光区
# coordinates = [[1425, 700], [2380, 700], [2380, 780], [1425, 780]]
# # 切削深度
# coordinates = [[1425, 940], [2380, 940], [2380, 1020], [1425, 1020]]


# # Master700
# 标题
coordinates = [[950, 930], [1600, 930], [1600, 1090], [950, 1090]]
# OD AL
coordinates = [[250, 1360], [560, 1360], [560, 1425], [250, 1425]]
# OS AL
coordinates = [[1330, 1360], [1630, 1360], [1630, 1425], [1330, 1425]]
# OD CW-chord
coordinates = [[650, 2760], [1220, 2760], [1220, 2820], [650, 2820]]
# OS CW-chord
coordinates = [[1720, 2760], [2240, 2760], [2240, 2820], [1720, 2820]]

annotated_image = draw_rectangle_on_image(saved_jpgs[3], coordinates, "annotated.jpg")


def process_pdf_with_orientation(pdf_path):
    """
    根据PDF方向进行不同处理
    """
    orientation = get_pdf_orientation(pdf_path)
    page_size = get_pdf_page_size(pdf_path)

    print(f"PDF方向: {orientation}")
    print(f"页面尺寸: {page_size}")

    # 根据方向调整处理逻辑
    if orientation == 'landscape':
        print("横版PDF - 可能需要调整OCR参数")
        # 横版PDF的特殊处理
        crop_box = (0, 0, 800, 600)  # 横版调整
        orientation = "横版"

    elif orientation == 'portrait':
        print("竖版PDF - 标准处理")
        # 竖版PDF的标准处理
        crop_box = (60, 1160, 700, 1440)  # 您的原始坐标
        orientation = "竖版"

    else:
        print("正方形或未知方向 - 需要进一步检查")
        crop_box = (0, 0, 600, 600)  # 默认处理
        orientation = "未知"

    return crop_box, orientation


# 使用示例
# crop_box, orientation = process_pdf_with_orientation(saved_jpgs[0])
#
# print(f"使用裁剪框: {crop_box}")
# print(f"页面方向: {orientation}")





