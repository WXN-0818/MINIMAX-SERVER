from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from minimax_user_management import MinimaxUserManager
from minimax_database import MinimaxDatabaseManager
import os

app = FastAPI()

# 数据库管理器和用户管理器实例
host = os.environ.get('DB_HOST', '0.0.0.0')
user = os.environ.get('DB_USER', 'root')
password = os.environ.get('DB_PASSWORD', 'Cloudsway00@12Mk3')
database = os.environ.get('DB_NAME', 'minimax')
db_manager = MinimaxDatabaseManager(host=host, user=user, password=password, database=database)
user_manager = MinimaxUserManager(db_manager)

# 用户注册请求体
class UserRegister(BaseModel):
    username: str
    password: str
    email: str

# 用户登录请求体
class UserTokenRequest(BaseModel):
    username: str
    password: str
    expiration_days: int = 1  # 默认授权天数为 1 天

# 用户注册接口
@app.post("/register")
async def register_user(user: UserRegister):
    result = user_manager.register_user(user.username, user.password, user.email)
    if result == "Username already exists":
        raise HTTPException(status_code=400, detail=result)
    return {"message": result}

# 创建 Bearer Token 接口
@app.post("/create_token")
async def create_bearer_token(user: UserTokenRequest):
    token = user_manager.create_bearer_token(user.username, user.password, expiration_days=user.expiration_days)
    if token == "Invalid username or password":
        raise HTTPException(status_code=400, detail=token)
    print(f"Created token1: {token}")
    return {"token": token}

# 获取用户信息接口
@app.get("/user/{username}")
async def get_user_info(username: str):
    user_info = user_manager.get_user_info(username)
    if user_info == "User not found":
        raise HTTPException(status_code=404, detail=user_info)
    return user_info

class TokenRequest(BaseModel):
    token: str

@app.post("/verify_token")
async def verify_bearer_token(token_request: TokenRequest):
    token = token_request.token  # 从请求体中提取 token
    result = user_manager.verify_bearer_token(token)  # 验证 token 的逻辑
    if result["status"] != 200:
        raise HTTPException(status_code=result["status"], detail=result["message"])
    return {"message": "Token is valid", "payload": result["payload"]}

@app.post("/increment_token_call")
async def increment_token_call(token_request: TokenRequest):
    try:
        with db_manager.get_connection() as connection:
            cursor = connection.cursor()
            # 查询 token 是否存在
            cursor.execute('SELECT COUNT(*) FROM bearer_tokens WHERE token = %s', (token_request.token,))
            token_exists = cursor.fetchone()[0] > 0
            cursor.close()

            if not token_exists:
                raise HTTPException(status_code=404, detail="Token not found")

        # 增加调用次数（如果新系统有这个方法）
        # 注意：新的计费系统可能不需要这个功能，因为我们有详细的API调用记录
        return {"message": "Token call count noted (detailed billing system active)"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 新增计费查询接口
@app.get("/billing/{username}")
async def get_user_billing(username: str):
    """获取用户计费信息"""
    try:
        # 先获取用户信息
        user_info = user_manager.get_user_info(username)
        if user_info == "User not found":
            raise HTTPException(status_code=404, detail="User not found")

        user_id = user_info['user_id']

        # 获取计费信息
        billing_summary = db_manager.get_user_billing_summary(user_id)
        recent_calls = db_manager.get_user_api_calls(user_id, limit=20)

        return {
            "user_info": user_info,
            "billing_summary": billing_summary,
            "recent_calls": recent_calls
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 管理员接口 - 获取所有用户信息和计费汇总
@app.get("/admin/all_users")
async def get_all_users_with_billing():
    """管理员接口：获取所有用户信息及其计费汇总"""
    try:
        users_with_billing = db_manager.get_all_users_with_billing()
        return {
            "total_users": len(users_with_billing),
            "users": users_with_billing
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 管理员接口 - 获取系统统计信息
@app.get("/admin/statistics")
async def get_system_statistics():
    """管理员接口：获取系统统计信息"""
    try:
        stats = db_manager.get_system_statistics()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 管理员接口 - 获取消费最高的用户
@app.get("/admin/top_users")
async def get_top_users_by_revenue(limit: int = 10):
    """管理员接口：获取消费最高的用户"""
    try:
        if limit > 100:  # 限制最大查询数量
            limit = 100
        top_users = db_manager.get_top_users_by_revenue(limit)
        return {
            "limit": limit,
            "top_users": top_users
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 管理员接口 - 获取特定用户的详细API调用记录
@app.get("/admin/user_calls/{username}")
async def get_user_detailed_calls(username: str, limit: int = 50, offset: int = 0):
    """管理员接口：获取用户详细的API调用记录"""
    try:
        # 先获取用户信息
        user_info = user_manager.get_user_info(username)
        if user_info == "User not found":
            raise HTTPException(status_code=404, detail="User not found")

        user_id = user_info['user_id']

        # 获取详细调用记录
        api_calls = db_manager.get_user_api_calls(user_id, limit, offset)

        return {
            "username": username,
            "user_id": user_id,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "returned_count": len(api_calls)
            },
            "api_calls": api_calls
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("user_management_http:app", host='0.0.0.0', port=8021, reload=True) 