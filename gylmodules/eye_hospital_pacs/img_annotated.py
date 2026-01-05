import PyPDF2
import fitz  # PyMuPDF
import numpy as np
import os
from datetime import datetime

from paddleocr import PaddleOCR
from pdf2image import convert_from_path
from gylmodules import global_config

from PIL import Image, ImageDraw

# 禁用PaddlePaddle的ccache警告
import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='paddle.utils.cpp_extension')

"""
在图片指定坐标位置绘制矩形框
:param image_path: 图片路径
:param coordinates: 矩形框坐标 [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
:param save_path: 保存路径(可选)
:return: 带矩形框的图片数组
"""


def draw_rectangle_on_image(image_path, coordinates, save_path=None):
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)
    # 绘制矩形框
    draw.polygon([tuple(p) for p in coordinates], outline="red", width=1)
    if save_path:
        img.save(save_path)
        print(f"标注图已保存: {save_path}")
    return np.array(img)


"""将 PDF 转换为 JPG 格式图片。"""

def pdf_to_jpg(pdf_path, output_dir=os.path.join(os.path.dirname(__file__), "output_jpg"), dpi=300):
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




# 屈光四图 图片
coordinates = [[420, 150], [580, 150], [580, 200], [420, 200]]  # 标志
coordinates = [[110, 205], [190, 205], [190, 225], [110, 225]]  # 姓
coordinates = [[110, 228], [190, 228], [190, 249], [110, 249]]  # 名
coordinates = [[250, 275], [310, 275], [310, 295], [250, 295]]  # 左右眼
coordinates = [[255, 380], [315, 380], [315, 400], [255, 400]]  # k1
coordinates = [[255, 415], [315, 415], [315, 430], [255, 430]]  # k2
coordinates = [[135, 445], [210, 445], [210, 464], [135, 464]]  # rm
coordinates = [[135, 808], [207, 808], [207, 828], [135, 828]]  # 最薄点位置
coordinates = [[135, 930], [204, 930], [204, 950], [135, 950]]  # 前房深度
coordinates = [[265, 870], [323, 870], [323, 890], [265, 890]]  # 水平方向白到白

# annotated_image = draw_rectangle_on_image("/Users/gaoyanliang/Downloads/Zhang_Liangjie_OS_30122025_150957_4 Maps Refr.PNG", coordinates, "annotated.jpg")
annotated_image = draw_rectangle_on_image("/Users/gaoyanliang/Downloads/Zhang_Yabin_OD_05012026_091431_4 Maps Refr.JPG", coordinates, "annotated.jpg")


#


# 使用示例 屈光四图  竖版
# 小范围
# coordinates = [[880, 1070], [1180, 1070], [1180, 1150], [880, 1150]]  # 左上角 患者信息
# coordinates = [[260, 1172], [670, 1172], [670, 1215], [260, 1215]]  # 左上角 姓
# coordinates = [[260, 1220], [670, 1220], [670, 1255], [260, 1255]]  # 左上角 名
# coordinates = [[540, 1310], [680, 1310], [680, 1345], [540, 1345]]  # 左上角 左右眼
# coordinates = [[550, 1525], [680, 1525], [680, 1560], [550, 1560]]  # k1
# coordinates = [[550, 1587], [680, 1587], [680, 1623], [550, 1623]]  # k2
# coordinates = [[312, 1650], [440, 1650], [440, 1685], [312, 1685]]  # rm
# coordinates = [[310, 2378], [445, 2378], [445, 2412], [310, 2412]]  # 左侧 最薄点位置
# coordinates = [[310, 2620], [440, 2620], [440, 2655], [310, 2655]]  # 左侧 前房深度
# coordinates = [[575, 2499], [680, 2499], [680, 2535], [575, 2535]]  # 左侧 水平方向白到白
# 大范围
# coordinates = [[50, 1150], [700, 1150], [700, 1450], [50, 1450]]  # 左上角 患者信息
# coordinates = [[60, 1450], [700, 1450], [700, 1710], [60, 1710]]  # 左侧 角膜前表面
# coordinates = [[60, 1600], [1100, 1600], [1100, 2000], [60, 2000]]  # 左侧 角膜后表面
# coordinates = [[60, 2250], [700, 2250], [700, 2500], [60, 2500]]  # 左侧 最薄点位置
# coordinates = [[60, 2480], [700, 2480], [700, 2670], [60, 2670]]  # 左侧 前房深度
# # 使用示例 屈光四图  横版
# 小范围
# coordinates = [[1050, 400], [1350, 400], [1350, 490], [1050, 490]]  # 左上角 标识
# coordinates = [[538, 519], [980, 519], [980, 563], [538, 563]]  # 左上角 姓
# coordinates = [[538, 576], [980, 576], [980, 620], [538, 620]]  # 左上角 名
# coordinates = [[885, 690], [1020, 690], [1020, 735], [885, 735]]  # 左上角 左右眼
# coordinates = [[900, 960], [1055, 960], [1055, 1000], [900, 1000]]  # k1
# coordinates = [[900, 1035], [1055, 1035], [1055, 1080], [900, 1080]]  # k2
# coordinates = [[600, 1113], [765, 1113], [765, 1157], [600, 1157]]  # rm
# coordinates = [[603, 2018], [765, 2018], [765, 2060], [603, 2060]]  # 左侧 最薄点位置
# coordinates = [[600, 2315], [766, 2315], [766, 2360], [600, 2360]]  # 左侧 前房深度
# coordinates = [[927, 2167], [1055, 2167], [1055, 2210], [927, 2210]]  # 左侧 水平方向白到白

# 大范围
# coordinates = [[280, 500], [1080, 500], [1080, 860], [280, 860]]  # 左上角 患者信息
# coordinates = [[290, 890], [1080, 890], [1080, 1350], [290, 1350]]  # 左侧 角膜前表面
# coordinates = [[290, 1800], [1080, 1800], [1080, 2150], [290, 2150]]  # 左侧 最薄点位置
# coordinates = [[290, 2150], [1080, 2150], [1080, 2370], [290, 2370]]  # 左侧 前房深度



# 屈光六图
# 横版
# coordinates = [[1500, 400], [1990, 400], [1990, 500], [1500, 500]]   # 标识  横版
# coordinates = [[1995, 515], [2150, 515], [2150, 560], [1995, 560]]   # 姓  横版
# coordinates = [[1995, 567], [2150, 567], [2150, 610], [1995, 610]]   # 名  横版
# coordinates = [[2260, 655], [2380, 655], [2380, 705], [2260, 705]]   # 左右眼  横版


# 竖版
# coordinates = [[1350, 1070], [1820, 1070], [1820, 1150], [1350, 1150]]   #  竖版 标识
# coordinates = [[1430, 1170], [1550, 1170], [1550, 1210], [1430, 1210]]   # 姓  竖版
# coordinates = [[1430, 1210], [1550, 1210], [1550, 1250], [1430, 1250]]   # 名  竖版
# coordinates = [[1645, 1284], [1750, 1284], [1750, 1320], [1645, 1320]]   # 左右眼



# 塑形镜验配图 角膜地形图
# coordinates = [[50, 50], [520, 50], [520, 125], [50, 125]]  # 标识
# coordinates = [[55, 150], [700, 150], [700, 220], [55, 220]]  # 顶部患者信息
# coordinates = [[450, 1600], [995, 1600], [995, 1670], [450, 1670]]  # 左侧 平k
# coordinates = [[450, 1670], [995, 1670], [995, 1735], [450, 1735]]  # 左侧 陡k
# coordinates = [[450, 1740], [1080, 1740], [1080, 1800], [450, 1800]]  # 左侧 △k
# coordinates = [[450, 1800], [995, 1800], [995, 1870], [450, 1870]]  # 左侧 平面E值
# coordinates = [[450, 1865], [995, 1865], [995, 1935], [450, 1935]]  # 左侧 斜面E值
# coordinates = [[2150, 1600], [2705, 1600], [2705, 1670], [2150, 1670]]  # 右侧 平k
# coordinates = [[2150, 1665], [2705, 1665], [2705, 1739], [2150, 1739]]  # 右侧 陡k
# coordinates = [[2150, 1740], [2800, 1740], [2800, 1800], [2150, 1800]]  # 右侧 △k
# coordinates = [[2150, 1800], [2705, 1800], [2705, 1870], [2150, 1870]]  # 右侧 平面E值
# coordinates = [[2150, 1865], [2705, 1865], [2705, 1935], [2150, 1935]]  # 右侧 斜面E值


# 角膜内皮细胞报告
# coordinates = [[360, 310], [2150, 310], [2150, 430], [360, 430]]  # 标识
# coordinates = [[1980, 640], [2155, 640], [2155, 690], [1980, 690]]  # 点位标识
# coordinates = [[320, 710], [485, 710], [485, 780], [320, 780]]  # 左右眼  上
# coordinates = [[320, 2010], [485, 2010], [485, 2080], [320, 2080]]  # 左右眼  下

# coordinates = [[780, 430], [1160, 430], [1160, 550], [780, 550]]  # 患者信息
# coordinates = [[1250, 1180], [1650, 1180], [1650, 1280], [1250, 1280]]  # cd1
# coordinates = [[1250, 2480], [1650, 2480], [1650, 2580], [1250, 2580]]  # cd2

# 角膜内皮细胞报告 22
# coordinates = [[1110, 1210], [1580, 1210], [1580, 1310], [1110, 1310]]  # cd1
# coordinates = [[1110, 2500], [1580, 2500], [1580, 2600], [1110, 2600]]  # cd2



# 眼表综合检查报告
# coordinates = [[960, 200], [1500, 200], [1500, 290], [960, 290]]   # 标识
# coordinates = [[50, 310], [500, 310], [500, 390], [50, 390]]   # 患者姓名
# coordinates = [[620, 500], [1000, 500], [1000, 580], [620, 580]]   # 右眼 首次破裂时间
# coordinates = [[1400, 500], [1700, 500], [1700, 580], [1400, 580]]   # 左眼 首次破裂时间

# 比较两次检查
# coordinates = [[1030, 400], [1450, 400], [1450, 500], [1030, 500]]   # 标识
# coordinates = [[540, 515], [850, 515], [850, 565], [540, 565]]   # 患者姓名
# coordinates = [[850, 605], [940, 605], [940, 655], [850, 655]]   #  左右眼

# Scheimpflug图像总览
# coordinates = [[1430, 400], [1830, 400], [1830, 500], [1430, 500]]   # 标识
# coordinates = [[530, 520], [850, 520], [850, 571], [530, 571]]   # 患者姓名
# coordinates = [[2850, 520], [3000, 520], [3000, 571], [2850, 571]]   # 左右眼

# 生物力学  非接触式眼压计
# coordinates = [[480, 710], [800, 710], [800, 800], [480, 800]]   # 横版  标识
# coordinates = [[420, 535], [750, 535], [750, 591], [420, 591]]   # 患者姓名  横版
# coordinates = [[1370, 591], [1650, 591], [1650, 650], [1370, 650]]   # 左右眼  横版

# coordinates = [[210, 1340], [500, 1340], [500, 1410], [210, 1410]]   # 竖版 标识
# coordinates = [[180, 1210], [430, 1210], [430, 1250], [180, 1250]]   # 患者姓名  竖版
# coordinates = [[940, 1250], [1130, 1250], [1130, 1295], [940, 1295]]   # 左右眼  竖版


# 眼底照片
# coordinates = [[100, 50], [300, 50], [300, 110], [100, 110]]   # 标识
# coordinates = [[1150, 50], [1600, 50], [1600, 115], [1150, 115]]   # 患者姓名


# # Master700
# 标识
# coordinates = [[200, 3190], [600, 3190], [600, 3270], [200, 3270]]
# 姓名
# coordinates = [[450, 120], [900, 120], [900, 250], [450, 250]]
# 标题
# coordinates = [[950, 930], [1600, 930], [1600, 1090], [950, 1090]]
# # OD AL
# coordinates = [[340, 1360], [560, 1360], [560, 1425], [340, 1425]]
# # OS AL
# coordinates = [[1405, 1360], [1630, 1360], [1630, 1425], [1405, 1425]]
# # OD CCT
# coordinates = [[340, 1416], [560, 1416], [560, 1470], [340, 1470]]
# # # OS CCT
# coordinates = [[1405, 1416], [1630, 1416], [1630, 1470], [1405, 1470]]
# # # OD WTW
# coordinates = [[340, 2710], [620, 2710], [620, 2770], [340, 2770]]
# # # OS WTW
# coordinates = [[1410, 2710], [1720, 2710], [1720, 2770], [1410, 2770]]
# # # OD CW-chord
# coordinates = [[840, 2760], [1220, 2760], [1220, 2820], [840, 2820]]
# # # OS CW-chord
# coordinates = [[1910, 2760], [2240, 2760], [2240, 2820], [1910, 2820]]


# 阿玛仕 全激光 设备报告
# 标识
# coordinates = [[300, 70], [800, 70], [800, 130], [300, 130]]
# # 左右眼
# coordinates = [[300, 500], [430, 500], [430, 630], [300, 630]]
# # 姓名
# coordinates = [[880, 555], [1200, 555], [1200, 625], [880, 625]]
# coordinates = [[1310, 555], [1600, 555], [1600, 625], [1310, 625]]

# 角膜曲率 k1
# coordinates = [[680, 960], [1110, 960], [1110, 1025], [680, 1025]]
# 角膜曲率  k2
# coordinates = [[680, 1025], [1110, 1025], [1110, 1090], [680, 1090]]
# # 屈光度
# coordinates = [[680, 1360], [1280, 1360], [1280, 1430], [680, 1430]]

# # 切削时间
# coordinates = [[700, 1560], [1200, 1560], [1200, 1625], [700, 1625]]
# # 光区
# coordinates = [[1925, 710], [2380, 710], [2380, 780], [1925, 780]]
# # 切削深度
# coordinates = [[1925, 940], [2380, 940], [2380, 1020], [1925, 1020]]

# OCT 竖版
# coordinates = [[2180, 20], [2450, 20], [2450, 125], [2180, 125]]  # 标识
# coordinates = [[20, 20], [250, 20], [250, 125], [20, 125]]  # 左右眼
# coordinates = [[130, 130], [350, 130], [350, 195], [130, 195]]  # 患者姓名

# OCT 横版
# coordinates = [[3270, 20], [3490, 20], [3490, 105], [3270, 105]]  # 标识
# coordinates = [[20, 20], [230, 20], [230, 105], [20, 105]]  # 左右眼
# coordinates = [[120, 110], [330, 110], [330, 170], [120, 170]]  # 患者姓名


# B超报告单.pdf"
# coordinates = [[1530, 140], [2000, 140], [2000, 270], [1530, 270]]  # 标识
# coordinates = [[230, 260], [610, 260], [610, 400], [230, 400]]  # 患者姓名




# pdf_file = "/Users/gaoyanliang/Downloads/黄斑OCT.pdf"
# pdf_file = r"E:\pdf_share\B超报告单1.pdf"
#
# output_directory = "."  # 替换为你的输出目录
# saved_jpgs = pdf_to_jpg(pdf_file, output_directory)
# print("转换完成的 JPG 文件完整路径:")
# for path in saved_jpgs:
#     print(path)
#
# annotated_image = draw_rectangle_on_image(saved_jpgs[0], coordinates, "annotated.jpg")


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





