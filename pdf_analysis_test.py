import numpy as np
from PIL import Image
from paddleocr import PaddleOCR
import logging
import time
import io
import os
from typing import Union, List, Dict


logger = logging.getLogger(__name__)


class MacOCRProcessor:
    def __init__(self):
        """macOS 专属初始化配置"""
        # 设置环境变量（解决macOS libomp问题）
        os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

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
            logger.info("Initializing PaddleOCR for macOS...")
            try:
                self._ocr_engine = PaddleOCR(
                    lang='ch',
                    use_angle_cls=False,  # macOS上建议禁用角度分类
                    use_gpu=False,  # macOS默认禁用GPU加速
                    enable_mkldnn=False,  # macOS不需要此参数
                    show_log=False,
                    det_model_dir='inference/ch_ppocr_server_v2.0_det_infer/',
                    rec_model_dir='inference/ch_ppocr_server_v2.0_rec_infer/',
                    cls_model_dir=None  # 显式禁用分类模型
                )
            except Exception as e:
                logger.error(f"初始化失败: {str(e)}")
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
            logger.error(f"图像加载失败: {str(e)}")
            raise

    def ocr_image(
            self,
            image_input: Union[str, np.ndarray, bytes],
            language: str = 'ch',
            merge_level: int = 1  # 0:不合并 1:行合并 2:段落合并
    ) -> Dict:
        """macOS优化版OCR方法"""
        start_time = time.time()
        result = {
            "code": 20000,
            "data": [],
            "time_cost": 0,
            "system": "macOS"
        }

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
                        result["data"].append({
                            "text": text.strip(),
                            "confidence": float(confidence),
                            "position": [list(map(int, p)) for p in points]
                        })

                # macOS特有的合并策略
                if merge_level > 0:
                    result["data"] = self._mac_merge_lines(
                        result["data"],
                        level=merge_level
                    )

            result["time_cost"] = round(time.time() - start_time, 2)
            return result

        except Exception as e:
            logger.error(f"OCR处理失败: {str(e)}")
            return {
                "code": 50000,
                "error": str(e),
                "time_cost": round(time.time() - start_time, 2)
            }

    def _mac_merge_lines(self, text_blocks: List[Dict], level: int = 1) -> List[Dict]:
        """
        macOS专属文本合并策略
        level参数:
        0 - 不合并
        1 - 行合并（默认）
        2 - 段落合并（适合多栏文本）
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


# macOS环境检测
if __name__ == "__main__":
    import platform

    if platform.system() != 'Darwin':
        print("警告：此代码专为macOS优化！")

    # 配置日志（macOS控制台友好格式）
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler()]
    )
    logger = logging.getLogger("MacOCR")

    # 使用示例
    processor = MacOCRProcessor()

    # 示例1: 识别PNG截图（处理透明背景）
    # result = processor.ocr_image(r"/Users/gaoyanliang/Downloads/L角膜OCT.jpg", merge_level=2)
    result = processor.ocr_image(r"/Users/gaoyanliang/nsyy/nsyy-project/202 角膜内皮细胞报告_page_1.jpg", merge_level=2)
    # result = processor.ocr_image("~/Desktop/screenshot.png", merge_level=2)

    # 示例2: 识别PDF转换的图片
    # with open("document.jpg", "rb") as f:
    #     result = processor.ocr_image(f.read(), language='en')

    # 打印结果
    for item in result.get("data", []):
        if item['confidence'] < 0.90:
            print(f"{item['text']} | 置信度: {item['confidence']:.2f}")
        else:
            print(f"{item['text']}")




