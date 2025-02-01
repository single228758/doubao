import json
import requests
from common.log import logger
import uuid
import time

class ApiClient:
    def __init__(self, token_manager):
        self.token_manager = token_manager
        self.base_url = "https://www.doubao.com"

    def _get_headers(self):
        """获取请求头"""
        auth = self.token_manager.config.get('auth', {})
        return {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9",
            "agw-js-conv": "str",
            "content-type": "application/json",
            "cookie": auth.get("cookie", ""),
            "last-event-id": "undefined",
            "origin": "https://www.doubao.com",
            "priority": "u=1, i",
            "referer": "https://www.doubao.com/chat/create-image",
            "sec-ch-ua": '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "x-flow-trace": auth.get("x-flow-trace", "")
        }

    def _get_params(self):
        """获取请求参数"""
        auth = self.token_manager.config.get('auth', {})
        return {
            "aid": "497858",
            "device_id": "7450669489257268771",
            "device_platform": "web",
            "language": "zh",
            "pkg_type": "release_version",
            "real_aid": "497858",
            "region": "CN",
            "samantha_web": "1",
            "sys_region": "CN",
            "tea_uuid": "7397236635946141218",
            "use-olympus-account": "1",
            "version_code": "20800",
            "web_id": "7397236635946141218",
            "msToken": auth.get("msToken", ""),
            "a_bogus": auth.get("a_bogus", "")
        }

    def send_request(self, data, endpoint="/samantha/chat/completion"):
        """发送请求"""
        try:
            url = self.base_url + endpoint
            headers = self._get_headers()
            
            # 如果是图像生成请求，需要特殊处理
            if endpoint == "/samantha/chat/completion" and "messages" in data:
                # 确保content是正确的JSON字符串格式
                if isinstance(data["messages"][0]["content"], dict):
                    data["messages"][0]["content"] = json.dumps(data["messages"][0]["content"])
            
            response = requests.post(
                url,
                json=data,
                headers=headers,
                params=self._get_params(),
                stream=endpoint == "/samantha/chat/completion",
                timeout=60
            )
            
            response.raise_for_status()
            
            # 如果是流式响应
            if endpoint == "/samantha/chat/completion":
                image_urls = []
                conversation_id = None
                section_id = None
                reply_id = None
                
                for line in response.iter_lines():
                    if not line:
                        continue
                        
                    line = line.decode('utf-8')
                    if not line.startswith("data:"):
                        continue
                        
                    try:
                        data = json.loads(line[5:])
                        event_data = json.loads(data.get("event_data", "{}"))
                        logger.debug(f"[Doubao] Response event_data: {event_data}")
                        
                        if "conversation_id" in event_data:
                            conversation_id = event_data["conversation_id"]
                            section_id = event_data.get("section_id")
                            logger.info(f"[Doubao] Found conversation info: id={conversation_id}, section={section_id}")
                            # 从event_data中提取reply_id
                            if "reply_id" in event_data:
                                reply_id = event_data["reply_id"]
                                logger.info(f"[Doubao] Found reply_id: {reply_id}")
                        
                        if "message" in event_data:
                            message = event_data["message"]
                            logger.debug(f"[Doubao] Message data: {message}")
                            if message.get("content_type") == 2010:  # 图片响应
                                content = json.loads(message["content"])
                                if "data" in content:
                                    for img_data in content["data"]:
                                        if "image_raw" in img_data:
                                            url = img_data["image_raw"]["url"]
                                            image_urls.append(url)
                                            logger.info(f"[Doubao] Found image URL: {url}")
                                            
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logger.error(f"[Doubao] Error processing response: {e}")
                        continue
                
                return {
                    "urls": image_urls,
                    "conversation_id": conversation_id,
                    "section_id": section_id,
                    "reply_id": reply_id
                }
            else:
                # 非流式响应直接返回JSON
                return response.json()
            
        except Exception as e:
            logger.error(f"[Doubao] Error sending request: {e}")
            return None

    def edit_image(self, image_url: str, edit_prompt: str, conversation_id: str, section_id: str, reply_id: str):
        """编辑图片"""
        try:
            # 从图片URL中提取token
            image_token = image_url.split("/")[-1].split("~")[0]
            
            # 构建编辑请求
            data = {
                "messages": [{
                    "content": json.dumps({
                        "text": edit_prompt,
                        "edit_image": {
                            "edit_image_url": image_url,
                            "edit_image_token": image_token,
                            "description": "",  # 描述可以为空
                            "outline_id": None
                        }
                    }),
                    "content_type": 2009,
                    "attachments": []
                }],
                "completion_option": {
                    "is_regen": False,
                    "with_suggest": False,
                    "need_create_conversation": False,
                    "launch_stage": 1,
                    "is_replace": False,
                    "is_delete": False,
                    "message_from": 0,
                    "event_id": "0"
                },
                "section_id": section_id,
                "conversation_id": conversation_id,
                "local_message_id": str(uuid.uuid1()),
                "reply_id": reply_id
            }
            
            result = self.send_request(data)
            if result and "urls" in result:
                return result["urls"]
            logger.debug(f"[Doubao] Edit image result: {result}")  # 添加调试日志
            return None
        except Exception as e:
            logger.error(f"[Doubao] Error in edit_image: {e}")
            return None

    def outpaint_image(self, image_url, ratio, conversation_id=None, section_id=None, reply_id=None):
        """扩展图片"""
        try:
            # 计算扩展比例
            expand_ratio = 0.3888889  # 7/18，用于将1:1扩展到16:9
            max_expand = 0.5  # 最大扩展比例
            
            # 根据不同比例设置扩展参数
            if ratio == "16:9":
                left = right = expand_ratio
                top = bottom = 0
            elif ratio == "9:16":
                left = right = 0
                top = bottom = expand_ratio
            elif ratio == "4:3":
                left = right = 0.166667  # 1/6
                top = bottom = 0
            elif ratio == "1:1":
                left = right = top = bottom = 0
            elif ratio == "max":
                left = right = top = bottom = max_expand
            else:
                return None
            
            data = {
                "messages": [{
                    "content": json.dumps({
                        "text": "按新尺寸生成图片",
                        "edit_image": {
                            "edit_image_url": image_url,
                            "edit_image_token": image_url.split("/")[-1].split("~")[0],
                            "description": "扩展图片",
                            "ability": "outpainting",
                            "top": top,
                            "bottom": bottom,
                            "left": left,
                            "right": right,
                            "is_edit_local_image": False,
                            "is_edit_local_image_v2": "false"
                        }
                    }),
                    "content_type": 2009,
                    "attachments": []
                }],
                "completion_option": {
                    "is_regen": False,
                    "with_suggest": False,
                    "need_create_conversation": not bool(conversation_id),
                    "launch_stage": 1,
                    "is_replace": False,
                    "is_delete": False,
                    "message_from": 0,
                    "event_id": "0"
                }
            }
            
            if conversation_id:
                data["conversation_id"] = conversation_id
                data["section_id"] = section_id
                data["local_message_id"] = str(uuid.uuid1())
                if reply_id:
                    data["reply_id"] = reply_id
            
            result = self.send_request(data)
            return result["urls"] if result else None
            
        except Exception as e:
            logger.error(f"[Doubao] Error outpainting image: {e}")
            return None