# MiniMax API Proxy Server

一个功能完善的 MiniMax API 代理服务器，提供 Text-to-Speech (TTS) 服务的完整解决方案，包括 HTTP 和 WebSocket 两种接口、用户管理、计费系统和音频存档功能。

## 🌟 核心特性

- **双协议支持**: 同时提供 HTTP 和 WebSocket 接口
- **完整的用户管理系统**: 包含注册、认证、Token 管理
- **灵活的计费系统**: 支持多种计费模型和定价策略
- **音频存档**: 自动保存生成的音频文件
- **实时流式传输**: WebSocket 支持音频流实时传输
- **异步任务处理**: 支持异步 TTS 任务和查询
- **详细的使用统计**: 记录每次 API 调用的详细信息

## 📁 项目结构

```
MINIMAX-SERVER/
├── minimax_http_proxy.py        # HTTP 代理服务器主程序
├── minimax_websocket_proxy.py   # WebSocket 代理服务器主程序
├── minimax_database.py          # 数据库管理和计费系统
├── minimax_user_management.py   # 用户管理核心功能
├── user_management_http.py      # 用户管理 HTTP API
├── admin_query_example.py       # 管理员查询工具
├── test_minimax_websocket.py    # WebSocket 测试客户端
├── audio_archive/               # 音频文件存储目录
└── concurrent_test_outputs/     # 测试输出目录
```

## 🚀 快速开始

### 环境要求

- Python 3.7+
- MySQL 5.7+ 或 MariaDB 10.3+
- 必要的 Python 包:
  ```bash
  pip install aiohttp websockets mysql-connector-python bcrypt pyjwt cryptography fastapi uvicorn
  ```

### 配置数据库

1. 创建 MySQL 数据库:
   ```sql
   CREATE DATABASE minimax;
   ```

2. 配置数据库连接（在代码中修改或通过环境变量设置）:
   ```python
   DB_HOST = '0.0.0.0'
   DB_USER = 'root'
   DB_PASSWORD = 'your_password'
   DB_NAME = 'minimax'
   ```

### 启动服务

1. **启动 HTTP 代理服务器** (端口 8768):
   ```bash
   python minimax_http_proxy.py
   ```

2. **启动 WebSocket 代理服务器** (端口 8766):
   ```bash
   python minimax_websocket_proxy.py
   ```

3. **启动用户管理 API** (端口 8000):
   ```bash
   python user_management_http.py
   ```

## 💡 核心组件详解

### 1. HTTP 代理服务器 (`minimax_http_proxy.py`)

提供完整的 HTTP API 代理功能，支持以下端点:

- **同步 TTS**: `/v1/t2a_v2` - 实时生成音频
- **异步 TTS**: `/v1/t2a_async_v2` - 提交异步任务
- **异步查询**: `/v1/query/t2a_async_query_v2` - 查询异步任务状态
- **文件管理**:
  - `/v1/files` - 文件上传
  - `/v1/files/list` - 文件列表
  - `/v1/files/{file_id}/content` - 获取文件内容

**主要特性**:
- Bearer Token 认证
- 自动音频存档
- 流式响应支持
- 详细的错误处理
- 请求日志记录

**使用示例**:
```python
import aiohttp
import json

async def call_tts():
    headers = {
        "Authorization": "Bearer YOUR_TOKEN",
        "Content-Type": "application/json"
    }

    data = {
        "text": "你好，世界",
        "model": "speech-01-turbo",
        "voice_id": "Bingjing"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:8768/v1/t2a_v2",
            headers=headers,
            json=data
        ) as response:
            audio_data = await response.read()
            # 保存音频文件
            with open("output.mp3", "wb") as f:
                f.write(audio_data)
```

### 2. WebSocket 代理服务器 (`minimax_websocket_proxy.py`)

提供实时流式音频传输，适合需要低延迟的应用场景。

**连接流程**:
1. 客户端连接到 `ws://localhost:8766`
2. 发送认证消息
3. 发送任务开始消息
4. 发送文本内容
5. 接收流式音频数据
6. 关闭连接

**消息格式**:
```json
{
    "type": "auth",
    "data": {
        "authorization": "Bearer YOUR_TOKEN"
    }
}

{
    "type": "start",
    "data": {
        "model": "speech-01-turbo",
        "voice_id": "Bingjing"
    }
}

{
    "type": "data",
    "data": {
        "text": "你好，世界"
    }
}
```

**特点**:
- 实时音频流传输
- 自动重连机制
- 心跳保活
- 音频自动存档
- 详细的计费记录

### 3. 数据库管理系统 (`minimax_database.py`)

核心数据库管理组件，提供：

**数据表结构**:
- `users` - 用户信息表
- `bearer_tokens` - Token 管理表
- `api_calls` - API 调用详细记录
- `pricing_config` - 定价配置表
- `user_billing_summary` - 用户账单汇总
- `voice_generation_history` - 音色生成历史
- `secure_key` - RSA 密钥存储

**主要功能**:
```python
class MinimaxDatabaseManager:
    def __init__(self, host, user, password, database)
    def create_tables()                    # 创建数据表
    def record_api_call()                  # 记录 API 调用
    def calculate_cost()                   # 计算费用
    def get_user_billing_summary()        # 获取用户账单
    def get_system_statistics()           # 系统统计信息
```

**计费模式**:
- **按字符计费**: TTS 服务按万字符计费
- **按音色计费**: 音色定制按次计费
- **按视频计费**: 视频生成按次计费
- **按 Token 计费**: 文本模型按百万 Token 计费

**字符计算规则**:
- 中文汉字: 2 个字符
- 其他字符: 1 个字符

### 4. 用户管理系统 (`minimax_user_management.py`)

提供完整的用户认证和授权功能：

**核心功能**:
- 用户注册与登录
- Bearer Token 生成与验证
- 密码加密存储（bcrypt）
- JWT Token 管理
- 用户信息查询

**API 端点** (通过 `user_management_http.py`):
- `POST /register` - 用户注册
- `POST /create_token` - 创建 Bearer Token
- `GET /user_info/{username}` - 获取用户信息
- `POST /verify_token` - 验证 Token
- `GET /user_billing/{username}` - 获取用户账单
- `GET /system_statistics` - 系统统计（管理员）

## 📊 管理工具

### 管理员查询工具 (`admin_query_example.py`)

提供命令行界面查询系统状态：

```bash
python admin_query_example.py
```

功能选项:
1. 查看所有用户和账单信息
2. 查看系统统计信息
3. 查看收入排行榜
4. 查询特定用户的调用记录

## 🔒 安全特性

- **Token 认证**: 所有 API 调用需要有效的 Bearer Token
- **密码加密**: 使用 bcrypt 加密存储用户密码
- **RSA 签名**: JWT Token 使用 RSA 算法签名
- **请求验证**: 严格的请求参数验证
- **SQL 注入防护**: 使用参数化查询
- **连接池管理**: 防止数据库连接泄露

## 📈 监控与日志

- **详细的 API 调用记录**: 每次调用都记录在数据库
- **实时计费**: 自动计算每次调用的费用
- **用户使用统计**: 追踪用户的使用情况
- **错误日志**: 完整的错误处理和日志记录
- **性能监控**: 支持查询响应时间和并发情况

## 🛠️ 配置选项

主要配置项（在源代码中修改）:

```python
# 端口配置
PROXY_PORT = 8768  # HTTP 代理端口
WEBSOCKET_PORT = 8766  # WebSocket 代理端口

# MiniMax API 配置
MINIMAX_API_KEY = "your_api_key"
MINIMAX_BASE_URL = "https://api.minimax.io"

# 音频存储配置
AUDIO_SAVE_BASE_DIR = "/path/to/audio/archive"
ENABLE_AUDIO_SAVE = True

# 文本长度限制
MAX_TEXT_LENGTH = 10000

# 数据库配置
DB_HOST = '0.0.0.0'
DB_USER = 'root'
DB_PASSWORD = 'your_password'
DB_NAME = 'minimax'
```

## 📝 测试

### WebSocket 测试客户端

使用提供的测试脚本:
```bash
python test_minimax_websocket.py
```

### HTTP 测试

```bash
# 同步 TTS
curl -X POST http://localhost:8768/v1/t2a_v2 \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "测试文本",
    "model": "speech-01-turbo",
    "voice_id": "Bingjing"
  }' \
  --output test.mp3

# 异步 TTS
curl -X POST http://localhost:8768/v1/t2a_async_v2 \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "测试文本",
    "model": "speech-01-turbo",
    "voice_id": "Bingjing"
  }'
```

## 🚧 注意事项

1. **生产环境部署**:
   - 修改默认密码和密钥
   - 使用环境变量管理敏感信息
   - 启用 HTTPS/WSS
   - 配置反向代理（如 Nginx）
   - 设置适当的防火墙规则

2. **性能优化**:
   - 调整数据库连接池大小
   - 启用查询缓存
   - 定期清理历史数据
   - 使用 CDN 分发音频文件

3. **备份策略**:
   - 定期备份数据库
   - 音频文件归档
   - 配置文件版本控制

## 📄 许可证

本项目仅供学习和研究使用，请遵守 MiniMax API 的使用条款。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request 来改进本项目。

## 📞 联系方式

如有问题或建议，请通过 GitHub Issues 联系。

---

**免责声明**: 本项目是独立开发的代理服务器，与 MiniMax 官方无关。使用时请遵守相关服务条款和法律法规。
