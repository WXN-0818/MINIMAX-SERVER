import asyncio
import websockets
import json
import ssl
from datetime import datetime, timedelta
import time
import re
import hashlib
import base64
import uuid
from minimax_user_management import MinimaxUserManager
from minimax_database import MinimaxDatabaseManager, count_length
import logging
import os
from decimal import Decimal

# 禁用websockets库的错误日志，避免显示HTTP请求错误
logging.getLogger('websockets.server').setLevel(logging.CRITICAL)
logging.getLogger('websockets.protocol').setLevel(logging.CRITICAL)

# 配置
PROXY_PORT = 8766
MINIMAX_API_KEY = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJHcm91cE5hbWUiOiJTbm93IEpvaG4iLCJVc2VyTmFtZSI6IlNub3cgSm9obiIsIkFjY291bnQiOiIiLCJTdWJqZWN0SUQiOiIxOTY2Mzc3NjMwMjE1MTg1MTEyIiwiUGhvbmUiOiIiLCJHcm91cElEIjoiMTk2NjM3NzYzMDIxMDk4NjcxMiIsIlBhZ2VOYW1lIjoiIiwiTWFpbCI6ImpvaG4wMDI1MDcwOEBnbWFpbC5jb20iLCJDcmVhdGVUaW1lIjoiMjAyNS0wOS0xNiAxMDo0NToxNiIsIlRva2VuVHlwZSI6MSwiaXNzIjoibWluaW1heCJ9.OhodgsM7URdE476H77dOH4i6RGE_HC78PXTh8Dh-wSOnUKf62go9pU-l5EQSWinHjTd77ZG4b9vqZ6BZGVGJzgrBoj9eJRMEdsBIO8pBT6TaVN9JVztKVjb9q-ET3MKsCsin6_cFNoBzdM4evYZ1FR6PNHNO_wZSjRNRq3R6tekwKSvqfMiGitsV5e8Qd3DfiquBAmH8iEJq6GR28WYezE4Z1YokeRHRE8xuaYXF4urcy1MVQc8aEgpZiK7TzDSQIAxCPKNzLxkZtIpt0QDdxkyPPqyC_UM7bAipewK6k-s135_EYibZXtadJPDIBGPUT79ScaxwCR141W4yB7C32A"

# 音频保存配置
AUDIO_SAVE_BASE_DIR = "/mnt/wxn/Change-API/minimax/audio_archive"  # 音频保存根目录
ENABLE_AUDIO_SAVE = True  # 是否启用音频保存功能

# 数据库和用户管理实例
host = os.environ.get('DB_HOST', '0.0.0.0')
user = os.environ.get('DB_USER', 'root')
password = os.environ.get('DB_PASSWORD', 'Cloudsway00@12Mk3')
database = os.environ.get('DB_NAME', 'minimax')
db_manager = MinimaxDatabaseManager(host=host, user=user, password=password, database=database)
user_manager = MinimaxUserManager(db_manager)

# 计费配置
MAX_TEXT_LENGTH = 10000      # 最大文本长度限制

def safe_filename(text, max_length=50):
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

def create_audio_path(username, text, audio_format='mp3'):
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
        print(f"创建音频保存路径时出错: {e}")
        return None, None

async def save_audio_file(filepath, audio_data):
    """保存音频文件"""
    if not filepath or not ENABLE_AUDIO_SAVE:
        return False

    try:
        # 根据数据类型进行解码
        if isinstance(audio_data, str):
            # MiniMax API返回的是十六进制编码，不是base64
            try:
                audio_binary = bytes.fromhex(audio_data)
                print("使用十六进制解码音频数据")
            except ValueError:
                # 如果十六进制解码失败，尝试base64
                try:
                    audio_binary = base64.b64decode(audio_data)
                    print("使用base64解码音频数据")
                except Exception:
                    print("音频数据解码失败")
                    return False
        else:
            audio_binary = audio_data

        with open(filepath, 'ab') as f:  # 使用追加模式，因为WebSocket是流式的
            f.write(audio_binary)

        return True
    except Exception as e:
        print(f"保存音频文件时出错: {e}")
        return False

async def calculate_websocket_cost(user_id, text, model_name, voice_id=None):
    """计算WebSocket TTS的费用"""
    try:
        # 计算字符数（使用新的统计方法）
        char_count = count_length(text)

        # 默认任务类型为流式TTS
        task_type = "sync_tts"

        # 查询定价配置
        pricing = db_manager.get_pricing_config(task_type, model_name)
        if not pricing:
            # 如果没有找到对应的定价，使用默认定价
            print(f"警告：未找到模型 {model_name} 的定价配置，使用默认定价")
            unit_price = Decimal('3.5')  # 默认3.5元/万字符
            billing_unit = 'per_10k_chars'
        else:
            unit_price = pricing['unit_price']
            billing_unit = pricing['billing_unit']

        # 计算TTS费用
        if billing_unit == 'per_10k_chars':
            tts_cost = (Decimal(char_count) / Decimal('10000')) * unit_price
        else:
            tts_cost = unit_price  # 其他计费单位

        voice_cost = Decimal('0')

        # 检查音色延迟计费（如果使用自定义音色）
        if voice_id and not voice_id.startswith('male-') and not voice_id.startswith('female-'):
            # 这是自定义音色，检查是否需要收费
            voice_cost = db_manager.check_and_charge_voice(user_id, voice_id, task_type='voice_design')

        total_cost = tts_cost + voice_cost

        return {
            'char_count': char_count,
            'unit_price': unit_price,
            'tts_cost': tts_cost,
            'voice_cost': voice_cost,
            'total_cost': total_cost,
            'billing_unit': billing_unit
        }

    except Exception as e:
        print(f"计算费用时出错: {e}")
        # 返回默认值
        char_count = count_length(text) if text else 0
        return {
            'char_count': char_count,
            'unit_price': Decimal('3.5'),
            'tts_cost': Decimal('0.01'),
            'voice_cost': Decimal('0'),
            'total_cost': Decimal('0.01'),
            'billing_unit': 'per_10k_chars'
        }

async def establish_minimax_connection():
    """建立与minimax的WebSocket连接"""
    url = "wss://api.minimax.io/ws/v1/t2a_v2"
    headers = {"Authorization": f"Bearer {MINIMAX_API_KEY}"}

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        ws = await websockets.connect(url, additional_headers=headers, ssl=ssl_context)
        connected = json.loads(await ws.recv())
        if connected.get("event") == "connected_success":
            print("与minimax服务器连接成功")
            return ws
        print(f"连接minimax失败: {connected}")
        return None
    except Exception as e:
        print(f"连接minimax时发生错误: {e}")
        return None


async def handle_client(client_websocket):
    """处理客户端连接"""
    user_id = None
    minimax_ws = None
    session_start_time = datetime.now()
    current_model = None
    current_voice_id = None

    try:
        # 1. 认证客户端（使用Bearer Token）
        auth_data = await client_websocket.recv()
        auth = json.loads(auth_data)

        bearer_token = auth.get("bearer_token")

        # 验证Bearer Token
        if not bearer_token:
            await client_websocket.send(json.dumps({
                "event": "error",
                "message": "缺少Bearer Token"
            }))
            return

        # 验证token
        token_result = user_manager.verify_bearer_token(bearer_token)
        if token_result["status"] != 200:
            await client_websocket.send(json.dumps({
                "event": "error",
                "message": f"Token验证失败: {token_result['message']}"
            }))
            return

        user_id = token_result["payload"]["sub"]
        await client_websocket.send(json.dumps({
            "event": "connected_success",
            "message": "认证成功",
            "user_id": user_id
        }))
        print(f"用户 {user_id} 认证成功")

        # 2. 处理客户端消息并转发到minimax
        while True:
            try:
                message = await client_websocket.recv()
                data = json.loads(message)

                # 如果是开始任务，建立与minimax的连接并记录模型信息
                if data.get("event") == "task_start" and not minimax_ws:
                    # 记录模型和音色信息
                    current_model = data.get("model", "speech-02-hd")
                    voice_setting = data.get("voice_setting", {})
                    current_voice_id = voice_setting.get("voice_id")

                    minimax_ws = await establish_minimax_connection()
                    if not minimax_ws:
                        await client_websocket.send(json.dumps({
                            "event": "error",
                            "message": "无法连接到语音合成服务"
                        }))
                        break

                    # 转发开始任务请求
                    await minimax_ws.send(message)
                    response = await minimax_ws.recv()
                    await client_websocket.send(response)
                    
                # 如果是继续任务，检查文本长度并进行计费
                elif data.get("event") == "task_continue" and minimax_ws:
                    # 直接从顶级text字段提取文本
                    text = data.get("text", "")
                    text_length = len(text)

                    # 检查文本长度限制
                    if text_length > MAX_TEXT_LENGTH:
                        await client_websocket.send(json.dumps({
                            "event": "error",
                            "message": f"文本过长，最大支持{MAX_TEXT_LENGTH}个字符"
                        }))
                        continue

                    # 计算费用
                    cost_info = await calculate_websocket_cost(
                        user_id, text, current_model or "speech-02-hd", current_voice_id
                    )

                    # 转发继续任务请求
                    print(f"发送文本到minimax: {text[:50]}...")
                    await minimax_ws.send(message)

                    # 接收并转发结果
                    audio_chunks = []
                    synthesis_success = False

                    while True:
                        response = await minimax_ws.recv()
                        response_data = json.loads(response)

                        print(f"从minimax接收到响应: {response_data.get('event', 'unknown')}")

                        # 转发给客户端
                        await client_websocket.send(response)

                        # 如果是错误或失败事件，记录详细信息
                        if response_data.get("event") in ["task_failed", "error"]:
                            print(f"任务失败详情: {response_data}")
                            break

                        if "data" in response_data and "audio" in response_data["data"]:
                            audio_chunks.append(response_data["data"]["audio"])

                        if response_data.get("is_final"):
                            synthesis_success = True
                            break

                    # 只有在合成成功时才记录费用和保存音频
                    if synthesis_success:
                        # 保存音频文件
                        if audio_chunks and ENABLE_AUDIO_SAVE:
                            try:
                                # 获取用户信息
                                username = None
                                try:
                                    user_info = user_manager.get_user_by_id(user_id)
                                    username = user_info['username'] if user_info else user_id
                                except:
                                    username = user_id

                                # 创建音频文件路径
                                audio_format = 'mp3'  # WebSocket默认格式
                                audio_path, info_path = create_audio_path(username, text, audio_format)

                                if audio_path:
                                    # 合并所有音频块并保存
                                    combined_audio = b''
                                    for chunk in audio_chunks:
                                        try:
                                            combined_audio += base64.b64decode(chunk)
                                        except Exception as e:
                                            print(f"解码音频块时出错: {e}")

                                    # 保存完整音频文件
                                    if combined_audio:
                                        with open(audio_path, 'wb') as f:
                                            f.write(combined_audio)
                                        print(f"音频文件已保存: {audio_path}")

                            except Exception as e:
                                print(f"保存WebSocket音频文件时出错: {e}")

                        try:
                            # 记录详细的API调用信息
                            request_params_json = json.dumps({
                                "model": current_model,
                                "voice_id": current_voice_id,
                                "event": "task_continue"
                            })

                            if current_voice_id and not current_voice_id.startswith('male-') and not current_voice_id.startswith('female-'):
                                # 使用带音色检查的方法
                                db_manager.record_api_call_with_voice_check(
                                    user_id=user_id,
                                    task_type="sync_tts",
                                    endpoint="/ws/v1/t2a_v2",
                                    model_name=current_model or "speech-02-hd",
                                    request_text=text,
                                    request_params=request_params_json,
                                    voice_id=current_voice_id
                                )
                            else:
                                # 使用普通方法
                                db_manager.record_api_call(
                                    user_id=user_id,
                                    task_type="sync_tts",
                                    endpoint="/ws/v1/t2a_v2",
                                    model_name=current_model or "speech-02-hd",
                                    request_text=text,
                                    request_params=request_params_json
                                )

                            print(f"用户 {user_id} WebSocket TTS调用 - 字符数: {cost_info['char_count']}, 费用: {cost_info['total_cost']}元")

                            # 发送详细的使用总结给客户端
                            await client_websocket.send(json.dumps({
                                "event": "usage_summary",
                                "char_count": cost_info['char_count'],
                                "tts_cost": float(cost_info['tts_cost']),
                                "voice_cost": float(cost_info['voice_cost']),
                                "total_cost": float(cost_info['total_cost']),
                                "model_name": current_model or "speech-02-hd",
                                "voice_id": current_voice_id,
                                "message": "API调用已记录并计费"
                            }))

                        except Exception as e:
                            print(f"记录API调用失败: {e}")
                            # 仍然发送基本的使用总结
                            await client_websocket.send(json.dumps({
                                "event": "usage_summary",
                                "char_count": cost_info['char_count'],
                                "message": "API调用完成，但计费记录失败"
                            }))
                    else:
                        # 合成失败，不收费
                        await client_websocket.send(json.dumps({
                            "event": "usage_summary",
                            "message": "TTS合成失败，未产生费用"
                        }))
                    
                # 如果是结束任务，关闭连接
                elif data.get("event") == "task_finish" and minimax_ws:
                    await minimax_ws.send(message)
                    await minimax_ws.close()
                    minimax_ws = None
                    break
                    
                # 其他消息直接转发
                elif minimax_ws:
                    await minimax_ws.send(message)
                    response = await minimax_ws.recv()
                    await client_websocket.send(response)
                    
            except websockets.exceptions.ConnectionClosed:
                print(f"客户端 {user_id} 断开连接")
                break
            except Exception as e:
                print(f"处理消息时出错: {e}")
                await client_websocket.send(json.dumps({
                    "event": "error",
                    "message": f"处理请求时出错: {str(e)}"
                }))
                break
                
    except Exception as e:
        print(f"处理客户端 {user_id} 时出错: {e}")
    finally:
        # 清理连接
        if minimax_ws:
            try:
                await minimax_ws.send(json.dumps({"event": "task_finish"}))
                await minimax_ws.close()
            except:
                pass
                
        # 计算会话时长
        session_duration = (datetime.now() - session_start_time).total_seconds()
        print(f"用户 {user_id} 的会话结束，持续时间: {session_duration:.2f}秒")


async def main():
    """主函数，启动服务器"""
    # 启动WebSocket服务器
    print(f"启动MiniMax WebSocket代理服务，端口: {PROXY_PORT}")
    print("✓ 使用Bearer Token进行用户认证")
    print("✓ 使用新的minimax数据库进行详细计费")
    print("✓ 支持音色延迟计费机制")
    print("✓ 实时字符数统计与费用计算")
    print("✓ 详细API调用记录和账单管理")
    
    # 启动WebSocket服务器，屏蔽HTTP请求错误日志
    async with websockets.serve(
        handle_client, 
        "0.0.0.0", 
        PROXY_PORT
    ):
        # 保持服务器运行
        await asyncio.Future()  # 无限期运行


if __name__ == "__main__":
    # 正确启动事件循环
    asyncio.run(main())
    