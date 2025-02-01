import os
import time
import requests
from PIL import Image, ImageDraw, ImageFilter
import io
import base64
from common.log import logger

class ImageProcessor:
    def __init__(self, temp_dir, uploader=None):
        self.temp_dir = temp_dir
        self.uploader = uploader
        self.image_data = {}
        self._ensure_temp_dir()

    def _ensure_temp_dir(self):
        """确保临时目录存在"""
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)

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

    def create_mask_from_marked_image(self, original_image_bytes, marked_image_bytes, color_threshold=(200, 50, 50)):
        """从标记图片创建蒙版
        Args:
            original_image_bytes: 原图字节数据
            marked_image_bytes: 带有红色标记的图片字节数据
            color_threshold: RGB颜色阈值,用于识别红色区域
        Returns:
            str: base64编码的蒙版数据
        """
        try:
            # 打开原图和标记图片
            with io.BytesIO(original_image_bytes) as orig_buf, io.BytesIO(marked_image_bytes) as marked_buf:
                orig_img = Image.open(orig_buf).convert('RGB')
                marked_img = Image.open(marked_buf).convert('RGB')
                
                # 确保两张图片大小相同
                if orig_img.size != marked_img.size:
                    marked_img = marked_img.resize(orig_img.size)
                
                width, height = orig_img.size
                
                # 创建黑色背景的蒙版
                mask = Image.new('RGB', (width, height), 'black')
                mask_pixels = mask.load()
                orig_pixels = orig_img.load()
                marked_pixels = marked_img.load()
                
                # 遍历每个像素
                for x in range(width):
                    for y in range(height):
                        # 获取原图和标记图片的像素值
                        orig_r, orig_g, orig_b = orig_pixels[x, y]
                        marked_r, marked_g, marked_b = marked_pixels[x, y]
                        
                        # 如果标记图片的像素与原图不同,说明是标记区域
                        if (abs(marked_r - orig_r) > 30 or 
                            abs(marked_g - orig_g) > 30 or 
                            abs(marked_b - orig_b) > 30):
                            mask_pixels[x, y] = (255, 255, 255)  # 设置为白色
                
                # 对蒙版进行膨胀操作,使标记区域更加连续
                mask = mask.filter(ImageFilter.MaxFilter(3))
                
                # 转换为base64
                buffer = io.BytesIO()
                mask.save(buffer, format='PNG')
                mask_base64 = base64.b64encode(buffer.getvalue()).decode()
                
                return f"data:image/png;base64,{mask_base64}"
                
        except Exception as e:
            logger.error(f"[Doubao] Error creating mask: {e}")
            return None

    def create_mask_from_circle_selection(self, original_image_bytes, marked_image_bytes, invert=False):
        """从圈选图片创建蒙版
        Args:
            original_image_bytes: 原图字节数据
            marked_image_bytes: 带有圈选标记的图片字节数据
            invert: 是否反选（选择圈外区域）
        Returns:
            str: base64编码的蒙版数据
        """
        try:
            # 打开原图和标记图片
            with io.BytesIO(original_image_bytes) as orig_buf, io.BytesIO(marked_image_bytes) as marked_buf:
                orig_img = Image.open(orig_buf).convert('RGB')
                marked_img = Image.open(marked_buf).convert('RGB')
                
                # 确保两张图片大小相同
                if orig_img.size != marked_img.size:
                    marked_img = marked_img.resize(orig_img.size)
                
                width, height = orig_img.size
                
                # 创建黑色背景的蒙版
                mask = Image.new('RGB', (width, height), 'black')
                mask_pixels = mask.load()
                orig_pixels = orig_img.load()
                marked_pixels = marked_img.load()
                
                # 创建临时蒙版用于存储标记线条
                line_mask = Image.new('RGB', (width, height), 'black')
                line_pixels = line_mask.load()
                
                # 检测标记区域
                for x in range(width):
                    for y in range(height):
                        orig_r, orig_g, orig_b = orig_pixels[x, y]
                        marked_r, marked_g, marked_b = marked_pixels[x, y]
                        
                        # 检测红色标记或明显的颜色差异
                        if (marked_r > 150 and marked_g < 100 and marked_b < 100) or \
                           (abs(marked_r - orig_r) > 30 and marked_r > marked_g and marked_r > marked_b):
                            line_pixels[x, y] = (255, 255, 255)
                
                # 找到所有标记点
                white_pixels = []
                for x in range(width):
                    for y in range(height):
                        if line_pixels[x, y] == (255, 255, 255):
                            white_pixels.append((x, y))
                
                if white_pixels:
                    # 计算中心点
                    center_x = sum(x for x, _ in white_pixels) // len(white_pixels)
                    center_y = sum(y for _, y in white_pixels) // len(white_pixels)
                    
                    # 使用泛洪填充
                    if len(white_pixels) < width * height * 0.1:  # 如果标记区域较小，认为是圈选
                        ImageDraw.floodfill(line_mask, (center_x, center_y), (255, 255, 255))
                    
                    # 根据是否反选设置最终蒙版
                    for x in range(width):
                        for y in range(height):
                            if not invert:
                                # 正常模式：标记区域为白色
                                if line_pixels[x, y] == (255, 255, 255):
                                    mask_pixels[x, y] = (255, 255, 255)
                            else:
                                # 反选模式：标记区域为黑色，其他区域为白色
                                if line_pixels[x, y] == (255, 255, 255):
                                    mask_pixels[x, y] = (0, 0, 0)
                                else:
                                    mask_pixels[x, y] = (255, 255, 255)
                
                # 对蒙版进行平滑处理
                mask = mask.filter(ImageFilter.MaxFilter(3))
                
                # 保存蒙版图片到storage目录
                storage_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'storage')
                os.makedirs(storage_dir, exist_ok=True)
                mask_path = os.path.join(storage_dir, 'mask.png')
                mask.save(mask_path)
                logger.info(f"[Doubao] Saved mask image to: {mask_path}")
                
                # 转换为base64
                buffer = io.BytesIO()
                mask.save(buffer, format='PNG')
                mask_base64 = base64.b64encode(buffer.getvalue()).decode()
                
                return f"data:image/png;base64,{mask_base64}"
                
        except Exception as e:
            logger.error(f"[Doubao] Error creating circle selection mask: {e}")
            return None 