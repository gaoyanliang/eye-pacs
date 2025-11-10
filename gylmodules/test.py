import os
import time

import cv2
from paddleocr import PaddleOCR

start_time = time.time()

# === 配置 ===
image_path = "/Users/gaoyanliang/nsyy/eye-pacs/gylmodules/eye_hospital_pacs/屈光四图-横版_page_1.jpg"
output_dir = "cropped_rois"
# image_path = "/home/gyl/paddle_ocr_offline/比较两次检查54_page_1.jpg"
# output_dir = "/home/gyl/paddle_ocr_offline/cropped_rois"
os.makedirs(output_dir, exist_ok=True)

# 定义多个 ROI：{字段名: (x1, y1, x2, y2)}
rois = {
                    "xing": (538, 519, 980, 563), "ming": (538, 576, 980, 620), "eye": (885, 690, 1020, 735),
                    "k1": (900, 960, 1055, 1000), "k2": (900, 1035, 1055, 1080), "rm": (600, 1113, 765, 1157),
                    "thinnest_point": (603, 2018, 765, 2060), "depth": (600, 2315, 766, 2360),
                    "distance": (927, 2167, 1055, 2210)
                }

# === 1. 初始化 OCR（一次即可）===
ocr = PaddleOCR(
    lang="ch",
    use_textline_orientation=False,
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
)

# === 2. 读取原图 ===
img = cv2.imread(image_path)
if img is None:
    raise FileNotFoundError(f"图像未找到: {image_path}")

# === 3. 批量裁剪 & OCR ===
results = {}

for field_name, (x1, y1, x2, y2) in rois.items():
    # 裁剪 ROI
    cropped = img[y1:y2, x1:x2]
    if cropped.size == 0:
        results[field_name] = "裁剪区域无效"
        continue

    # 保存裁剪图（可选）
    # save_path = os.path.join(output_dir, f"{field_name}_cropped.jpg")
    # cv2.imwrite(save_path, cropped)

    # OCR 识别
    results = ocr.predict(cropped)

    # 取第一页结果
    page = results[0]

    # 直接获取 rec_texts
    texts = page["rec_texts"]
    # print(texts)  # 例如：["比较两次检查"]

    # 如果你只关心文本，可直接拼接
    full_text = " ".join([t for t in texts if t.strip()])
    print(full_text)  # "比较两次检查"
    # texts = [t for t in result['rec_texts'] if t.strip()]
    # results[field_name] = " ".join(texts) if texts else "未识别到文本"

print('耗时：', time.time() - start_time)


