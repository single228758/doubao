import os
import time
import uuid
import hmac
import json
import zlib
import base64
import hashlib
import logging
import requests
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 配置日志
logger = logging.getLogger(__name__)

class ImageUploader:
    def __init__(self, config):
        self.config = config
        self.headers = {
            'cookie': config['auth']['cookie'],
            'msToken': config['auth']['msToken'],
            'x-bogus': config['auth']['a_bogus']
        }
        
        # 配置日志
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(handler)
        
        # 配置请求会话
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _generate_s_param(self):
        """生成s参数，使用固定规则"""
        timestamp = int(time.time() * 1000)
        seed = timestamp % 1000000
        chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
        result = []
        for i in range(11):
            index = (seed + i * 7) % len(chars)
            result.append(chars[index])
        s_param = ''.join(result)
        self.logger.debug(f"[Doubao] Generated s_param: {s_param}")
        return s_param

    def _get_authorization_header(self, access_key, secret_key, region, service, request_parameters, amz_date, datestamp, security_token, method='GET', payload=''):
        """生成 AWS 授权头"""
        self.logger.debug(f"[Doubao] Generating authorization header with parameters:")
        self.logger.debug(f"Access Key: {access_key}")
        self.logger.debug(f"Region: {region}")
        self.logger.debug(f"Service: {service}")
        self.logger.debug(f"Date: {amz_date}")
        self.logger.debug(f"Method: {method}")
        
        # 1. 参数编码和排序
        def encode_param(param):
            return requests.utils.quote(str(param), safe='')
            
        # 构建规范化查询字符串
        canonical_querystring = '&'.join([
            f"{k}={encode_param(v)}" 
            for k, v in sorted(request_parameters.items())
        ])
        self.logger.debug(f"[Doubao] Canonical Query String: {canonical_querystring}")
        
        # 2. 构建规范化请求头（包含host）
        canonical_headers = (
            f'host:imagex.bytedanceapi.com\n'
            f'x-amz-date:{amz_date}\n'
            f'x-amz-security-token:{security_token}\n'
        )
        self.logger.debug(f"[Doubao] Canonical Headers:\n{canonical_headers}")
        
        # 3. 构建签名的头部列表（包含host）
        signed_headers = 'host;x-amz-date;x-amz-security-token'
        
        # 4. 计算请求体的hash
        payload_hash = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        
        # 5. 构建规范化请求
        canonical_request = '\n'.join([
            method,
            '/',
            canonical_querystring,
            canonical_headers,
            signed_headers,
            payload_hash
        ])
        self.logger.debug(f"[Doubao] Canonical Request:\n{canonical_request}")
        
        # 6. 创建待签名字符串
        algorithm = 'AWS4-HMAC-SHA256'
        credential_scope = f"{datestamp}/{region}/{service}/aws4_request"
        string_to_sign = '\n'.join([
            algorithm,
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
        ])
        self.logger.debug(f"[Doubao] String to Sign:\n{string_to_sign}")
        
        # 7. 计算签名密钥
        k_date = hmac.new(f'AWS4{secret_key}'.encode('utf-8'), datestamp.encode('utf-8'), hashlib.sha256).digest()
        k_region = hmac.new(k_date, region.encode('utf-8'), hashlib.sha256).digest()
        k_service = hmac.new(k_region, service.encode('utf-8'), hashlib.sha256).digest()
        k_signing = hmac.new(k_service, b'aws4_request', hashlib.sha256).digest()
        
        # 8. 计算最终签名
        signature = hmac.new(k_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
        self.logger.debug(f"[Doubao] Signature: {signature}")
        
        # 9. 构建授权头
        authorization_header = (
            f"{algorithm} "
            f"Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        self.logger.debug(f"[Doubao] Authorization Header: {authorization_header}")
        
        return authorization_header, canonical_querystring

    def upload_and_process_image(self, image_data):
        """上传并处理图片"""
        try:
            self.logger.debug("[Doubao] Starting image upload process...")
            
            # 0. 检查配额（暂不实现）
            
            # 1. 获取新的token
            self.logger.debug("[Doubao] Getting fresh token...")
            token_info = self.get_upload_token()
            if not token_info:
                raise Exception("Failed to get upload token")
            self.logger.debug(f"[Doubao] Got fresh token: {token_info}")

            # 2. 申请上传
            request_parameters = {
                "Action": "ApplyImageUpload",
                "Version": "2018-08-01",
                "ServiceId": token_info['space_name'],
                "FileSize": str(len(image_data)),
                "FileExtension": ".png",
                "s": self._generate_s_param()
            }
            self.logger.debug(f"[Doubao] Request parameters: {request_parameters}")

            t = datetime.utcnow()
            amz_date = t.strftime('%Y%m%dT%H%M%SZ')
            datestamp = t.strftime('%Y%m%d')

            authorization, canonical_querystring = self._get_authorization_header(
                token_info['access_key_id'],
                token_info['secret_access_key'],
                'cn-north-1',
                'imagex',
                request_parameters,
                amz_date,
                datestamp,
                token_info['session_token']
            )

            # 只保留必要的请求头
            request_headers = {
                'accept': '*/*',
                'authorization': authorization,
                'x-amz-date': amz_date,
                'x-amz-security-token': token_info['session_token']
            }
            self.logger.debug(f"[Doubao] Request headers: {request_headers}")

            url = f'https://imagex.bytedanceapi.com/?{canonical_querystring}'
            self.logger.debug(f"[Doubao] Request URL: {url}")
            
            response = self.session.get(url, headers=request_headers)
            self.logger.debug(f"[Doubao] Response status: {response.status_code}")
            self.logger.debug(f"[Doubao] Response content: {response.text}")
            
            if response.status_code != 200:
                raise Exception(f"Apply upload failed: {response.text}")

            upload_info = response.json()
            if 'ResponseMetadata' in upload_info and 'Error' in upload_info['ResponseMetadata']:
                error = upload_info['ResponseMetadata']['Error']
                raise Exception(f"API Error: {error.get('Code')} - {error.get('Message')}")

            # 3. 上传图片
            store_info = upload_info['Result']['UploadAddress']['StoreInfos'][0]
            upload_host = upload_info['Result']['UploadAddress']['UploadHosts'][0]
            url = f"https://{upload_host}/upload/v1/{store_info['StoreUri']}"
            self.logger.debug(f"[Doubao] Upload URL: {url}")

            # 计算CRC32
            crc32 = format(zlib.crc32(image_data) & 0xFFFFFFFF, '08x')
            self.logger.debug(f"[Doubao] CRC32: {crc32}")

            upload_headers = {
                'Authorization': store_info['Auth'],
                'Content-CRC32': crc32,
                'Content-Type': 'application/octet-stream',
                'Content-Disposition': 'attachment; filename="image.png"'
            }
            self.logger.debug(f"[Doubao] Upload headers: {upload_headers}")

            response = self.session.post(url, headers=upload_headers, data=image_data)
            result = response.json()
            self.logger.debug(f"[Doubao] Upload response: {result}")
            
            if 'code' not in result or result['code'] != 2000:
                raise Exception(f"Upload failed: {json.dumps(result)}")

            # 4. 提交上传
            commit_result = self.commit_upload(token_info, upload_info)
            if not commit_result:
                raise Exception("Failed to commit upload")

            # 获取背景蒙版
            try:
                mask_result = self.get_background_mask(store_info['StoreUri'])
                if mask_result and mask_result.get('code') == 0:
                    return {
                        'success': True,
                        'image_key': store_info['StoreUri'],
                        'file_info': {
                            'main_url': mask_result.get('url', ''),
                            'mask_url': mask_result.get('url', '')
                        },
                        'mask': mask_result.get('mask', ''),
                        'without_background': mask_result.get('without_background', False)
                    }
            except Exception as e:
                self.logger.error(f"[Doubao] Failed to get background mask: {e}")
                
            # 如果获取背景蒙版失败，返回错误
            return {
                'success': False,
                'error': 'Failed to get background mask'
            }

        except Exception as e:
            self.logger.error(f"[Doubao] Error in upload process: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def get_upload_token(self):
        """获取上传token"""
        url = 'https://www.doubao.com/alice/upload/auth_token'
        
        params = {
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
            'msToken': self.headers['msToken'],
            'a_bogus': self.headers['x-bogus']
        }
        
        request_headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'cookie': self.headers['cookie'],
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
            'msToken': self.headers['msToken'],
            'x-bogus': self.headers['x-bogus']
        }
        
        data = {
            "scene": "bot_chat",
            "data_type": "file"
        }
        
        response = self.session.post(url, headers=request_headers, params=params, json=data)
        if response.status_code != 200:
            raise Exception(f"Get token failed: {response.text}")
        
        result = response.json()
        if result.get('code') != 0:
            raise Exception(f"Get token error: {result}")
        
        auth_data = result.get('data', {}).get('auth', {})
        token_info = {
            'access_key_id': auth_data.get('access_key_id'),
            'secret_access_key': auth_data.get('secret_access_key'),
            'session_token': auth_data.get('session_token'),
            'space_name': 'a9rns2rl98'  # 固定值
        }
        
        return token_info

    def commit_upload(self, token_info, upload_info):
        """提交上传"""
        t = datetime.utcnow()
        amz_date = t.strftime('%Y%m%dT%H%M%SZ')
        datestamp = t.strftime('%Y%m%d')

        request_parameters = {
            "Action": "CommitImageUpload",
            "Version": "2018-08-01",
            "ServiceId": token_info['space_name']
        }

        data = {"SessionKey": upload_info['Result']['UploadAddress']['SessionKey']}
        payload = json.dumps(data)

        authorization, canonical_querystring = self._get_authorization_header(
            token_info['access_key_id'],
            token_info['secret_access_key'],
            'cn-north-1',
            'imagex',
            request_parameters,
            amz_date,
            datestamp,
            token_info['session_token'],
            method='POST',
            payload=payload
        )

        # 只保留必要的请求头
        request_headers = {
            'host': 'imagex.bytedanceapi.com',
            'authorization': authorization,
            'x-amz-date': amz_date,
            'x-amz-security-token': token_info['session_token'],
            'content-type': 'application/json'  # 这个头不参与签名计算
        }

        url = f'https://imagex.bytedanceapi.com/?{canonical_querystring}'
        response = self.session.post(url, headers=request_headers, json=data)
        
        if response.status_code != 200:
            raise Exception(f"Commit upload failed: {response.text}")
            
        result = response.json()
        if 'ResponseMetadata' in result and 'Error' in result['ResponseMetadata']:
            error = result['ResponseMetadata']['Error']
            raise Exception(f"API Error: {error.get('Code')} - {error.get('Message')}")
            
        return result 

    def get_background_mask(self, image_key):
        """获取背景蒙版"""
        url = 'https://www.doubao.com/samantha/image/image_get_background_mask'
        
        params = {
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
            'msToken': self.headers['msToken'],
            'a_bogus': self.headers['x-bogus']
        }
        
        data = {
            "tos_key": image_key,
            "is_from_local": True
        }
        
        request_headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'cookie': self.headers['cookie'],
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
            'msToken': self.headers['msToken'],
            'x-bogus': self.headers['x-bogus']
        }
        
        response = self.session.post(url, headers=request_headers, params=params, json=data)
        if response.status_code != 200:
            self.logger.error(f"Get background mask failed: {response.text}")
            raise Exception(f"Get background mask failed: {response.text}")
        
        result = response.json()
        if result.get('code') != 0:
            self.logger.error(f"Get background mask error: {result}")
            raise Exception(f"Get background mask error: {result}")
        
        # 记录完整的响应数据用于调试
        self.logger.debug(f"Background mask response: {json.dumps(result, indent=2)}")
        
        return result 