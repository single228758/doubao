import sqlite3
import json
import time
import os
from common.log import logger

class ImageStorage:
    def __init__(self, db_path, retention_days=7):
        self.db_path = db_path
        self.retention_days = retention_days
        self._init_db()
        
    def _init_db(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # 创建图片表，增加edit_chain和operation_history字段
        c.execute('''CREATE TABLE IF NOT EXISTS images
                    (id TEXT PRIMARY KEY,
                     urls TEXT NOT NULL,
                     operation_type TEXT NOT NULL,
                     operation_params TEXT,
                     parent_id TEXT,
                     edit_chain TEXT,
                     operation_history TEXT,
                     created_at INTEGER)''')
        
        conn.commit()
        conn.close()
        
    def store_image(self, img_id: str, image_info: dict):
        """存储图片信息
        Args:
            img_id: 图片ID
            image_info: 图片信息，包含urls、type、operation_params等
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            # 获取父图片的编辑链
            edit_chain = []
            operation_history = []
            parent_id = image_info.get("parent_id")
            
            if parent_id:
                c.execute('SELECT edit_chain, operation_history FROM images WHERE id = ?', (parent_id,))
                result = c.fetchone()
                if result:
                    edit_chain = json.loads(result[0]) if result[0] else []
                    operation_history = json.loads(result[1]) if result[1] else []
            
            # 更新编辑链
            if parent_id:
                edit_chain.append(parent_id)
            
            # 更新操作历史
            operation_history.append({
                'id': img_id,
                'type': image_info.get("type"),
                'params': image_info.get("operation_params"),
                'timestamp': image_info.get("create_time", int(time.time()))
            })
            
            # 存储图片信息
            c.execute('''INSERT INTO images 
                        (id, urls, operation_type, operation_params, parent_id, edit_chain, operation_history, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                     (img_id, 
                      json.dumps(image_info.get("urls", [])),
                      image_info.get("type"),
                      json.dumps(image_info.get("operation_params", {})),
                      parent_id,
                      json.dumps(edit_chain),
                      json.dumps(operation_history),
                      image_info.get("create_time", int(time.time()))))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"[Doubao] Error storing image info: {e}")
            raise e
        finally:
            conn.close()
        
    def get_image(self, img_id: str) -> dict:
        """获取图片信息
        Args:
            img_id: 图片ID
        Returns:
            dict: 图片信息
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            c.execute('''SELECT id, urls, operation_type, operation_params, 
                               parent_id, edit_chain, operation_history, created_at 
                        FROM images WHERE id = ?''', (img_id,))
            result = c.fetchone()
            
            if result:
                image_info = {
                    'id': result[0],
                    'urls': json.loads(result[1]),
                    'type': result[2],
                    'operation_params': json.loads(result[3]),
                    'parent_id': result[4],
                    'edit_chain': json.loads(result[5]) if result[5] else [],
                    'operation_history': json.loads(result[6]) if result[6] else [],
                    'create_time': result[7]
                }
                return image_info
                
            return None
            
        except Exception as e:
            logger.error(f"[Doubao] Error getting image info: {e}")
            return None
        finally:
            conn.close()
        
    def validate_image_index(self, img_id: str, index: int) -> tuple:
        """验证图片序号是否有效
        Args:
            img_id: 图片ID
            index: 图片序号(1-4)
        Returns:
            tuple: (是否有效, 错误信息)
        """
        try:
            image_data = self.get_image(img_id)
            if not image_data:
                return False, "找不到对应的图片ID"
                
            if not isinstance(index, int):
                return False, "图片序号必须是数字"
                
            if index < 1 or index > 4:
                return False, "图片序号必须是1-4之间的数字"
                
            urls = image_data.get("urls", [])
            if not urls or len(urls) < index:
                return False, "图片序号超出范围"
                
            return True, None
            
        except Exception as e:
            logger.error(f"[Doubao] Error validating image index: {e}")
            return False, "验证图片序号时出错"
            
    def get_latest_image(self):
        '''获取最新的一条图片记录'''
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, urls, operation_type, operation_params, parent_id, created_at 
                FROM images 
                ORDER BY created_at DESC 
                LIMIT 1
            ''')
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'urls': json.loads(row[1]),
                    'type': row[2],
                    'operation_params': json.loads(row[3]) if row[3] else {},
                    'parent_id': row[4],
                    'created_at': row[5]
                }
            return None
        except Exception as e:
            logger.error(f"[ImageStorage] Error getting latest image: {e}")
            return None
        finally:
            if 'conn' in locals():
                conn.close() 