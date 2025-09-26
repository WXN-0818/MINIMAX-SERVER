import asyncio
import aiohttp
from aiohttp import web
import json
from datetime import datetime
import time
import os
import re
import hashlib
import base64
import uuid
from minimax_user_management import MinimaxUserManager
from minimax_database import MinimaxDatabaseManager, count_length
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 配置
PROXY_PORT = 8768
MINIMAX_API_KEY = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJHcm91cE5hbWUiOiJTbm93IEpvaG4iLCJVc2VyTmFtZSI6IlNub3cgSm9obiIsIkFjY291bnQiOiIiLCJTdWJqZWN0SUQiOiIxOTY2Mzc3NjMwMjE1MTg1MTEyIiwiUGhvbmUiOiIiLCJHcm91cElEIjoiMTk2NjM3NzYzMDIxMDk4NjcxMiIsIlBhZ2VOYW1lIjoiIiwiTWFpbCI6ImpvaG4wMDI1MDcwOEBnbWFpbC5jb20iLCJDcmVhdGVUaW1lIjoiMjAyNS0wOS0xNiAxMDo0NToxNiIsIlRva2VuVHlwZSI6MSwiaXNzIjoibWluaW1heCJ9.OhodgsM7URdE476H77dOH4i6RGE_HC78PXTh8Dh-wSOnUKf62go9pU-l5EQSWinHjTd77ZG4b9vqZ6BZGVGJzgrBoj9eJRMEdsBIO8pBT6TaVN9JVztKVjb9q-ET3MKsCsin6_cFNoBzdM4evYZ1FR6PNHNO_wZSjRNRq3R6tekwKSvqfMiGitsV5e8Qd3DfiquBAmH8iEJq6GR28WYezE4Z1YokeRHRE8xuaYXF4urcy1MVQc8aEgpZiK7TzDSQIAxCPKNzLxkZtIpt0QDdxkyPPqyC_UM7bAipewK6k-s135_EYibZXtadJPDIBGPUT79ScaxwCR141W4yB7C32A"
MINIMAX_BASE_URL = "https://api.minimax.io"  # MiniMax API基础URL
MINIMAX_HTTP_URL = "https://api.minimax.io/v1/t2a_v2"
MINIMAX_ASYNC_URL = "https://api.minimax.io/v1/t2a_async_v2"

# 音频保存配置
AUDIO_SAVE_BASE_DIR = "/mnt/wxn/Change-API/minimax/audio_archive"   # 音频保存根目录
ENABLE_AUDIO_SAVE = True  # 是否启用音频保存功能
MINIMAX_QUERY_URL = "https://api.minimax.io/v1/query/t2a_async_query_v2"
MAX_TEXT_LENGTH = 10000

# 数据库和用户管理实例
db_manager = MinimaxDatabaseManager(host='0.0.0.0', user='root', password='Cloudsway00@12Mk3', database='minimax')
user_manager = MinimaxUserManager(db_manager)

class MiniMaxHTTPProxy:
    def __init__(self):
        self.session = None

    def safe_filename(self, text, max_length=50):
        """将文本转换为安全的文件名"""
        # 移除或替换不安全的字符
        safe_text = re.sub(r'[<>:"/\\|?*]', '_', text)
        # 移除连续的空格和换行符
        safe_text = re.sub(r'\s+', '_', safe_text.strip())
        # 限制长度
        if len(safe_text) > max_length:
            safe_text = safe_text[:max_length]
        # 如果为空或只有下划线，使用哈希值
        if not safe_text or safe_text.replace('_', '') == '':
            safe_text = hashlib.md5(text.encode('utf-8')).hexdigest()[:10]
        return safe_text

    def create_audio_path(self, username, text, audio_format='mp3'):
        """创建音频文件保存路径"""
        if not ENABLE_AUDIO_SAVE:
            return None, None

        try:
            # 创建目录结构：用户名/日期/
            today = datetime.now().strftime('%Y-%m-%d')
            user_dir = os.path.join(AUDIO_SAVE_BASE_DIR, username, today)
            os.makedirs(user_dir, exist_ok=True)

            # 创建文件名：时间戳_UUID.mp3
            timestamp = datetime.now().strftime('%H%M%S')
            unique_id = str(uuid.uuid4())[:8]  # 取前8位UUID
            filename = f"{timestamp}_{unique_id}.{audio_format}"
            filepath = os.path.join(user_dir, filename)

            # 创建说明文件，记录音频对应的文本内容
            info_filename = f"{timestamp}_{unique_id}.txt"
            info_filepath = os.path.join(user_dir, info_filename)

            with open(info_filepath, 'w', encoding='utf-8') as f:
                f.write(f"音频文件: {filename}\n")
                f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"用户: {username}\n")
                f.write(f"文本内容: {text}\n")

            return filepath, info_filepath
        except Exception as e:
            logger.error(f"创建音频保存路径时出错: {e}")
            return None, None

    async def save_audio_file(self, filepath, audio_data):
        """保存音频文件"""
        if not filepath or not ENABLE_AUDIO_SAVE:
            return False

        try:
            # 根据数据类型进行解码
            if isinstance(audio_data, str):
                # MiniMax API返回的是十六进制编码，不是base64
                try:
                    audio_binary = bytes.fromhex(audio_data)
                    logger.info("使用十六进制解码音频数据")
                except ValueError:
                    # 如果十六进制解码失败，尝试base64
                    try:
                        audio_binary = base64.b64decode(audio_data)
                        logger.info("使用base64解码音频数据")
                    except Exception:
                        logger.error("音频数据解码失败")
                        return False
            else:
                audio_binary = audio_data

            with open(filepath, 'wb') as f:
                f.write(audio_binary)

            logger.info(f"音频文件已保存: {filepath} ({len(audio_binary)} bytes)")
            return True
        except Exception as e:
            logger.error(f"保存音频文件时出错: {e}")
            return False

    def record_api_call_safe(self, user_id, task_type, endpoint, model_name=None,
                           request_text=None, request_params=None, voice_count=0, voice_id=None):
        """安全记录API调用的辅助方法"""
        try:
            if voice_id and task_type in ['sync_tts', 'async_tts']:
                # TTS调用时检查音色费用
                cost = db_manager.record_api_call_with_voice_check(
                    user_id=user_id,
                    task_type=task_type,
                    endpoint=endpoint,
                    model_name=model_name or 'all_models',
                    request_text=request_text,
                    request_params=request_params,
                    voice_id=voice_id
                )
            else:
                # 普通API调用
                cost = db_manager.record_api_call(
                    user_id=user_id,
                    task_type=task_type,
                    endpoint=endpoint,
                    model_name=model_name or 'all_models',
                    request_text=request_text,
                    request_params=request_params,
                    voice_count=voice_count
                )
            return cost
        except Exception as e:
            logger.error(f"记录API调用失败: {e}")
            return 0

    def extract_voice_id_from_request(self, request_body):
        """从请求中提取voice_id"""
        voice_id = request_body.get('voice_id')
        if not voice_id:
            # 尝试从其他字段提取
            voice_reference = request_body.get('voice_reference')
            if voice_reference and isinstance(voice_reference, dict):
                voice_id = voice_reference.get('voice_id')
        return voice_id

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def verify_bearer_token(self, authorization_header):
        """验证Bearer Token"""
        if not authorization_header or not authorization_header.startswith('Bearer '):
            return None, {"status": 401, "message": "缺少Bearer Token"}

        token = authorization_header[7:]  # 移除 'Bearer ' 前缀

        token_result = user_manager.verify_bearer_token(token)
        if token_result["status"] != 200:
            return None, token_result

        user_id = token_result["payload"]["sub"]
        return user_id, token_result

    async def handle_non_stream_request(self, request):
        """处理非流式请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取请求体
            request_body = await request.json()

            # 3. 验证和计费检查
            text = request_body.get("text", "")
            text_length = count_length(text)

            if text_length > MAX_TEXT_LENGTH:
                return web.json_response(
                    {"error": f"文本过长，最大支持{MAX_TEXT_LENGTH}个字符"},
                    status=400
                )

            # 4. 构造发送给minimax的请求
            headers = {
                'Authorization': f'Bearer {MINIMAX_API_KEY}',
                'Content-Type': 'application/json'
            }

            # 5. 发送请求到minimax
            async with self.session.post(
                MINIMAX_HTTP_URL,
                json=request_body,
                headers=headers
            ) as response:
                # 获取用户信息用于文件保存
                username = None
                try:
                    user_info = user_manager.get_user_by_id(user_id)
                    username = user_info['username'] if user_info else user_id
                except:
                    username = user_id

                if response.headers.get('content-type', '').startswith('audio/'):
                    # 如果返回的是音频数据
                    audio_data = await response.read()

                    # 保存音频文件
                    audio_format = request_body.get('audio_setting', {}).get('format', 'mp3')
                    audio_path, info_path = self.create_audio_path(username, text, audio_format)
                    if audio_path:
                        await self.save_audio_file(audio_path, audio_data)

                    # 记录API调用
                    try:
                        model_name = request_body.get('model', 'unknown')
                        voice_id = self.extract_voice_id_from_request(request_body)
                        cost = self.record_api_call_safe(
                            user_id=user_id,
                            task_type='sync_tts',
                            endpoint='/v1/t2a_v2',
                            model_name=model_name,
                            request_text=text,
                            request_params=json.dumps(request_body),
                            voice_id=voice_id
                        )
                        if voice_id:
                            logger.info(f"用户 {username} 同步TTS使用了 {text_length} 字符，模型: {model_name}，音色: {voice_id}，费用: {cost}元，音频已保存")
                        else:
                            logger.info(f"用户 {username} 同步TTS使用了 {text_length} 字符，模型: {model_name}，费用: {cost}元，音频已保存")
                    except Exception as e:
                        logger.error(f"记录API调用失败: {e}")

                    # 返回音频数据给客户端
                    return web.Response(body=audio_data, content_type=response.headers.get('content-type', 'audio/mpeg'))
                else:
                    # 如果返回的是JSON数据
                    response_data = await response.json()

                    # 检查JSON中是否包含音频数据
                    if 'data' in response_data and 'audio' in response_data['data']:
                        # 如果JSON中包含base64编码的音频数据
                        audio_base64 = response_data['data']['audio']
                        audio_format = request_body.get('audio_setting', {}).get('format', 'mp3')
                        audio_path, info_path = self.create_audio_path(username, text, audio_format)
                        if audio_path:
                            await self.save_audio_file(audio_path, audio_base64)

                    # 6. 记录API调用
                    try:
                        model_name = request_body.get('model', 'unknown')
                        voice_id = self.extract_voice_id_from_request(request_body)
                        cost = self.record_api_call_safe(
                            user_id=user_id,
                            task_type='sync_tts',
                            endpoint='/v1/t2a_v2',
                            model_name=model_name,
                            request_text=text,
                            request_params=json.dumps(request_body),
                            voice_id=voice_id
                        )
                        if voice_id:
                            logger.info(f"用户 {username} 同步TTS使用了 {text_length} 字符，模型: {model_name}，音色: {voice_id}，费用: {cost}元，音频已保存")
                        else:
                            logger.info(f"用户 {username} 同步TTS使用了 {text_length} 字符，模型: {model_name}，费用: {cost}元，音频已保存")
                    except Exception as e:
                        logger.error(f"记录API调用失败: {e}")

                    # 7. 返回响应给客户端
                    return web.json_response(response_data, status=response.status)

        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"处理非流式请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_stream_request(self, request):
        """处理流式请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取请求体
            request_body = await request.json()

            # 3. 验证和计费检查
            text = request_body.get("text", "")
            text_length = count_length(text)

            if text_length > MAX_TEXT_LENGTH:
                return web.json_response(
                    {"error": f"文本过长，最大支持{MAX_TEXT_LENGTH}个字符"},
                    status=400
                )

            # 4. 构造发送给minimax的请求
            headers = {
                'Authorization': f'Bearer {MINIMAX_API_KEY}',
                'Content-Type': 'application/json'
            }

            # 5. 创建流式响应
            response = web.StreamResponse()
            response.headers['Content-Type'] = 'text/plain; charset=utf-8'
            response.headers['Cache-Control'] = 'no-cache'
            response.headers['Connection'] = 'keep-alive'
            await response.prepare(request)

            try:
                # 6. 发送流式请求到minimax
                async with self.session.post(
                    MINIMAX_HTTP_URL,
                    json=request_body,
                    headers=headers
                ) as minimax_response:

                    # 7. 流式转发响应
                    async for chunk in minimax_response.content.iter_chunked(1024):
                        if chunk:
                            await response.write(chunk)

                    # 8. 记录API调用
                    try:
                        model_name = request_body.get('model', 'unknown')
                        cost = db_manager.record_api_call(
                            user_id=user_id,
                            task_type='sync_tts',
                            endpoint='/v1/t2a_v2',
                            model_name=model_name,
                            request_text=text,
                            request_params=json.dumps(request_body)
                        )
                        logger.info(f"用户 {user_id} 流式TTS使用了 {text_length} 字符，模型: {model_name}，费用: {cost}元")
                    except Exception as e:
                        logger.error(f"记录API调用失败: {e}")

                await response.write_eof()
                return response

            except Exception as e:
                logger.error(f"流式请求处理错误: {e}")
                await response.write(b'data: {"error": "Stream processing error"}\n\n')
                await response.write_eof()
                return response

        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"处理流式请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_tts_request(self, request):
        """处理TTS请求 - 根据stream参数决定处理方式"""
        try:
            # 获取请求体来检查stream参数
            request_body = await request.json()
            is_stream = request_body.get("stream", False)

            if is_stream:
                return await self.handle_stream_request(request)
            else:
                return await self.handle_non_stream_request(request)

        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"处理TTS请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)


    async def handle_async_tts_request(self, request):
        """处理异步TTS请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取请求体
            request_body = await request.json()

            # 3. 验证和计费检查
            text = ""
            text_length = 0

            # 支持文本和文件两种输入方式
            if "text" in request_body:
                # 文本输入方式
                text = request_body.get("text", "")
                text_length = count_length(text)

                # 文本长度检查
                if text_length > MAX_TEXT_LENGTH:
                    return web.json_response(
                        {"error": f"文本过长，最大支持{MAX_TEXT_LENGTH}个字符"},
                        status=400
                    )
            elif "text_file_id" in request_body:
                # 文件输入方式 - 稍后从返回结果中获取实际使用字符数
                file_id = request_body.get('text_file_id')
                text = f"[文件输入: file_id={file_id}]"
                text_length = 0  # 暂时设为0，稍后从API返回结果中获取
                logger.info(f"用户 {user_id} 使用文件输入，file_id: {file_id}")
            else:
                return web.json_response(
                    {"error": "缺少text或text_file_id参数"},
                    status=400
                )

            # 4. 构造发送给minimax的请求
            headers = {
                'Authorization': f'Bearer {MINIMAX_API_KEY}',
                'Content-Type': 'application/json'
            }

            # 5. 发送请求到minimax异步API
            async with self.session.post(
                MINIMAX_ASYNC_URL,
                json=request_body,
                headers=headers
            ) as response:
                response_data = await response.json()

                # 6. 记录API调用
                try:
                    # 如果是文件输入，从返回结果中获取实际使用字符数
                    if "text_file_id" in request_body and 'usage_characters' in response_data:
                        actual_text_length = response_data['usage_characters']
                        logger.info(f"从API返回结果获取实际字符数: {actual_text_length}")
                        # 构造包含实际字符数的文本用于计费
                        billing_text = "x" * actual_text_length  # 生成对应长度的字符串用于计费
                    else:
                        actual_text_length = text_length
                        billing_text = text

                    model_name = request_body.get('model', 'unknown')
                    cost = db_manager.record_api_call(
                        user_id=user_id,
                        task_type='async_tts',
                        endpoint='/v1/t2a_async_v2',
                        model_name=model_name,
                        request_text=billing_text,
                        request_params=json.dumps(request_body)
                    )
                    logger.info(f"用户 {user_id} 异步TTS使用了 {actual_text_length} 字符，模型: {model_name}，费用: {cost}元")
                except Exception as e:
                    logger.error(f"记录API调用失败: {e}")

                # 7. 返回响应给客户端
                return web.json_response(response_data, status=response.status)

        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"处理异步TTS请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_async_query_request(self, request):
        """处理异步任务查询请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取task_id参数
            task_id = request.query.get('task_id')
            if not task_id:
                return web.json_response(
                    {"error": "缺少task_id参数"},
                    status=400
                )

            # 3. 构造发送给minimax的请求
            headers = {
                'Authorization': f'Bearer {MINIMAX_API_KEY}',
                'Content-Type': 'application/json'
            }

            # 4. 发送查询请求到minimax
            query_url = f"{MINIMAX_QUERY_URL}?task_id={task_id}"
            async with self.session.get(
                query_url,
                headers=headers
            ) as response:
                response_data = await response.json()

                # 5. 记录查询操作
                try:
                    db_manager.record_api_call(
                        user_id=user_id,
                        task_type='async_tts_query',
                        endpoint='/v1/query/t2a_async_query_v2',
                        model_name='query',
                        request_text=f"task_id: {task_id}",
                        request_params=json.dumps({"task_id": task_id})
                    )
                    logger.info(f"用户 {user_id} 查询TTS任务状态，task_id: {task_id}")
                except Exception as e:
                    logger.error(f"记录查询操作失败: {e}")

                # 6. 返回响应给客户端
                return web.json_response(response_data, status=response.status)

        except Exception as e:
            logger.error(f"处理异步查询请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_file_upload_request(self, request):
        """处理文件上传请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 处理multipart表单数据
            reader = await request.multipart()

            files = {}
            data = {}

            async for field in reader:
                if field.name == 'file':
                    # 处理文件字段
                    filename = field.filename or 'uploaded_file'
                    content = await field.read()
                    content_type = getattr(field, 'content_type', None) or 'application/octet-stream'
                    files['file'] = (filename, content, content_type)
                else:
                    # 处理其他表单字段
                    data[field.name] = await field.text()

            if not files:
                return web.json_response(
                    {"error": "缺少文件字段"},
                    status=400
                )

            # 3. 构造发送给minimax的请求
            headers = {
                'Authorization': f'Bearer {MINIMAX_API_KEY}'
            }

            # 4. 发送文件上传请求到minimax
            form_data = aiohttp.FormData()
            for key, value in data.items():
                form_data.add_field(key, value)

            for field_name, (filename, content, content_type) in files.items():
                form_data.add_field(field_name, content, filename=filename, content_type=content_type)

            async with self.session.post(
                "https://api.minimax.io/v1/files/upload",
                data=form_data,
                headers=headers
            ) as response:
                response_data = await response.json()

                # 5. 记录文件上传操作
                try:
                    purpose = data.get('purpose', 'unknown')
                    filename = files['file'][0]
                    cost = self.record_api_call_safe(
                        user_id=user_id,
                        task_type='file_upload',
                        endpoint='/v1/files/upload',
                        model_name='file_system',
                        request_text=f"文件上传: purpose={purpose}, filename={filename}",
                        request_params=json.dumps(data)
                    )
                    logger.info(f"用户 {user_id} 上传文件，purpose: {purpose}，费用: {cost}元")
                except Exception as e:
                    logger.error(f"记录文件上传失败: {e}")

                # 6. 返回响应给客户端
                return web.json_response(response_data, status=response.status)

        except Exception as e:
            logger.error(f"处理文件上传请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_file_list_request(self, request):
        """处理文件列表请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 构造发送给minimax的请求
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {MINIMAX_API_KEY}'
            }

            # 3. 发送文件列表请求到minimax
            async with self.session.get(
                "https://api.minimax.io/v1/files/list",
                headers=headers
            ) as response:
                response_data = await response.json()

                # 4. 记录文件列表操作
                try:
                    db_manager.record_api_call(user_id, "[文件列表查询]")
                    logger.info(f"用户 {user_id} 查询文件列表")
                except Exception as e:
                    logger.error(f"记录文件列表查询失败: {e}")

                # 5. 返回响应给客户端
                return web.json_response(response_data, status=response.status)

        except Exception as e:
            logger.error(f"处理文件列表请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_file_retrieve_request(self, request):
        """处理文件检索请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取file_id参数
            file_id = request.query.get('file_id')
            if not file_id:
                return web.json_response(
                    {"error": "缺少file_id参数"},
                    status=400
                )

            # 3. 构造发送给minimax的请求
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {MINIMAX_API_KEY}'
            }

            # 4. 发送文件检索请求到minimax
            retrieve_url = f"https://api.minimax.io/v1/files/retrieve?file_id={file_id}"
            async with self.session.get(
                retrieve_url,
                headers=headers
            ) as response:
                response_data = await response.json()

                # 5. 记录文件检索操作
                try:
                    db_manager.record_api_call(user_id, f"[文件检索: file_id={file_id}]")
                    logger.info(f"用户 {user_id} 检索文件，file_id: {file_id}")
                except Exception as e:
                    logger.error(f"记录文件检索失败: {e}")

                # 6. 返回响应给客户端
                return web.json_response(response_data, status=response.status)

        except Exception as e:
            logger.error(f"处理文件检索请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_file_download_request(self, request):
        """处理文件下载请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取file_id参数
            file_id = request.query.get('file_id')
            if not file_id:
                return web.json_response(
                    {"error": "缺少file_id参数"},
                    status=400
                )

            # 3. 构造发送给minimax的请求
            headers = {
                'content-type': 'application/json',
                'Authorization': f'Bearer {MINIMAX_API_KEY}'
            }

            # 4. 发送文件下载请求到minimax
            download_url = f"https://api.minimax.io/v1/files/retrieve_content?file_id={file_id}"
            async with self.session.get(
                download_url,
                headers=headers
            ) as response:

                # 5. 记录文件下载操作
                try:
                    db_manager.record_api_call(user_id, f"[文件下载: file_id={file_id}]")
                    logger.info(f"用户 {user_id} 下载文件，file_id: {file_id}")
                except Exception as e:
                    logger.error(f"记录文件下载失败: {e}")

                # 6. 判断响应类型并处理
                content_type = response.headers.get('content-type', '')

                if 'application/json' in content_type:
                    # JSON响应（可能是错误信息）
                    response_data = await response.json()
                    return web.json_response(response_data, status=response.status)
                else:
                    # 文件内容响应，直接转发二进制数据
                    file_content = await response.read()

                    # 创建文件下载响应
                    file_response = web.Response(
                        body=file_content,
                        status=response.status,
                        headers={
                            'Content-Type': response.headers.get('content-type', 'application/octet-stream'),
                            'Content-Disposition': response.headers.get('content-disposition', f'attachment; filename="file_{file_id}"')
                        }
                    )
                    return file_response

        except Exception as e:
            logger.error(f"处理文件下载请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_file_delete_request(self, request):
        """处理文件删除请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取请求体
            request_body = await request.json()

            file_id = request_body.get('file_id')
            if not file_id:
                return web.json_response(
                    {"error": "缺少file_id参数"},
                    status=400
                )

            # 3. 构造发送给minimax的请求
            headers = {
                'Authorization': f'Bearer {MINIMAX_API_KEY}',
                'Content-Type': 'application/json'
            }

            # 4. 发送文件删除请求到minimax
            async with self.session.post(
                "https://api.minimax.io/v1/files/delete",
                json=request_body,
                headers=headers
            ) as response:
                response_data = await response.json()

                # 5. 记录文件删除操作
                try:
                    purpose = request_body.get('purpose', 'unknown')
                    db_manager.record_api_call(user_id, f"[文件删除: file_id={file_id}, purpose={purpose}]")
                    logger.info(f"用户 {user_id} 删除文件，file_id: {file_id}, purpose: {purpose}")
                except Exception as e:
                    logger.error(f"记录文件删除失败: {e}")

                # 6. 返回响应给客户端
                return web.json_response(response_data, status=response.status)

        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"处理文件删除请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_voice_clone_upload_request(self, request):
        """处理语音复刻音频上传请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取GroupId参数
            group_id = request.query.get('GroupId')
            if not group_id:
                return web.json_response(
                    {"error": "缺少GroupId参数"},
                    status=400
                )

            # 3. 处理multipart表单数据
            reader = await request.multipart()

            files = {}
            data = {'purpose': 'voice_clone'}  # 固定purpose为voice_clone

            async for field in reader:
                if field.name == 'file':
                    # 处理文件字段
                    filename = field.filename or 'voice_clone_audio'
                    content = await field.read()
                    content_type = getattr(field, 'content_type', None) or 'audio/mpeg'
                    files['file'] = (filename, content, content_type)
                else:
                    # 处理其他表单字段
                    data[field.name] = await field.text()

            if not files:
                return web.json_response(
                    {"error": "缺少文件字段"},
                    status=400
                )

            # 4. 构造发送给minimax的请求
            headers = {
                'authority': 'api.minimax.io',
                'Authorization': f'Bearer {MINIMAX_API_KEY}'
            }

            # 5. 发送语音复刻音频上传请求到minimax
            form_data = aiohttp.FormData()
            for key, value in data.items():
                form_data.add_field(key, value)

            for field_name, (filename, content, content_type) in files.items():
                form_data.add_field(field_name, content, filename=filename, content_type=content_type)

            upload_url = f"https://api.minimax.io/v1/files/upload?GroupId={group_id}"
            async with self.session.post(
                upload_url,
                data=form_data,
                headers=headers
            ) as response:
                response_data = await response.json()

                # 6. 记录语音复刻音频上传操作
                try:
                    db_manager.record_api_call(user_id, f"[语音复刻音频上传: filename={files['file'][0]}, GroupId={group_id}]")
                    logger.info(f"用户 {user_id} 上传语音复刻音频，GroupId: {group_id}")
                except Exception as e:
                    logger.error(f"记录语音复刻音频上传失败: {e}")

                # 7. 返回响应给客户端
                return web.json_response(response_data, status=response.status)

        except Exception as e:
            logger.error(f"处理语音复刻音频上传请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_prompt_audio_upload_request(self, request):
        """处理示例音频上传请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取GroupId参数
            group_id = request.query.get('GroupId')
            if not group_id:
                return web.json_response(
                    {"error": "缺少GroupId参数"},
                    status=400
                )

            # 3. 处理multipart表单数据
            reader = await request.multipart()

            files = {}
            data = {'purpose': 'prompt_audio'}  # 固定purpose为prompt_audio

            async for field in reader:
                if field.name == 'file':
                    # 处理文件字段
                    filename = field.filename or 'prompt_audio'
                    content = await field.read()
                    content_type = getattr(field, 'content_type', None) or 'audio/mpeg'
                    files['file'] = (filename, content, content_type)
                else:
                    # 处理其他表单字段
                    data[field.name] = await field.text()

            if not files:
                return web.json_response(
                    {"error": "缺少文件字段"},
                    status=400
                )

            # 4. 构造发送给minimax的请求
            headers = {
                'authority': 'api.minimax.io',
                'Authorization': f'Bearer {MINIMAX_API_KEY}'
            }

            # 5. 发送示例音频上传请求到minimax
            form_data = aiohttp.FormData()
            for key, value in data.items():
                form_data.add_field(key, value)

            for field_name, (filename, content, content_type) in files.items():
                form_data.add_field(field_name, content, filename=filename, content_type=content_type)

            upload_url = f"https://api.minimax.io/v1/files/upload?GroupId={group_id}"
            async with self.session.post(
                upload_url,
                data=form_data,
                headers=headers
            ) as response:
                response_data = await response.json()

                # 6. 记录示例音频上传操作
                try:
                    db_manager.record_api_call(user_id, f"[示例音频上传: filename={files['file'][0]}, GroupId={group_id}]")
                    logger.info(f"用户 {user_id} 上传示例音频，GroupId: {group_id}")
                except Exception as e:
                    logger.error(f"记录示例音频上传失败: {e}")

                # 7. 返回响应给客户端
                return web.json_response(response_data, status=response.status)

        except Exception as e:
            logger.error(f"处理示例音频上传请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_voice_clone_request(self, request):
        """处理快速语音复刻请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取请求体
            request_body = await request.json()

            # 3. 验证必需参数
            required_fields = ['file_id', 'voice_id', 'clone_prompt', 'text']
            for field in required_fields:
                if field not in request_body:
                    return web.json_response(
                        {"error": f"缺少必需参数: {field}"},
                        status=400
                    )

            # 验证clone_prompt结构
            clone_prompt = request_body.get('clone_prompt', {})
            if 'prompt_audio' not in clone_prompt or 'prompt_text' not in clone_prompt:
                return web.json_response(
                    {"error": "clone_prompt必须包含prompt_audio和prompt_text字段"},
                    status=400
                )

            # 4. 验证和计费检查
            text = request_body.get("text", "")
            text_length = count_length(text)

            if text_length > MAX_TEXT_LENGTH:
                return web.json_response(
                    {"error": f"文本过长，最大支持{MAX_TEXT_LENGTH}个字符"},
                    status=400
                )

            # 5. 构造发送给minimax的请求
            headers = {
                'Authorization': f'Bearer {MINIMAX_API_KEY}',
                'content-type': 'application/json'
            }

            # 6. 发送语音复刻请求到minimax
            async with self.session.post(
                "https://api.minimax.io/v1/voice_clone",
                json=request_body,
                headers=headers
            ) as response:
                response_data = await response.json()

                # 7. 记录语音复刻操作
                try:
                    voice_id = request_body.get('voice_id', 'unknown')
                    file_id = request_body.get('file_id', 'unknown')
                    model_name = request_body.get('model', 'all_models')

                    # 记录音色生成（不收费）
                    db_manager.record_voice_generation(user_id, voice_id, 'voice_clone')

                    # TTS合成费用（包含首次使用音色的费用检查）
                    tts_cost = self.record_api_call_safe(
                        user_id=user_id,
                        task_type='sync_tts',
                        endpoint='/v1/voice_clone',
                        model_name=model_name,
                        request_text=text,
                        request_params=json.dumps(request_body),
                        voice_id=voice_id
                    )

                    logger.info(f"用户 {user_id} 语音复刻，voice_id: {voice_id}，TTS费用（含首次音色费用）: {tts_cost}元")
                except Exception as e:
                    logger.error(f"记录语音复刻失败: {e}")

                # 8. 返回响应给客户端
                return web.json_response(response_data, status=response.status)

        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"处理语音复刻请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_voice_design_request(self, request):
        """处理音色设计请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取请求体
            request_body = await request.json()

            # 3. 验证必需参数
            if 'prompt' not in request_body:
                return web.json_response(
                    {"error": "缺少必需参数: prompt"},
                    status=400
                )

            # 4. 验证和计费检查
            prompt = request_body.get("prompt", "")
            preview_text = request_body.get("preview_text", "")
            total_text_length = count_length(prompt + preview_text)

            if total_text_length > MAX_TEXT_LENGTH:
                return web.json_response(
                    {"error": f"文本过长，最大支持{MAX_TEXT_LENGTH}个字符"},
                    status=400
                )

            # 5. 构造发送给minimax的请求
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {MINIMAX_API_KEY}'
            }

            # 6. 发送音色设计请求到minimax
            async with self.session.post(
                "https://api.minimax.io/v1/voice_design",
                json=request_body,
                headers=headers
            ) as response:
                response_data = await response.json()

                # 7. 记录音色设计操作
                try:
                    # 从响应中获取voice_id（假设API返回包含voice_id）
                    voice_id = response_data.get('voice_id', f"voice_design_{int(time.time())}")

                    # 记录音色生成（不收费）
                    db_manager.record_voice_generation(user_id, voice_id, 'voice_design')

                    # 只记录试听费用（如果有preview_text）
                    preview_cost = 0
                    if preview_text:
                        preview_cost = self.record_api_call_safe(
                            user_id=user_id,
                            task_type='voice_design_preview',
                            endpoint='/v1/voice_design',
                            model_name='all_models',
                            request_text=preview_text,
                            request_params=json.dumps({"preview_text": preview_text})
                        )

                    logger.info(f"用户 {user_id} 音色设计，voice_id: {voice_id}，试听费用: {preview_cost}元（音色费用将在首次使用时收取）")
                except Exception as e:
                    logger.error(f"记录音色设计失败: {e}")

                # 8. 返回响应给客户端
                return web.json_response(response_data, status=response.status)

        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"处理音色设计请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_get_voices_request(self, request):
        """处理查询可用音色请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取请求体
            request_body = await request.json()

            # 3. 设置默认voice_type为'all'
            if 'voice_type' not in request_body:
                request_body['voice_type'] = 'all'

            # 4. 构造发送给minimax的请求
            headers = {
                'authority': 'api.minimax.io',
                'Authorization': f'Bearer {MINIMAX_API_KEY}',
                'content-type': 'application/json'
            }

            # 5. 发送查询音色请求到minimax
            async with self.session.post(
                "https://api.minimax.io/v1/get_voice",
                json=request_body,
                headers=headers
            ) as response:
                response_data = await response.json()

                # 6. 记录查询音色操作
                try:
                    voice_type = request_body.get('voice_type', 'all')
                    db_manager.record_api_call(user_id, f"[查询音色: voice_type={voice_type}]")
                    logger.info(f"用户 {user_id} 查询音色，voice_type: {voice_type}")
                except Exception as e:
                    logger.error(f"记录查询音色失败: {e}")

                # 7. 返回响应给客户端
                return web.json_response(response_data, status=response.status)

        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"处理查询音色请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_delete_voice_request(self, request):
        """处理删除音色请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取请求体
            request_body = await request.json()

            # 3. 验证必需参数
            required_fields = ['voice_type', 'voice_id']
            for field in required_fields:
                if field not in request_body:
                    return web.json_response(
                        {"error": f"缺少必需参数: {field}"},
                        status=400
                    )

            # 4. 构造发送给minimax的请求
            headers = {
                'content-type': 'application/json',
                'authorization': f'Bearer {MINIMAX_API_KEY}'
            }

            # 5. 发送删除音色请求到minimax
            async with self.session.post(
                "https://api.minimax.io/v1/delete_voice",
                json=request_body,
                headers=headers
            ) as response:
                response_data = await response.json()

                # 6. 记录删除音色操作
                try:
                    voice_type = request_body.get('voice_type', 'unknown')
                    voice_id = request_body.get('voice_id', 'unknown')
                    db_manager.record_api_call(user_id, f"[删除音色: voice_type={voice_type}, voice_id={voice_id}]")
                    logger.info(f"用户 {user_id} 删除音色，voice_type: {voice_type}, voice_id: {voice_id}")
                except Exception as e:
                    logger.error(f"记录删除音色失败: {e}")

                # 7. 返回响应给客户端
                return web.json_response(response_data, status=response.status)

        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"处理删除音色请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_video_generation_request(self, request):
        """处理视频生成请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取请求体
            request_body = await request.json()

            # 3. 验证必需参数
            if 'prompt' not in request_body:
                return web.json_response(
                    {"error": "缺少必需参数: prompt"},
                    status=400
                )

            # 4. 验证和计费检查
            prompt = request_body.get("prompt", "")
            prompt_length = count_length(prompt)

            if prompt_length > MAX_TEXT_LENGTH:
                return web.json_response(
                    {"error": f"提示词过长，最大支持{MAX_TEXT_LENGTH}个字符"},
                    status=400
                )

            # 5. 识别视频生成类型并记录相关信息
            video_type = "文生视频"
            additional_info = []

            # 检查是否有首帧图片
            if 'first_frame_image' in request_body:
                if 'last_frame_image' in request_body:
                    video_type = "首尾帧生成视频"
                    additional_info.append(f"首帧图片: {request_body['first_frame_image']}")
                    additional_info.append(f"尾帧图片: {request_body['last_frame_image']}")
                else:
                    video_type = "图生视频"
                    additional_info.append(f"首帧图片: {request_body['first_frame_image']}")

            # 检查是否有主体参考
            if 'subject_reference' in request_body:
                video_type = "主体参考视频生成"
                subject_ref = request_body['subject_reference']
                if isinstance(subject_ref, list) and len(subject_ref) > 0:
                    ref_type = subject_ref[0].get('type', 'unknown')
                    ref_images = subject_ref[0].get('image', [])
                    additional_info.append(f"参考类型: {ref_type}")
                    additional_info.append(f"参考图片数量: {len(ref_images)}")

            # 6. 构造发送给minimax的请求
            headers = {
                'Authorization': f'Bearer {MINIMAX_API_KEY}',
                'Content-Type': 'application/json'
            }

            # 7. 发送视频生成请求到minimax
            async with self.session.post(
                "https://api.minimax.io/v1/video_generation",
                json=request_body,
                headers=headers
            ) as response:
                response_data = await response.json()

                # 8. 记录视频生成操作和计费
                try:
                    model = request_body.get('model', 'unknown')

                    # 构建详细的请求描述
                    log_info = f"[{video_type}: prompt={prompt[:50]}...]"
                    if additional_info:
                        log_info += f", {', '.join(additional_info)}"

                    # 使用新的视频生成计费方法
                    cost = db_manager.record_video_generation_call(
                        user_id=user_id,
                        model_name=model,
                        request_text=log_info,
                        endpoint='/v1/video_generation',
                        request_params=json.dumps(request_body)
                    )

                    logger.info(f"用户 {user_id} 使用{video_type}，model: {model}, 费用: {cost}元")
                except Exception as e:
                    logger.error(f"记录视频生成失败: {e}")

                # 9. 返回响应给客户端
                return web.json_response(response_data, status=response.status)

        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"处理视频生成请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_video_query_request(self, request):
        """处理视频生成任务状态查询请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取task_id参数
            task_id = request.query.get('task_id')
            if not task_id:
                return web.json_response(
                    {"error": "缺少task_id参数"},
                    status=400
                )

            # 3. 构造发送给minimax的请求
            headers = {
                'Authorization': f'Bearer {MINIMAX_API_KEY}',
                'Content-Type': 'application/json'
            }

            # 4. 发送视频任务查询请求到minimax
            query_url = f"https://api.minimax.io/v1/query/video_generation?task_id={task_id}"
            async with self.session.get(
                query_url,
                headers=headers
            ) as response:
                response_data = await response.json()

                # 5. 记录视频任务查询操作
                try:
                    db_manager.record_api_call(user_id, f"[视频任务查询: task_id={task_id}]")
                    logger.info(f"用户 {user_id} 查询视频任务状态，task_id: {task_id}")
                except Exception as e:
                    logger.error(f"记录视频任务查询失败: {e}")

                # 6. 返回响应给客户端
                return web.json_response(response_data, status=response.status)

        except Exception as e:
            logger.error(f"处理视频任务查询请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_video_download_request(self, request):
        """处理视频文件下载请求（专门用于视频下载的文件检索接口）"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取file_id参数
            file_id = request.query.get('file_id')
            if not file_id:
                return web.json_response(
                    {"error": "缺少file_id参数"},
                    status=400
                )

            # 3. 构造发送给minimax的请求
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {MINIMAX_API_KEY}'
            }

            # 4. 发送视频文件检索请求到minimax
            retrieve_url = f"https://api.minimax.io/v1/files/retrieve?file_id={file_id}"
            async with self.session.get(
                retrieve_url,
                headers=headers
            ) as response:
                response_data = await response.json()

                # 5. 记录视频文件下载操作
                try:
                    db_manager.record_api_call(user_id, f"[视频文件下载: file_id={file_id}]")
                    logger.info(f"用户 {user_id} 下载视频文件，file_id: {file_id}")
                except Exception as e:
                    logger.error(f"记录视频文件下载失败: {e}")

                # 6. 返回响应给客户端
                return web.json_response(response_data, status=response.status)

        except Exception as e:
            logger.error(f"处理视频文件下载请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_billing_query_request(self, request):
        """处理用户计费查询请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)

            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 获取查询参数
            limit = min(int(request.query.get('limit', 50)), 1000)  # 最多1000条
            offset = int(request.query.get('offset', 0))

            # 3. 获取用户计费信息
            billing_summary = db_manager.get_user_billing_summary(user_id)
            api_calls = db_manager.get_user_api_calls(user_id, limit=limit, offset=offset)

            # 4. 记录查询操作
            self.record_api_call_safe(
                user_id=user_id,
                task_type='billing_query',
                endpoint='/v1/billing/query',
                model_name='query',
                request_text='计费查询',
                request_params=json.dumps({"limit": limit, "offset": offset})
            )

            # 5. 返回计费信息
            return web.json_response({
                "summary": billing_summary,
                "api_calls": api_calls,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "has_more": len(api_calls) == limit
                }
            })

        except Exception as e:
            logger.error(f"处理计费查询请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def handle_text_chat_request(self, request):
        """处理文本聊天完成请求"""
        try:
            # 1. 验证Bearer Token
            authorization = request.headers.get('Authorization')
            user_id, auth_result = self.verify_bearer_token(authorization)
            if not user_id:
                return web.json_response(
                    {"error": f"Authentication failed: {auth_result['message']}"},
                    status=auth_result["status"]
                )

            # 2. 解析请求数据
            data = await request.json()
            model = data.get('model', 'MiniMax-M1')
            messages = data.get('messages', [])
            stream = data.get('stream', False)

            # 3. 构建请求参数
            payload = {
                'model': model,
                'messages': messages
            }

            # 如果是流式请求，添加stream参数
            if stream:
                payload['stream'] = True

            # 4. 提取文本内容用于计费
            request_text_parts = []

            for message in messages:
                content = message.get('content', '')
                if isinstance(content, str):
                    # 纯文本消息
                    request_text_parts.append(content)
                elif isinstance(content, list):
                    # 多模态消息（文本+图像）
                    for item in content:
                        if item.get('type') == 'text':
                            text_content = item.get('text', '')
                            request_text_parts.append(text_content)

            request_text = '\n'.join(request_text_parts)

            # 5. 发送请求到MiniMax API
            headers = {
                'Authorization': f'Bearer {MINIMAX_API_KEY}',
                'Content-Type': 'application/json'
            }

            if stream:
                # 流式处理
                return await self._handle_stream_text_chat(payload, headers, user_id, model, request_text)
            else:
                # 非流式处理
                return await self._handle_non_stream_text_chat(payload, headers, user_id, model, request_text)

        except Exception as e:
            logger.error(f"处理文本聊天请求时出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def _handle_non_stream_text_chat(self, payload, headers, user_id, model, request_text):
        """处理非流式文本聊天"""
        try:
            async with self.session.post(
                f'{MINIMAX_BASE_URL}/v1/text/chatcompletion_v2',
                json=payload,
                headers=headers
            ) as response:
                if response.status == 200:
                    result = await response.json()

                    # 提取响应文本用于计费
                    response_text = ""
                    if 'choices' in result and len(result['choices']) > 0:
                        choice = result['choices'][0]
                        if 'message' in choice and 'content' in choice['message']:
                            response_text = choice['message']['content']

                    # 使用新的tokens计费方法
                    total_cost = db_manager.record_text_chat_call(
                        user_id=user_id,
                        model_name=model,
                        request_text=request_text,
                        response_text=response_text,
                        endpoint='/v1/text/chatcompletion_v2',
                        request_params=json.dumps({
                            "model": model,
                            "stream": False,
                            "messages_count": len(payload.get('messages', []))
                        })
                    )

                    logger.info(f"用户 {user_id} 文本聊天调用完成，费用: {total_cost}元")

                    return web.json_response(result)
                else:
                    error_text = await response.text()
                    logger.error(f"MiniMax API错误: {response.status} - {error_text}")
                    return web.json_response(
                        {"error": f"MiniMax API error: {response.status}"},
                        status=response.status
                    )

        except Exception as e:
            logger.error(f"非流式文本聊天请求出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

    async def _handle_stream_text_chat(self, payload, headers, user_id, model, request_text):
        """处理流式文本聊天"""
        try:
            async with self.session.post(
                f'{MINIMAX_BASE_URL}/v1/text/chatcompletion_v2',
                json=payload,
                headers=headers
            ) as response:
                if response.status == 200:
                    # 创建流式响应
                    response_stream = web.StreamResponse()
                    response_stream.headers['Content-Type'] = 'text/plain; charset=utf-8'
                    response_stream.headers['Cache-Control'] = 'no-cache'
                    response_stream.headers['Connection'] = 'keep-alive'

                    await response_stream.prepare(request)

                    # 收集完整响应文本用于计费
                    response_text_parts = []

                    # 转发流式数据并收集响应
                    async for chunk in response.content.iter_chunked(1024):
                        if chunk:
                            await response_stream.write(chunk)

                            # 解析SSE数据，提取文本内容
                            try:
                                chunk_str = chunk.decode('utf-8')
                                # 简单的SSE解析，寻找data:开头的行
                                for line in chunk_str.split('\n'):
                                    if line.startswith('data: '):
                                        try:
                                            data_json = json.loads(line[6:])  # 去掉"data: "前缀
                                            if 'choices' in data_json and len(data_json['choices']) > 0:
                                                choice = data_json['choices'][0]
                                                if 'delta' in choice and 'content' in choice['delta']:
                                                    response_text_parts.append(choice['delta']['content'])
                                        except (json.JSONDecodeError, KeyError):
                                            pass  # 忽略解析错误
                            except UnicodeDecodeError:
                                pass  # 忽略编码错误

                    await response_stream.write_eof()

                    # 合并完整响应文本并计费
                    response_text = ''.join(response_text_parts)
                    total_cost = db_manager.record_text_chat_call(
                        user_id=user_id,
                        model_name=model,
                        request_text=request_text,
                        response_text=response_text,
                        endpoint='/v1/text/chatcompletion_v2',
                        request_params=json.dumps({
                            "model": model,
                            "stream": True,
                            "messages_count": len(payload.get('messages', []))
                        })
                    )

                    logger.info(f"用户 {user_id} 流式文本聊天调用完成，费用: {total_cost}元")

                    return response_stream
                else:
                    error_text = await response.text()
                    logger.error(f"MiniMax API错误: {response.status} - {error_text}")
                    return web.json_response(
                        {"error": f"MiniMax API error: {response.status}"},
                        status=response.status
                    )

        except Exception as e:
            logger.error(f"流式文本聊天请求出错: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)

# 代理实例
proxy = None

async def init_proxy(app):
    """初始化代理"""
    global proxy
    proxy = MiniMaxHTTPProxy()
    await proxy.__aenter__()

async def cleanup_proxy(app):
    """清理代理资源"""
    global proxy
    if proxy:
        await proxy.__aexit__(None, None, None)

async def tts_handler(request):
    """TTS请求处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_tts_request(request)

async def async_tts_handler(request):
    """异步TTS请求处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_async_tts_request(request)

async def async_query_handler(request):
    """异步任务查询处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_async_query_request(request)

async def file_upload_handler(request):
    """文件上传处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_file_upload_request(request)

async def file_list_handler(request):
    """文件列表处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_file_list_request(request)

async def file_retrieve_handler(request):
    """文件检索处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_file_retrieve_request(request)

async def file_download_handler(request):
    """文件下载处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_file_download_request(request)

async def file_delete_handler(request):
    """文件删除处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_file_delete_request(request)

async def voice_clone_upload_handler(request):
    """语音复刻音频上传处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_voice_clone_upload_request(request)

async def prompt_audio_upload_handler(request):
    """示例音频上传处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_prompt_audio_upload_request(request)

async def voice_clone_handler(request):
    """快速语音复刻处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_voice_clone_request(request)

async def voice_design_handler(request):
    """音色设计处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_voice_design_request(request)

async def get_voices_handler(request):
    """查询可用音色处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_get_voices_request(request)

async def delete_voice_handler(request):
    """删除音色处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_delete_voice_request(request)

async def video_generation_handler(request):
    """视频生成处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_video_generation_request(request)

async def video_query_handler(request):
    """视频任务状态查询处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_video_query_request(request)

async def video_download_handler(request):
    """视频文件下载处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_video_download_request(request)

async def billing_query_handler(request):
    """用户计费查询处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_billing_query_request(request)

async def text_chat_handler(request):
    """文本聊天完成处理器"""
    global proxy
    if not proxy:
        return web.json_response({"error": "Proxy not initialized"}, status=500)

    return await proxy.handle_text_chat_request(request)

async def health_handler(request):
    """健康检查端点"""
    return web.json_response({
        "status": "healthy",
        "service": "MiniMax HTTP Proxy",
        "timestamp": datetime.now().isoformat()
    })

def create_app():
    """创建应用实例"""
    app = web.Application()

    # 注册启动和清理回调
    app.on_startup.append(init_proxy)
    app.on_cleanup.append(cleanup_proxy)

    # 注册路由
    # 文本聊天完成接口
    app.router.add_post('/v1/text/chatcompletion_v2', text_chat_handler)

    # TTS接口
    app.router.add_post('/v1/t2a_v2', tts_handler)
    app.router.add_post('/v1/t2a_async_v2', async_tts_handler)
    app.router.add_get('/v1/query/t2a_async_query_v2', async_query_handler)

    # 文件管理接口
    app.router.add_post('/v1/files/upload', file_upload_handler)
    app.router.add_get('/v1/files/list', file_list_handler)
    app.router.add_get('/v1/files/retrieve', file_retrieve_handler)
    app.router.add_get('/v1/files/retrieve_content', file_download_handler)
    app.router.add_post('/v1/files/delete', file_delete_handler)

    # 语音复刻接口
    app.router.add_post('/v1/files/upload/voice_clone', voice_clone_upload_handler)
    app.router.add_post('/v1/files/upload/prompt_audio', prompt_audio_upload_handler)
    app.router.add_post('/v1/voice_clone', voice_clone_handler)

    # 音色管理接口
    app.router.add_post('/v1/voice_design', voice_design_handler)
    app.router.add_post('/v1/get_voice', get_voices_handler)
    app.router.add_post('/v1/delete_voice', delete_voice_handler)

    # 视频生成接口
    app.router.add_post('/v1/video_generation', video_generation_handler)
    app.router.add_get('/v1/query/video_generation', video_query_handler)
    app.router.add_get('/v1/video/download', video_download_handler)

    # 计费查询接口
    app.router.add_get('/v1/billing/query', billing_query_handler)

    app.router.add_get('/health', health_handler)

    return app

async def main():
    """主函数"""
    app = create_app()

    # 启动服务器
    logger.info(f"启动MiniMax HTTP代理服务，端口: {PROXY_PORT}")
    logger.info("支持的接口:")
    logger.info("  POST /v1/text/chatcompletion_v2 - 文本聊天完成（支持流式、图像输入、tokens计费）")
    logger.info("  POST /v1/t2a_v2 - 流式和非流式TTS请求")
    logger.info("  POST /v1/t2a_async_v2 - 异步TTS请求（文本和文件输入）")
    logger.info("  GET /v1/query/t2a_async_query_v2 - 异步任务状态查询")
    logger.info("  POST /v1/files/upload - 文件上传")
    logger.info("  GET /v1/files/list - 文件列表查询")
    logger.info("  GET /v1/files/retrieve - 文件信息检索")
    logger.info("  GET /v1/files/retrieve_content - 文件内容下载")
    logger.info("  POST /v1/files/delete - 文件删除")
    logger.info("  POST /v1/files/upload/voice_clone - 语音复刻音频上传")
    logger.info("  POST /v1/files/upload/prompt_audio - 示例音频上传")
    logger.info("  POST /v1/voice_clone - 快速语音复刻")
    logger.info("  POST /v1/voice_design - 音色设计")
    logger.info("  POST /v1/get_voice - 查询可用音色")
    logger.info("  POST /v1/delete_voice - 删除音色")
    logger.info("  POST /v1/video_generation - 视频生成（文生视频/图生视频/首尾帧/主体参考）")
    logger.info("  GET /v1/query/video_generation - 视频生成任务状态查询")
    logger.info("  GET /v1/video/download - 视频文件下载")
    logger.info("  GET /v1/billing/query - 用户计费查询")
    logger.info("  GET /health - 健康检查")
    logger.info("使用Bearer Token进行用户认证")
    logger.info("API调用将记录到数据库中进行计费")

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, '0.0.0.0', PROXY_PORT)
    await site.start()

    # 保持服务器运行
    try:
        await asyncio.Future()  # 无限期运行
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭服务器...")
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())