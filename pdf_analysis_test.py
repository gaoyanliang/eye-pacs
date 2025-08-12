import numpy as np
from PIL import Image
from paddleocr import PaddleOCR
import logging
import time
import io
import os
from typing import Union, List, Dict



import traceback

from gylmodules.eye_hospital_pacs.pdf_ocr_analysis import extract_quguang

data = "RS中 南陽南石眼料醫院 南阳瑞视眼科医院 OCULUS - PENTACAM 屈光四图 姓： Zhou 名： Long 51.0 ID: 轴向曲 50.0 2000/11/08 右眼 出生日期： 眼睛： 49.0 120 9mm 8- 2025/03/28 10:46:45 检查日期： 时间： 48.0 47.0 检查备注： 45 09 46.0 4- 45.0 角膜前表面 44. 90° 44.0 43.2D 平坦7.81毫米 K1: 43.0 陡峭7.56毫米 K2: 44.6D ： 42.0 0- 41.0 270° Rm: Km: 7.68毫米 43.9D 43.4 40.0 42.4 轴位： 39.0 17.1* 散光： -1.4D 质量监OK （平坦） 38.0 偏心率 最小7.38毫米 周边曲7.82毫米 0.38 37.0 (8毫米] 36.0 8- 角膜后表面 0.25D 90° 7 平坦6.29毫米 -6.4D K1: 曲率 相对 K2: -6.8D 随峭5.88毫米 300 角 Rm: 6.09毫米 Km: -6.6D 270° 340 轴位： 质量监OK +0.4D 380 散光： 9mm 8- 420 偏心率 0.69 周边曲6.53毫米 最小5.78毫米 （8毫米） 460 626 500 厚度： x[mm] y[mm] 4 540 616 561 516微米 + -0.13 0.03 瞳孔中心： 580 620 601 516微米 0.00 0.00 顶点厚度： 660 0- 547 最薄点位置 -0.13 0.32 515微米 700 592 740 +3.43 -1.23 45.7D 最大K值（前表面）： 543 780 590 4- 水平方向白10.9毫米 60.1毫米3 角膜容积： 820 601 860 28.4° 152毫米3 房角： 前房容积： 900 8- 10微米 2.73毫米 前房深度（内） 瞳孔直径： 3.03毫米 T 厚度 +1.4mmHg 晶体厚度： 输入眼压眼压加： 绝对"

extract_quguang(joined_text)



