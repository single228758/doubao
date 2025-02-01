import requests
import logging
import threading
import time
from common.log import logger

class TokenManager:
    def __init__(self, config):
        self.config = config
        self._lock = threading.Lock()
        self._last_refresh_time = 0
        self._refresh_interval = 1800  # 30分钟刷新一次

    def get_headers(self):
        """获取请求头"""
        auth = self.config.get('auth', {})
        return {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'cookie': auth.get('cookie', ''),
            'origin': 'https://www.doubao.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.doubao.com/chat/create-image',
            'sec-ch-ua': '"Microsoft Edge";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0',
            'msToken': auth.get('msToken', ''),
            'x-bogus': auth.get('a_bogus', '')
        }

    def get_request_params(self):
        """获取请求参数"""
        auth = self.config.get('auth', {})
        return {
            'version_code': '20800',
            'language': 'zh',
            'device_platform': 'web',
            'aid': '497858',
            'real_aid': '497858',
            'pc_version': '1.51.81',
            'pkg_type': 'release_version',
            'device_id': '7460980997308483113',
            'web_id': '7460981012103120435',
            'tea_uuid': '7460981012103120435',
            'use-olympus-account': '1',
            'region': 'CN',
            'sys_region': 'CN',
            'samantha_web': '1',
            'msToken': auth.get('msToken', ''),
            'a_bogus': auth.get('a_bogus', '')
        }

    def refresh_token(self):
        """刷新token"""
        with self._lock:
            current_time = time.time()
            if current_time - self._last_refresh_time < self._refresh_interval:
                return

            try:
                headers = self.get_headers()
                params = self.get_request_params()
                
                response = requests.get(
                    "https://www.doubao.com/chat/create-image",
                    headers=headers,
                    params=params
                )
                response.raise_for_status()

                # 更新最后刷新时间
                self._last_refresh_time = current_time
                logger.info("[Doubao] Token refreshed successfully")

            except Exception as e:
                logger.error(f"[Doubao] Failed to refresh token: {e}")
                raise 