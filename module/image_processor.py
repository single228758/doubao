import os
import time
import requests
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import io
import base64
from sklearn.cluster import KMeans
from common.log import logger

class ImageProcessor:
    def __init__(self, temp_dir, uploader=None):
        self.temp_dir = temp_dir
        self.uploader = uploader
        self.image_data = {}
        self._ensure_temp_dir()

    def _ensure_temp_dir(self):
        """确保临时目录存在"""
        os.makedirs(self.temp_dir, exist_ok=True)

    def _bytes_to_cv(self, image_bytes):
        """字节数据转OpenCV格式"""
        np_arr = np.frombuffer(image_bytes, np.uint8)
        return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    def _strict_red_mask(self, image_cv):
        """精准红色标记检测"""
        hsv = cv2.cvtColor(image_cv, cv2.COLOR_BGR2HSV)
        
        # 精确红色范围（避免检测到橙色或粉色）
        lower_red = np.array([170, 150, 50])
        upper_red = np.array([180, 255, 255])
        mask1 = cv2.inRange(hsv, lower_red, upper_red)

        lower_red2 = np.array([0, 150, 50])
        upper_red2 = np.array([10, 255, 255])
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)

        combined = cv2.bitwise_or(mask1, mask2)
        
        # 精准形态学处理（仅闭合小间隙）
        kernel = np.ones((3,3), np.uint8)
        return cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=1)

    def _exact_contour_mask(self, red_mask):
        """生成精准轮廓蒙版"""
        # 精准轮廓查找
        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        # 找到最大有效轮廓（面积>50像素）
        main_contour = max(
            [c for c in contours if cv2.contourArea(c) > 50],
            key=cv2.contourArea,
            default=None
        )
        if main_contour is None:
            return None

        # 高精度多边形近似（epsilon=0.1%周长）
        epsilon = 0.001 * cv2.arcLength(main_contour, True)
        approx = cv2.approxPolyDP(main_contour, epsilon, True)

        # 创建精准蒙版
        mask = np.zeros_like(red_mask)
        cv2.fillPoly(mask, [approx], 255)
        return mask

    def combine_images(self, image_urls):
        """根据图片数量使用不同的布局方式拼接图片：
        1张图片：直接返回原图
        2张图片：左右对称布局，中间白线分割
        3-4张图片：3:1布局，不足4张用白色填充
        """
        temp_path = None
        try:
            # 下载所有图片
            images = []
            for url in image_urls:  # 处理所有提供的图片
                try:
                    response = requests.get(url)
                    response.raise_for_status()
                    img = Image.open(io.BytesIO(response.content))
                    # 统一转换为RGB模式
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    images.append(img)
                except Exception as e:
                    logger.error(f"[Doubao] Error downloading image {url}: {e}")
                    continue

            if not images:
                logger.error("[Doubao] No images downloaded")
                return None

            # 如果只有一张图片，直接返回
            if len(images) == 1:
                temp_path = os.path.join(self.temp_dir, f"single_{int(time.time())}.jpg")
                images[0].save(temp_path, format='JPEG', quality=95)
                logger.info(f"[Doubao] Successfully saved single image to {temp_path}")
                return self._safe_open_file(temp_path)

            # 获取第一张图片的尺寸作为基准
            base_width = images[0].width
            base_height = images[0].height

            # 设置白线宽度
            line_width = 10

            if len(images) == 2:
                # 左右对称布局
                # 计算两张图片的最大宽高比
                ratios = [img.width / img.height for img in images]
                max_ratio = max(ratios)
                
                # 计算目标画布尺寸，使总宽度约为总高度的2倍
                target_height = int((base_width + line_width) / (2 * max_ratio))
                total_width = base_width
                total_height = target_height
                canvas = Image.new('RGB', (total_width, total_height), 'white')

                # 计算单个图片的目标尺寸
                target_width = (total_width - line_width) // 2
                
                # 调整并粘贴两张图片
                for i, img in enumerate(images):
                    # 计算缩放后的尺寸，保持比例
                    img_ratio = img.width / img.height
                    new_height = target_height
                    new_width = int(new_height * img_ratio)
                    
                    if new_width > target_width:
                        new_width = target_width
                        new_height = int(new_width / img_ratio)
                    
                    # 缩放图片
                    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    # 计算粘贴位置（水平居中）
                    x = i * (target_width + line_width) + (target_width - new_width) // 2
                    y = (target_height - new_height) // 2
                    canvas.paste(resized_img, (x, y))

            else:
                # 3:1布局（3-4张图片）
                # 计算小图尺寸
                small_width = int(base_width / 3)
                small_height = int(base_height / 3)

                # 计算新画布尺寸
                total_width = base_width + small_width + line_width
                total_height = base_height
                canvas = Image.new('RGB', (total_width, total_height), 'white')

                # 粘贴大图到左侧
                canvas.paste(images[0], (0, 0))

                # 创建一个白色的填充图片
                blank_image = Image.new('RGB', (small_width, small_height), 'white')

                # 粘贴小图到右侧，不足的用白色填充
                for i in range(1, 4):
                    x = base_width + line_width
                    y = (i - 1) * (small_height + line_width)
                    
                    if i < len(images):
                        # 如果有实际的图片，使用实际图片
                        small_img = images[i].resize((small_width, small_height), Image.Resampling.LANCZOS)
                        canvas.paste(small_img, (x, y))
                    else:
                        # 如果没有实际的图片，使用白色填充图片
                        canvas.paste(blank_image, (x, y))

            # 保存为临时文件
            temp_path = os.path.join(self.temp_dir, f"combined_{int(time.time())}.jpg")
            canvas.save(temp_path, format='JPEG', quality=95)
            logger.info(f"[Doubao] Successfully saved combined image to {temp_path}")

            return self._safe_open_file(temp_path)

        except Exception as e:
            logger.error(f"[Doubao] Error in combine_images: {e}")
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass
            return None

    def _safe_open_file(self, file_path):
        """安全地打开文件，如果文件被占用则等待并重试"""
        max_retries = 3
        retry_delay = 1  # 秒
        
        for i in range(max_retries):
            try:
                return open(file_path, 'rb')
            except IOError as e:
                if i < max_retries - 1:
                    logger.warning(f"[Doubao] Failed to open file {file_path}, retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"[Doubao] Failed to open file after {max_retries} retries: {e}")
                    return None

    def cleanup_temp_files(self):
        """清理临时文件"""
        try:
            for file in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, file)
                if os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        logger.warning(f"[Doubao] Failed to remove temp file {file_path}: {e}")
            logger.info("[Doubao] Cleaned up temporary files")
        except Exception as e:
            logger.error(f"[Doubao] Error cleaning up temp files: {e}")

    def store_image_data(self, image_urls, operation_type, parent_id=None):
        """存储图片信息"""
        img_id = str(int(time.time()))
        self.image_data[img_id] = {
            "urls": image_urls,
            "timestamp": time.time(),
            "operation": operation_type
        }
        if parent_id:
            self.image_data[img_id]["parent_id"] = parent_id
        return img_id

    def get_image_data(self, img_id):
        """获取图片信息"""
        return self.image_data.get(img_id)

    def validate_image_index(self, img_id, index):
        """验证图片索引的有效性"""
        image_data = self.get_image_data(img_id)
        if not image_data:
            return False, "找不到对应的图片ID"
        if not image_data.get("urls"):
            return False, "找不到图片数据"
        if index > len(image_data["urls"]):
            return False, f"图片索引超出范围，当前只有{len(image_data['urls'])}张图片"
        return True, None

    def _get_dominant_colors(self, image_cv, n_clusters=3):
        """获取图像的主色调"""
        pixels = image_cv.reshape(-1, 3)
        kmeans = KMeans(n_clusters=n_clusters, n_init=10)
        kmeans.fit(pixels)
        return kmeans.cluster_centers_.astype(int)

    def _find_contrast_color(self, image_cv):
        """自动寻找最佳对比色"""
        # 转换为LAB颜色空间
        lab = cv2.cvtColor(image_cv, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        
        # 获取主色调
        dominant_colors = self._get_dominant_colors(image_cv)
        main_color = dominant_colors[0]
        
        # 在LAB空间计算对比色
        target_l = 255 - l.mean()
        target_a = 128 + (128 - a.mean())
        target_b = 128 + (128 - b.mean())
        
        # 限制取值范围
        target_l = np.clip(target_l, 0, 255)
        target_a = np.clip(target_a, 0, 255)
        target_b = np.clip(target_b, 0, 255)
        
        # 转换回BGR颜色空间
        target_lab = np.uint8([[[target_l, target_a, target_b]]])
        return cv2.cvtColor(target_lab, cv2.COLOR_LAB2BGR)[0][0]

    def _dynamic_color_mask(self, orig_cv, marked_cv):
        """动态颜色差异蒙版"""
        # 计算图像差异
        diff = cv2.absdiff(orig_cv, marked_cv)
        diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        
        # 使用自适应阈值
        _, diff_mask = cv2.threshold(diff_gray, 30, 255, cv2.THRESH_BINARY)
        
        # 形态学处理以减少噪点
        kernel = np.ones((3,3), np.uint8)
        diff_mask = cv2.morphologyEx(diff_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        diff_mask = cv2.morphologyEx(diff_mask, cv2.MORPH_OPEN, kernel, iterations=1)
        
        return diff_mask

    def create_mask_from_marked_image(self, original_image_bytes, marked_image_bytes):
        """增强版蒙版生成，支持动态颜色检测"""
        try:
            # 转换并统一尺寸
            orig_cv = self._bytes_to_cv(original_image_bytes)
            marked_cv = self._bytes_to_cv(marked_image_bytes)
            
            if orig_cv.shape != marked_cv.shape:
                marked_cv = cv2.resize(marked_cv, (orig_cv.shape[1], orig_cv.shape[0]))

            # 生成动态差异蒙版
            mask = self._dynamic_color_mask(orig_cv, marked_cv)
            
            # 转换为PIL图像并保持为灰度图
            pil_mask = Image.fromarray(mask).convert('L')
            
            # 保存调试图片
            debug_path = os.path.join(self.temp_dir, "debug_mask.png")
            pil_mask.save(debug_path)
            logger.info(f"[Doubao] Updated mask at: {debug_path}")

            # 转换为RGB并编码返回
            rgb_mask = pil_mask.convert('RGB')
            buffer = io.BytesIO()
            rgb_mask.save(buffer, format="PNG")
            return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"

        except Exception as e:
            logger.error(f"[Doubao] Enhanced mask error: {str(e)}")
            return self._black_mask(orig_cv.shape if 'orig_cv' in locals() else (512,512,3))

    def create_mask_from_circle_selection(self, original_image_bytes, marked_image_bytes, invert=False):
        """增强版精准圈选，支持动态颜色"""
        try:
            # 转换并统一尺寸
            marked_cv = self._bytes_to_cv(marked_image_bytes)
            orig_cv = self._bytes_to_cv(original_image_bytes)
            
            if orig_cv.shape[:2] != marked_cv.shape[:2]:
                marked_cv = cv2.resize(marked_cv, (orig_cv.shape[1], orig_cv.shape[0]))

            # 生成动态差异蒙版
            mask = self._dynamic_color_mask(orig_cv, marked_cv)
            
            # 获取精准轮廓
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return self._black_mask(orig_cv.shape)

            # 找到最大有效轮廓
            main_contour = max(
                [c for c in contours if cv2.contourArea(c) > 50],
                key=cv2.contourArea,
                default=None
            )
            if main_contour is None:
                return self._black_mask(orig_cv.shape)

            # 创建轮廓蒙版
            mask = np.zeros(orig_cv.shape[:2], dtype=np.uint8)
            cv2.drawContours(mask, [main_contour], -1, 255, -1)

            # 反选处理 - 确保圈选区域为黑色(0)，外部为白色(255)
            if invert:
                mask = cv2.bitwise_not(mask)

            # 转换为PIL图像
            pil_mask = Image.fromarray(mask).convert('L')
            
            # 保存调试图片
            debug_path = os.path.join(self.temp_dir, "debug_mask.png")
            pil_mask.save(debug_path)
            logger.info(f"[Doubao] Updated mask at: {debug_path}")
            
            # 转换为RGB并编码返回
            rgb_mask = pil_mask.convert('RGB')
            buffer = io.BytesIO()
            rgb_mask.save(buffer, format="PNG")
            return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"

        except Exception as e:
            logger.error(f"[Doubao] Enhanced circle mask error: {str(e)}")
            return self._black_mask(orig_cv.shape if 'orig_cv' in locals() else (512,512,3))

    def _black_mask(self, shape):
        """生成全黑蒙版（表示无修改区域）"""
        if isinstance(shape, tuple) and len(shape) >= 2:
            height, width = shape[:2]
        else:
            height, width = shape[0], shape[1]
        mask = Image.new('L', (width, height), 0)  # 使用'L'模式创建灰度图
        buffer = io.BytesIO()
        mask.save(buffer, format="PNG")
        return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
