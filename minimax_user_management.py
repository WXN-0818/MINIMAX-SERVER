import bcrypt
import jwt
import datetime
import uuid
from minimax_database import MinimaxDatabaseManager

# 用户类
class User:
    def __init__(self, user_id, username, password_hash, email):
        self.user_id = user_id
        self.username = username
        self.password_hash = password_hash
        self.email = email
        self.created_at = datetime.datetime.utcnow()
        self.is_active = True

    @staticmethod
    def hash_password(password: str) -> bytes:
        """Hash a password using bcrypt."""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    def check_password(self, password: str) -> bool:
        """Check if the provided password matches the stored password hash."""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash)

# 用户管理类
class MinimaxUserManager:
    ERROR_CODES = {
        401: "TOKEN_EXPIRED",
        403: "INVALID_TOKEN",
        200: "SUCCESS",
    }

    def __init__(self, db_manager: MinimaxDatabaseManager):
        self.db_manager = db_manager

    def register_user(self, username, password, email):
        """注册用户"""
        if self.db_manager.get_user(username):
            return "Username already exists"
        user_id = str(uuid.uuid4())
        password_hash = User.hash_password(password)
        user = User(user_id, username, password_hash, email)
        self.db_manager.add_user(user.user_id, user.username, user.password_hash, user.email)
        return "User registered successfully"

    def create_bearer_token(self, username, password, expiration_days=1):
        """创建Bearer Token"""
        user_data = self.db_manager.get_user(username)
        if user_data and bcrypt.checkpw(password.encode('utf-8'), user_data['password_hash'].encode('utf-8')):
            user = User(user_data['user_id'], user_data['username'], user_data['password_hash'], user_data['email'])

            payload = {
                "sub": user.user_id,
                "user_name": user.username,
                "iat": datetime.datetime.utcnow(),
                "exp": datetime.datetime.utcnow() + datetime.timedelta(days=expiration_days),
                "group_name": "",
                "group_id": "",
                "mail": user.email,
                "token_type": 1,
                "iss": "cloudsway"
            }

            keys = self.db_manager.get_keys()
            private_key_pem = keys[1]
            token = jwt.encode(payload, private_key_pem, algorithm='RS256')
            expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=expiration_days)
            self.db_manager.add_bearer_token(token, user.user_id, expires_at)
            return token
        return "Invalid username or password"

    def verify_bearer_token(self, token):
        """验证Bearer Token"""
        keys = self.db_manager.get_keys()
        public_key_pem = keys[2]
        try:
            payload = jwt.decode(token, public_key_pem, algorithms=['RS256'])

            with self.db_manager.get_connection() as connection:
                cursor = connection.cursor()
                try:
                    cursor.execute('SELECT is_revoked FROM bearer_tokens WHERE token = %s', (token,))
                    result = cursor.fetchone()
                    if result and result[0]:
                        return {"status": 401, "message": "Token has been revoked"}
                    return {"status": 200, "payload": payload}
                finally:
                    cursor.close()
        except jwt.ExpiredSignatureError:
            return {"status": 403, "message": "Token has expired"}
        except jwt.InvalidTokenError:
            return {"status": 401, "message": "Invalid token"}

    def get_user_info(self, username):
        """获取用户信息"""
        user = self.db_manager.get_user(username)
        if user:
            return {
                'user_id': user['user_id'],
                'username': user['username'],
                'email': user['email'],
                'created_at': user['created_at']
            }
        return "User not found"

    def get_user_by_id(self, user_id):
        """根据用户ID获取用户信息"""
        try:
            with self.db_manager.get_connection() as connection:
                cursor = connection.cursor(dictionary=True)
                cursor.execute('SELECT user_id, username, email, created_at FROM users WHERE user_id = %s', (user_id,))
                user = cursor.fetchone()
                return user
        except Exception as e:
            print(f"获取用户信息失败: {e}")
            return None

    def get_user_billing_info(self, user_id):
        """获取用户计费信息"""
        summary = self.db_manager.get_user_billing_summary(user_id)
        recent_calls = self.db_manager.get_user_api_calls(user_id, limit=10)

        return {
            "summary": summary,
            "recent_calls": recent_calls
        }

if __name__ == '__main__':
    # 测试代码
    db_manager = MinimaxDatabaseManager()
    user_manager = MinimaxUserManager(db_manager)

    # 测试注册和token创建
    print(user_manager.register_user('test_user', 'password123', 'test@example.com'))
    token = user_manager.create_bearer_token('test_user', 'password123', expiration_days=30)
    print(f"Token: {token}")

    # 验证token
    result = user_manager.verify_bearer_token(token)
    if result["status"] == 200:
        payload = result["payload"]
        print(f"Token is valid. User ID: {payload['sub']}")

        # 测试计费记录
        user_id = payload['sub']
        cost = db_manager.record_api_call(
            user_id=user_id,
            task_type='sync_tts',
            endpoint='/v1/t2a_v2',
            model_name='speech-2.5-hd-preview',
            request_text='这是一个测试文本，用来测试计费系统。',
            request_params=None
        )
        print(f"Cost calculated: {cost} 元")

        # 获取用户计费信息
        billing_info = user_manager.get_user_billing_info(user_id)
        print(f"User billing summary: {billing_info}")
    else:
        print(f"Token validation failed: {result}")