import bcrypt
import jwt
import datetime
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import mysql.connector
from mysql.connector import errorcode
import mysql.connector.pooling
from contextlib import contextmanager
import uuid
from decimal import Decimal

def count_length(text):
    """计算文本字符数，只有中文汉字算2个，其他字符（包括中文标点）都算1个"""
    length = 0
    for char in text:
        if '\u4e00' <= char <= '\u9fff':  # 中文汉字范围
            length += 2
        else:                             # 其他字符（ASCII、中文标点等）
            length += 1
    return length

def estimate_tokens(text):
    """估算文本的tokens数量
    根据官方比例：1000 tokens ≈ 1600中文字符
    """
    if not text:
        return 0

    char_count = len(text)  # 使用实际字符数，不是加权字符数
    # 1000 tokens = 1600 字符，所以 1 token = 1.6 字符
    tokens = char_count / 1.6
    return int(tokens)

class MinimaxDatabaseManager:
    def __init__(self, host='0.0.0.0', user='root', password='Cloudsway00@12Mk3', database='minimax'):
        self.host = host
        self.user = user
        self.password = password
        self.database = database

        # 创建连接池配置
        self.pool_config = {
            'pool_name': 'minimax_pool',
            'pool_size': 10,
            'pool_reset_session': True,
            'host': self.host,
            'user': self.user,
            'password': self.password,
            'database': self.database,
            'autocommit': True,
            'charset': 'utf8mb4',
            'use_unicode': True,
            'get_warnings': False,
            'raise_on_warnings': False,
            'connection_timeout': 30,
            'sql_mode': 'STRICT_TRANS_TABLES',
        }

        try:
            # 首先尝试创建数据库
            self._create_database_if_not_exists()

            # 创建连接池
            self.pool = mysql.connector.pooling.MySQLConnectionPool(**self.pool_config)

            # 初始化表和密钥
            with self.get_connection() as connection:
                self.create_tables(connection)
                self.ensure_keys_exist(connection)
                self.init_pricing_config(connection)
            print("MiniMax database pool created successfully.")
        except mysql.connector.Error as err:
            print(f"Error creating connection pool: {err}")
            raise

    def _create_database_if_not_exists(self):
        """创建数据库（如果不存在）"""
        config = {
            'host': self.host,
            'user': self.user,
            'password': self.password,
            'charset': 'utf8mb4',
            'use_unicode': True,
        }

        connection = mysql.connector.connect(**config)
        cursor = connection.cursor()
        try:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.database} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            connection.commit()
            print(f"Database '{self.database}' created or already exists.")
        finally:
            cursor.close()
            connection.close()

    @contextmanager
    def get_connection(self):
        """获取连接池中的连接"""
        connection = None
        try:
            connection = self.pool.get_connection()
            yield connection
        except mysql.connector.Error as err:
            print(f"Database connection error: {err}")
            if connection:
                connection.rollback()
            raise
        finally:
            if connection and connection.is_connected():
                connection.close()

    def create_tables(self, connection=None):
        if connection is None:
            with self.get_connection() as conn:
                return self.create_tables(conn)

        cursor = connection.cursor()
        try:
            # 创建用户表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(255) UNIQUE NOT NULL,
                    username VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')

            # 创建 bearer_tokens 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bearer_tokens (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    token TEXT NOT NULL,
                    user_id VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME NOT NULL,
                    is_revoked BOOLEAN DEFAULT FALSE,
                    call_count INT DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # 创建 secure_key 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS secure_key (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    private_key TEXT NOT NULL,
                    public_key TEXT NOT NULL
                )
            ''')

            # 创建新的 api_calls 表（详细计费记录）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS api_calls (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    task_type VARCHAR(100) NOT NULL COMMENT '任务类型：sync_tts/async_tts/voice_design/voice_clone/video_generation等',
                    model_name VARCHAR(100) DEFAULT NULL COMMENT '使用的模型名称',
                    request_text TEXT DEFAULT NULL COMMENT '请求的文本内容',
                    char_count INT NOT NULL DEFAULT 0 COMMENT '字符数统计',
                    unit_price DECIMAL(10,4) NOT NULL DEFAULT 0.0000 COMMENT '单价（元/万字符 或 元/音色）',
                    cost_amount DECIMAL(10,4) NOT NULL DEFAULT 0.0000 COMMENT '本次消费金额（元）',
                    billing_unit ENUM('per_10k_chars', 'per_voice', 'per_video', 'per_million_tokens') NOT NULL DEFAULT 'per_10k_chars' COMMENT '计费单位',
                    endpoint VARCHAR(200) NOT NULL COMMENT 'API端点路径',
                    request_params JSON DEFAULT NULL COMMENT '请求参数（JSON格式）',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    INDEX idx_user_id (user_id),
                    INDEX idx_task_type (task_type),
                    INDEX idx_created_at (created_at)
                )
            ''')

            # 创建定价配置表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pricing_config (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    task_type VARCHAR(100) NOT NULL COMMENT '任务类型',
                    model_name VARCHAR(100) NOT NULL COMMENT '模型名称',
                    unit_price DECIMAL(10,4) NOT NULL COMMENT '单价',
                    billing_unit ENUM('per_10k_chars', 'per_voice', 'per_video', 'per_million_tokens') NOT NULL DEFAULT 'per_10k_chars' COMMENT '计费单位',
                    description TEXT DEFAULT NULL COMMENT '价格描述',
                    is_active BOOLEAN DEFAULT TRUE COMMENT '是否启用',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_task_model (task_type, model_name)
                )
            ''')

            # 创建用户账单汇总表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_billing_summary (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    total_calls INT NOT NULL DEFAULT 0 COMMENT '总调用次数',
                    total_chars INT NOT NULL DEFAULT 0 COMMENT '总字符数',
                    total_amount DECIMAL(12,4) NOT NULL DEFAULT 0.0000 COMMENT '总消费金额（元）',
                    last_call_at TIMESTAMP NULL COMMENT '最后调用时间',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    UNIQUE KEY unique_user_id (user_id)
                )
            ''')

            # 创建音色计费状态跟踪表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS voice_billing_status (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    voice_id VARCHAR(255) NOT NULL COMMENT '音色ID',
                    task_type ENUM('voice_design', 'voice_clone') NOT NULL COMMENT '音色类型',
                    voice_fee DECIMAL(10,4) NOT NULL DEFAULT 9.9000 COMMENT '音色费用',
                    is_charged BOOLEAN DEFAULT FALSE COMMENT '是否已收费',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '音色生成时间',
                    first_used_at TIMESTAMP NULL COMMENT '首次使用时间',
                    charged_at TIMESTAMP NULL COMMENT '收费时间',
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    UNIQUE KEY unique_user_voice (user_id, voice_id),
                    INDEX idx_user_voice (user_id, voice_id),
                    INDEX idx_is_charged (is_charged)
                )
            ''')

        finally:
            cursor.close()

    def ensure_keys_exist(self, connection=None):
        """确保RSA密钥存在"""
        if connection is None:
            with self.get_connection() as conn:
                return self.ensure_keys_exist(conn)

        cursor = connection.cursor()
        cursor.execute('SELECT * FROM secure_key')
        if cursor.fetchone() is None:
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            public_key = private_key.public_key()
            private_key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
            public_key_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            cursor.execute('INSERT INTO secure_key (private_key, public_key) VALUES (%s, %s)',
                         (private_key_pem.decode('utf-8'), public_key_pem.decode('utf-8')))
            connection.commit()
        cursor.close()

    def init_pricing_config(self, connection=None):
        """初始化定价配置"""
        if connection is None:
            with self.get_connection() as conn:
                return self.init_pricing_config(conn)

        cursor = connection.cursor()

        # 检查是否已有定价数据
        cursor.execute('SELECT COUNT(*) FROM pricing_config')
        count = cursor.fetchone()[0]

        if count == 0:
            # 插入定价配置
            pricing_data = [
                # 同步TTS - 高清模型 3.5元/万字符
                ('sync_tts', 'speech-2.5-hd-preview', 3.5000, 'per_10k_chars', '同步语音合成-高清模型'),
                ('sync_tts', 'speech-02-hd', 3.5000, 'per_10k_chars', '同步语音合成-高清模型'),
                ('sync_tts', 'speech-01-hd', 3.5000, 'per_10k_chars', '同步语音合成-高清模型'),

                # 同步TTS - 快速模型 2元/万字符
                ('sync_tts', 'speech-2.5-turbo-preview', 2.0000, 'per_10k_chars', '同步语音合成-快速模型'),
                ('sync_tts', 'speech-02-turbo', 2.0000, 'per_10k_chars', '同步语音合成-快速模型'),
                ('sync_tts', 'speech-01-turbo', 2.0000, 'per_10k_chars', '同步语音合成-快速模型'),

                # 异步TTS - 高清模型 3.5元/万字符
                ('async_tts', 'speech-2.5-hd-preview', 3.5000, 'per_10k_chars', '异步语音合成-高清模型'),
                ('async_tts', 'speech-02-hd', 3.5000, 'per_10k_chars', '异步语音合成-高清模型'),
                ('async_tts', 'speech-01-hd', 3.5000, 'per_10k_chars', '异步语音合成-高清模型'),

                # 异步TTS - 快速模型 2元/万字符
                ('async_tts', 'speech-2.5-turbo-preview', 2.0000, 'per_10k_chars', '异步语音合成-快速模型'),
                ('async_tts', 'speech-02-turbo', 2.0000, 'per_10k_chars', '异步语音合成-快速模型'),
                ('async_tts', 'speech-01-turbo', 2.0000, 'per_10k_chars', '异步语音合成-快速模型'),

                # 音色设计 - 所有模型 9.9元/音色
                ('voice_design', 'all_models', 9.9000, 'per_voice', '音色设计'),

                # 语音复刻 - 所有模型 9.9元/音色
                ('voice_clone', 'all_models', 9.9000, 'per_voice', '语音复刻'),

                # 音色设计试听 - 2元/万字符
                ('voice_design_preview', 'all_models', 2.0000, 'per_10k_chars', '音色设计试听'),

                # 视频生成 - 按分辨率、时长、模型分层定价
                # MiniMax-Hailuo-02 512P
                ('video_generation_512p_6s', 'MiniMax-Hailuo-02', 0.6000, 'per_video', '视频生成 512P 6s'),
                ('video_generation_512p_10s', 'MiniMax-Hailuo-02', 1.0000, 'per_video', '视频生成 512P 10s'),
                # MiniMax-Hailuo-02 768P
                ('video_generation_768p_6s', 'MiniMax-Hailuo-02', 2.0000, 'per_video', '视频生成 768P 6s'),
                ('video_generation_768p_10s', 'MiniMax-Hailuo-02', 4.0000, 'per_video', '视频生成 768P 10s'),
                # MiniMax-Hailuo-02 1080P
                ('video_generation_1080p_6s', 'MiniMax-Hailuo-02', 3.5000, 'per_video', '视频生成 1080P 6s'),
                # Director系列和其他模型
                ('video_generation_director', 'T2V-01-Director', 3.0000, 'per_video', '视频生成 Director模型'),
                ('video_generation_director', 'I2V-01-Director', 3.0000, 'per_video', '视频生成 Director模型'),
                ('video_generation_live', 'I2V-01-live', 3.0000, 'per_video', '视频生成 Live模型'),
                ('video_generation_standard', 'T2V-01', 3.0000, 'per_video', '视频生成 标准模型'),
                ('video_generation_standard', 'I2V-01', 3.0000, 'per_video', '视频生成 标准模型'),
                # 主体参考视频生成
                ('video_generation_subject', 'S2V-01', 4.5000, 'per_video', '视频生成 主体参考模型'),

                # 文本聊天 - 按tokens计费
                # MiniMax-M1 输入0-32k: 0.8元/百万tokens
                ('text_chat_input_0_32k', 'MiniMax-M1', 0.8000, 'per_million_tokens', 'MiniMax-M1输入0-32k tokens'),
                ('text_chat_output_0_32k', 'MiniMax-M1', 8.0000, 'per_million_tokens', 'MiniMax-M1输出0-32k tokens'),
                # MiniMax-M1 输入32-128k: 1.2元/百万tokens输入，16元/百万tokens输出
                ('text_chat_input_32_128k', 'MiniMax-M1', 1.2000, 'per_million_tokens', 'MiniMax-M1输入32-128k tokens'),
                ('text_chat_output_32_128k', 'MiniMax-M1', 16.0000, 'per_million_tokens', 'MiniMax-M1输出32-128k tokens'),
                # MiniMax-M1 输入128k+: 2.4元/百万tokens输入，24元/百万tokens输出
                ('text_chat_input_128k_plus', 'MiniMax-M1', 2.4000, 'per_million_tokens', 'MiniMax-M1输入128k+ tokens'),
                ('text_chat_output_128k_plus', 'MiniMax-M1', 24.0000, 'per_million_tokens', 'MiniMax-M1输出128k+ tokens'),
                # MiniMax-Text-01: 1元/百万tokens输入，8元/百万tokens输出
                ('text_chat_input', 'MiniMax-Text-01', 1.0000, 'per_million_tokens', 'MiniMax-Text-01输入tokens'),
                ('text_chat_output', 'MiniMax-Text-01', 8.0000, 'per_million_tokens', 'MiniMax-Text-01输出tokens'),

                # 文件操作 - 不收费
                ('file_upload', 'all_models', 0.0000, 'per_10k_chars', '文件上传'),
                ('file_download', 'all_models', 0.0000, 'per_10k_chars', '文件下载'),
                ('file_list', 'all_models', 0.0000, 'per_10k_chars', '文件列表'),
                ('file_delete', 'all_models', 0.0000, 'per_10k_chars', '文件删除'),
                ('file_retrieve', 'all_models', 0.0000, 'per_10k_chars', '文件检索'),
            ]

            cursor.executemany('''
                INSERT INTO pricing_config (task_type, model_name, unit_price, billing_unit, description)
                VALUES (%s, %s, %s, %s, %s)
            ''', pricing_data)
            connection.commit()
            print("Pricing configuration initialized.")

        cursor.close()

    def get_pricing(self, task_type, model_name='all_models'):
        """获取定价信息"""
        with self.get_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            try:
                # 首先尝试精确匹配
                cursor.execute('''
                    SELECT unit_price, billing_unit FROM pricing_config
                    WHERE task_type = %s AND model_name = %s AND is_active = TRUE
                ''', (task_type, model_name))
                result = cursor.fetchone()

                # 如果没有找到，尝试使用通用模型配置
                if not result:
                    cursor.execute('''
                        SELECT unit_price, billing_unit FROM pricing_config
                        WHERE task_type = %s AND model_name = 'all_models' AND is_active = TRUE
                    ''', (task_type,))
                    result = cursor.fetchone()

                return result
            finally:
                cursor.close()

    def calculate_cost(self, task_type, model_name, char_count=0, voice_count=0):
        """计算费用"""
        pricing = self.get_pricing(task_type, model_name)
        if not pricing:
            return Decimal('0.0000')

        unit_price = Decimal(str(pricing['unit_price']))
        billing_unit = pricing['billing_unit']

        if billing_unit == 'per_10k_chars':
            # 按万字符计费
            return unit_price * Decimal(str(char_count)) / Decimal('10000')
        elif billing_unit == 'per_voice':
            # 按音色数量计费
            return unit_price * Decimal(str(voice_count))
        else:
            return Decimal('0.0000')

    def record_api_call(self, user_id, task_type, endpoint, model_name=None, request_text=None,
                       request_params=None, voice_count=0):
        """记录API调用并计算费用"""
        char_count = count_length(request_text) if request_text else 0
        cost_amount = self.calculate_cost(task_type, model_name or 'all_models', char_count, voice_count)

        pricing = self.get_pricing(task_type, model_name or 'all_models')
        unit_price = Decimal(str(pricing['unit_price'])) if pricing else Decimal('0.0000')
        billing_unit = pricing['billing_unit'] if pricing else 'per_10k_chars'

        with self.get_connection() as connection:
            cursor = connection.cursor()
            try:
                # 插入API调用记录
                cursor.execute('''
                    INSERT INTO api_calls
                    (user_id, task_type, model_name, request_text, char_count, unit_price,
                     cost_amount, billing_unit, endpoint, request_params)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (user_id, task_type, model_name, request_text, char_count,
                      unit_price, cost_amount, billing_unit, endpoint, request_params))

                # 更新用户账单汇总
                cursor.execute('''
                    INSERT INTO user_billing_summary (user_id, total_calls, total_chars, total_amount, last_call_at)
                    VALUES (%s, 1, %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                    total_calls = total_calls + 1,
                    total_chars = total_chars + %s,
                    total_amount = total_amount + %s,
                    last_call_at = NOW()
                ''', (user_id, char_count, cost_amount, char_count, cost_amount))

                connection.commit()
                return cost_amount

            except mysql.connector.Error as err:
                print(f"Error recording API call: {err}")
                return Decimal('0.0000')
            finally:
                cursor.close()

    def get_user_billing_summary(self, user_id):
        """获取用户账单汇总"""
        with self.get_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute('''
                    SELECT total_calls, total_chars, total_amount, last_call_at
                    FROM user_billing_summary
                    WHERE user_id = %s
                ''', (user_id,))
                return cursor.fetchone()
            finally:
                cursor.close()

    def get_user_api_calls(self, user_id, limit=100, offset=0):
        """获取用户API调用历史"""
        with self.get_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute('''
                    SELECT task_type, model_name, request_text, char_count,
                           unit_price, cost_amount, billing_unit, endpoint, created_at
                    FROM api_calls
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                ''', (user_id, limit, offset))
                return cursor.fetchall()
            finally:
                cursor.close()

    def record_voice_generation(self, user_id, voice_id, task_type):
        """记录音色生成（不立即收费）"""
        with self.get_connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute('''
                    INSERT INTO voice_billing_status (user_id, voice_id, task_type, is_charged)
                    VALUES (%s, %s, %s, FALSE)
                    ON DUPLICATE KEY UPDATE
                    task_type = VALUES(task_type),
                    created_at = CURRENT_TIMESTAMP
                ''', (user_id, voice_id, task_type))
                connection.commit()
                return True
            except Exception as e:
                print(f"Error recording voice generation: {e}")
                return False
            finally:
                cursor.close()

    def check_and_charge_voice_fee(self, user_id, voice_id, endpoint):
        """检查并收取音色首次使用费用"""
        with self.get_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            try:
                # 检查音色是否已收费
                cursor.execute('''
                    SELECT id, task_type, voice_fee, is_charged
                    FROM voice_billing_status
                    WHERE user_id = %s AND voice_id = %s
                ''', (user_id, voice_id))
                voice_status = cursor.fetchone()

                if not voice_status:
                    # 如果没有记录，说明是系统预设音色，无需收费
                    return Decimal('0.0000')

                if voice_status['is_charged']:
                    # 已经收费过了，无需再次收费
                    return Decimal('0.0000')

                # 首次使用，需要收费
                voice_fee = Decimal(str(voice_status['voice_fee']))
                task_type = voice_status['task_type']

                # 记录音色费用
                cursor.execute('''
                    INSERT INTO api_calls
                    (user_id, task_type, model_name, request_text, char_count, unit_price,
                     cost_amount, billing_unit, endpoint, request_params)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (user_id, f'{task_type}_charge', 'all_models',
                      f'首次使用音色: {voice_id}', 0, voice_fee, voice_fee,
                      'per_voice', endpoint, None))

                # 更新音色计费状态
                cursor.execute('''
                    UPDATE voice_billing_status
                    SET is_charged = TRUE, first_used_at = NOW(), charged_at = NOW()
                    WHERE user_id = %s AND voice_id = %s
                ''', (user_id, voice_id))

                # 更新用户账单汇总
                cursor.execute('''
                    INSERT INTO user_billing_summary (user_id, total_calls, total_chars, total_amount, last_call_at)
                    VALUES (%s, 1, 0, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                    total_calls = total_calls + 1,
                    total_amount = total_amount + %s,
                    last_call_at = NOW()
                ''', (user_id, voice_fee, voice_fee))

                connection.commit()
                return voice_fee

            except Exception as e:
                print(f"Error checking/charging voice fee: {e}")
                return Decimal('0.0000')
            finally:
                cursor.close()

    def record_api_call_with_voice_check(self, user_id, task_type, endpoint, model_name=None,
                                       request_text=None, request_params=None, voice_id=None):
        """记录API调用并检查音色费用"""
        # 先计算基础费用
        char_count = count_length(request_text) if request_text else 0
        base_cost = self.calculate_cost(task_type, model_name or 'all_models', char_count, 0)

        # 检查音色费用
        voice_cost = Decimal('0.0000')
        if voice_id and task_type in ['sync_tts', 'async_tts']:
            voice_cost = self.check_and_charge_voice_fee(user_id, voice_id, endpoint)

        # 记录基础API调用
        total_cost = self.record_api_call(user_id, task_type, endpoint, model_name,
                                        request_text, request_params, 0)

        return total_cost + voice_cost

    def record_text_chat_call(self, user_id, model_name, request_text, response_text, endpoint, request_params=None):
        """记录文本聊天API调用，分别计算输入和输出费用"""
        try:
            # 估算输入和输出tokens
            input_tokens = estimate_tokens(request_text) if request_text else 0
            output_tokens = estimate_tokens(response_text) if response_text else 0

            # 计算费用
            input_cost, output_cost = self.calculate_text_chat_cost(model_name, input_tokens, output_tokens)
            total_cost = input_cost + output_cost

            # 获取定价信息用于记录
            if model_name == 'MiniMax-M1':
                # 根据输入长度确定定价层级
                if input_tokens <= 32000:
                    input_task_type = 'text_chat_input_0_32k'
                    output_task_type = 'text_chat_output_0_32k'
                elif input_tokens <= 128000:
                    input_task_type = 'text_chat_input_32_128k'
                    output_task_type = 'text_chat_output_32_128k'
                else:
                    input_task_type = 'text_chat_input_128k_plus'
                    output_task_type = 'text_chat_output_128k_plus'
            else:  # MiniMax-Text-01
                input_task_type = 'text_chat_input'
                output_task_type = 'text_chat_output'

            # 记录输入部分
            input_pricing = self.get_pricing_config(input_task_type, model_name)
            input_unit_price = input_pricing['unit_price'] if input_pricing else Decimal('0')

            # 记录输出部分
            output_pricing = self.get_pricing_config(output_task_type, model_name)
            output_unit_price = output_pricing['unit_price'] if output_pricing else Decimal('0')

            with self.get_connection() as connection:
                cursor = connection.cursor()

                # 记录输入费用
                cursor.execute('''
                    INSERT INTO api_calls (
                        user_id, task_type, model_name, request_text, char_count,
                        unit_price, cost_amount, billing_unit, endpoint, request_params
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    user_id, input_task_type, model_name, request_text, input_tokens,
                    input_unit_price, input_cost, 'per_million_tokens', endpoint, request_params
                ))

                # 记录输出费用
                cursor.execute('''
                    INSERT INTO api_calls (
                        user_id, task_type, model_name, request_text, char_count,
                        unit_price, cost_amount, billing_unit, endpoint, request_params
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    user_id, output_task_type, model_name, response_text or "输出内容", output_tokens,
                    output_unit_price, output_cost, 'per_million_tokens', endpoint, request_params
                ))

                # 更新用户账单汇总
                cursor.execute('''
                    INSERT INTO user_billing_summary (user_id, total_calls, total_chars, total_amount, last_call_at)
                    VALUES (%s, 2, %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                        total_calls = total_calls + 2,
                        total_chars = total_chars + %s,
                        total_amount = total_amount + %s,
                        last_call_at = NOW()
                ''', (user_id, input_tokens + output_tokens, total_cost, input_tokens + output_tokens, total_cost))

                connection.commit()
                cursor.close()

            return total_cost

        except Exception as e:
            print(f"记录文本聊天API调用时出错: {e}")
            return Decimal('0')

    def calculate_text_chat_cost(self, model_name, input_tokens, output_tokens):
        """计算文本聊天费用"""
        try:
            if model_name == 'MiniMax-M1':
                # 根据输入长度确定定价
                if input_tokens <= 32000:
                    input_price = Decimal('0.8')  # 0.8元/百万tokens
                    output_price = Decimal('8.0')  # 8元/百万tokens
                elif input_tokens <= 128000:
                    input_price = Decimal('1.2')  # 1.2元/百万tokens
                    output_price = Decimal('16.0')  # 16元/百万tokens
                else:
                    input_price = Decimal('2.4')  # 2.4元/百万tokens
                    output_price = Decimal('24.0')  # 24元/百万tokens
            elif model_name == 'MiniMax-Text-01':
                input_price = Decimal('1.0')  # 1元/百万tokens
                output_price = Decimal('8.0')  # 8元/百万tokens
            else:
                # 未知模型，使用默认价格
                input_price = Decimal('1.0')
                output_price = Decimal('8.0')

            # 计算费用 (tokens / 1,000,000 * price)
            input_cost = (Decimal(input_tokens) / Decimal('1000000')) * input_price
            output_cost = (Decimal(output_tokens) / Decimal('1000000')) * output_price

            return input_cost, output_cost

        except Exception as e:
            print(f"计算文本聊天费用时出错: {e}")
            return Decimal('0'), Decimal('0')

    def record_video_generation_call(self, user_id, model_name, request_text, endpoint, request_params=None):
        """记录视频生成API调用，根据模型和参数确定费用"""
        try:
            # 解析请求参数以确定视频规格
            task_type, cost = self.calculate_video_generation_cost(model_name, request_params)

            # 获取定价信息
            pricing = self.get_pricing(task_type, model_name)
            unit_price = pricing['unit_price'] if pricing else cost

            with self.get_connection() as connection:
                cursor = connection.cursor()

                # 记录API调用
                cursor.execute('''
                    INSERT INTO api_calls (
                        user_id, task_type, model_name, request_text, char_count,
                        unit_price, cost_amount, billing_unit, endpoint, request_params
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    user_id, task_type, model_name, request_text or "视频生成", 1,
                    unit_price, cost, 'per_video', endpoint, request_params
                ))

                # 更新用户账单汇总
                cursor.execute('''
                    INSERT INTO user_billing_summary (user_id, total_calls, total_chars, total_amount, last_call_at)
                    VALUES (%s, 1, 1, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                        total_calls = total_calls + 1,
                        total_chars = total_chars + 1,
                        total_amount = total_amount + %s,
                        last_call_at = NOW()
                ''', (user_id, cost, cost))

                connection.commit()
                cursor.close()

            return cost

        except Exception as e:
            print(f"记录视频生成API调用时出错: {e}")
            return Decimal('0')

    def calculate_video_generation_cost(self, model_name, request_params_str):
        """计算视频生成费用，根据模型和参数确定任务类型和价格"""
        try:
            # 解析请求参数
            if isinstance(request_params_str, str):
                import json
                request_params = json.loads(request_params_str)
            else:
                request_params = request_params_str or {}

            # 根据模型确定基础任务类型和费用
            if model_name == 'MiniMax-Hailuo-02':
                # 从请求参数中获取分辨率和时长信息
                # 这些参数可能在video_setting中
                video_setting = request_params.get('video_setting', {})

                # 尝试从不同可能的字段获取分辨率
                resolution = (video_setting.get('resolution') or
                            video_setting.get('video_resolution') or
                            request_params.get('resolution') or
                            request_params.get('video_resolution'))

                # 尝试获取时长
                duration = (video_setting.get('duration') or
                          video_setting.get('video_duration') or
                          request_params.get('duration') or
                          request_params.get('video_duration'))

                # 根据分辨率和时长确定价格
                if resolution and '1080' in str(resolution):
                    return 'video_generation_1080p_6s', Decimal('3.5')  # 目前只有6s的1080P
                elif resolution and '768' in str(resolution):
                    if duration and ('10' in str(duration) or 'long' in str(duration).lower()):
                        return 'video_generation_768p_10s', Decimal('4.0')
                    else:
                        return 'video_generation_768p_6s', Decimal('2.0')
                else:  # 默认512P
                    if duration and ('10' in str(duration) or 'long' in str(duration).lower()):
                        return 'video_generation_512p_10s', Decimal('1.0')
                    else:
                        return 'video_generation_512p_6s', Decimal('0.6')

            elif model_name in ['T2V-01-Director', 'I2V-01-Director']:
                return 'video_generation_director', Decimal('3.0')
            elif model_name == 'I2V-01-live':
                return 'video_generation_live', Decimal('3.0')
            elif model_name in ['T2V-01', 'I2V-01']:
                return 'video_generation_standard', Decimal('3.0')
            elif model_name == 'S2V-01':
                return 'video_generation_subject', Decimal('4.5')
            else:
                # 未知模型，使用默认价格
                return 'video_generation_standard', Decimal('3.0')

        except Exception as e:
            print(f"计算视频生成费用时出错: {e}")
            return 'video_generation_standard', Decimal('3.0')

    # 保持原有的用户管理方法
    def get_keys(self):
        with self.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute('SELECT * FROM secure_key')
            return cursor.fetchone()

    def add_user(self, user_id, username, password_hash, email):
        with self.get_connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute('INSERT INTO users (user_id, username, password_hash, email) VALUES (%s, %s, %s, %s)',
                             (user_id, username, password_hash, email))
                connection.commit()
            finally:
                cursor.close()

    def get_user(self, username):
        with self.get_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute('SELECT user_id, username, password_hash, email, created_at FROM users WHERE username = %s', (username,))
                return cursor.fetchone()
            finally:
                cursor.close()

    def add_bearer_token(self, token, user_id, expires_at):
        with self.get_connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute('INSERT INTO bearer_tokens (token, user_id, expires_at) VALUES (%s, %s, %s)',
                             (token, user_id, expires_at))
                connection.commit()
            finally:
                cursor.close()

    def get_all_users_with_billing(self):
        """获取所有用户信息及其计费汇总"""
        with self.get_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute('''
                    SELECT
                        u.user_id,
                        u.username,
                        u.email,
                        u.created_at as user_created_at,
                        u.is_active,
                        COALESCE(ubs.total_calls, 0) as total_calls,
                        COALESCE(ubs.total_chars, 0) as total_chars,
                        COALESCE(ubs.total_amount, 0.0000) as total_amount,
                        ubs.last_call_at,
                        ubs.created_at as billing_created_at
                    FROM users u
                    LEFT JOIN user_billing_summary ubs ON u.user_id = ubs.user_id
                    ORDER BY u.created_at DESC
                ''')
                return cursor.fetchall()
            finally:
                cursor.close()

    def get_system_statistics(self):
        """获取系统统计信息"""
        with self.get_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            try:
                # 用户统计
                cursor.execute('SELECT COUNT(*) as total_users FROM users WHERE is_active = TRUE')
                user_stats = cursor.fetchone()

                # API调用统计
                cursor.execute('''
                    SELECT
                        COUNT(*) as total_api_calls,
                        SUM(char_count) as total_chars,
                        SUM(cost_amount) as total_revenue
                    FROM api_calls
                ''')
                api_stats = cursor.fetchone()

                # 按任务类型统计
                cursor.execute('''
                    SELECT
                        task_type,
                        COUNT(*) as call_count,
                        SUM(char_count) as total_chars,
                        SUM(cost_amount) as total_cost
                    FROM api_calls
                    GROUP BY task_type
                    ORDER BY total_cost DESC
                ''')
                task_stats = cursor.fetchall()

                # 音色统计
                cursor.execute('''
                    SELECT
                        task_type,
                        COUNT(*) as total_voices,
                        SUM(CASE WHEN is_charged THEN 1 ELSE 0 END) as charged_voices,
                        SUM(CASE WHEN is_charged THEN voice_fee ELSE 0 END) as voice_revenue
                    FROM voice_billing_status
                    GROUP BY task_type
                ''')
                voice_stats = cursor.fetchall()

                # 今日统计
                cursor.execute('''
                    SELECT
                        COUNT(*) as today_calls,
                        SUM(char_count) as today_chars,
                        SUM(cost_amount) as today_revenue
                    FROM api_calls
                    WHERE DATE(created_at) = CURDATE()
                ''')
                today_stats = cursor.fetchone()

                return {
                    'user_stats': user_stats,
                    'api_stats': api_stats,
                    'task_stats': task_stats,
                    'voice_stats': voice_stats,
                    'today_stats': today_stats
                }
            finally:
                cursor.close()

    def get_top_users_by_revenue(self, limit=10):
        """获取消费最高的用户"""
        with self.get_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute('''
                    SELECT
                        u.username,
                        u.email,
                        ubs.total_calls,
                        ubs.total_chars,
                        ubs.total_amount,
                        ubs.last_call_at
                    FROM user_billing_summary ubs
                    JOIN users u ON ubs.user_id = u.user_id
                    WHERE u.is_active = TRUE
                    ORDER BY ubs.total_amount DESC
                    LIMIT %s
                ''', (limit,))
                return cursor.fetchall()
            finally:
                cursor.close()

if __name__ == '__main__':
    # 测试代码
    db = MinimaxDatabaseManager()
    print("Database initialized successfully!")