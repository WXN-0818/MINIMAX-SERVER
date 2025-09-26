#!/usr/bin/env python3
"""
MiniMax管理员查询示例脚本
展示如何使用管理员接口查询所有用户信息和计费数据
"""

import requests
import json
from datetime import datetime

# 配置
BASE_URL = "http://localhost:8021"

def format_datetime(dt_str):
    """格式化时间显示"""
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return dt_str

def format_currency(amount):
    """格式化金额显示"""
    if amount is None:
        return "0.00"
    return f"{float(amount):.4f}"

def get_display_width(text):
    """计算文本的显示宽度（中文字符占2个宽度，英文字符占1个宽度）"""
    width = 0
    for char in str(text):
        if '\u4e00' <= char <= '\u9fff':  # 中文字符范围
            width += 2
        else:
            width += 1
    return width

def pad_text(text, target_width):
    """填充文本到指定显示宽度"""
    text = str(text)
    current_width = get_display_width(text)
    if current_width >= target_width:
        # 如果文本太长，截断并保证不超过目标宽度
        truncated = ""
        width = 0
        for char in text:
            char_width = 2 if '\u4e00' <= char <= '\u9fff' else 1
            if width + char_width > target_width - 3:  # 留3个字符给"..."
                truncated += "..."
                break
            truncated += char
            width += char_width
        return truncated
    else:
        # 用空格填充
        padding = target_width - current_width
        return text + " " * padding

def query_all_users():
    """查询所有用户信息和计费汇总"""
    print("=== 查询所有用户信息和计费汇总 ===\n")

    try:
        response = requests.get(f"{BASE_URL}/admin/all_users")
        if response.status_code == 200:
            data = response.json()
            users = data['users']

            print(f"总用户数: {data['total_users']}\n")
            print("用户详情:")
            print("-" * 128)
            # 表头也用同样的方式处理
            header_username = pad_text("用户名", 16)
            header_email = pad_text("邮箱", 28)
            header_created = pad_text("注册时间", 20)
            header_calls = pad_text("调用次数", 10)
            header_chars = pad_text("字符数", 10)
            header_amount = pad_text("消费金额", 12)
            header_last = pad_text("最后调用", 20)
            print(f"{header_username} {header_email} {header_created} {header_calls} {header_chars} {header_amount} {header_last}")
            print("-" * 128)

            for user in users:
                username = pad_text(user['username'], 16)
                email = pad_text(user['email'], 28)
                created_at = pad_text(format_datetime(user['user_created_at'])[:19], 20)
                total_calls = pad_text(str(user['total_calls']), 10)
                total_chars = pad_text(str(user['total_chars']), 10)
                total_amount = pad_text(format_currency(user['total_amount']), 12)
                last_call = pad_text(format_datetime(user['last_call_at'])[:19] if user['last_call_at'] else "未调用", 20)

                print(f"{username} {email} {created_at} {total_calls} {total_chars} {total_amount} {last_call}")

        else:
            print(f"请求失败: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"查询失败: {e}")

def query_system_statistics():
    """查询系统统计信息"""
    print("\n=== 系统统计信息 ===\n")

    try:
        response = requests.get(f"{BASE_URL}/admin/statistics")
        if response.status_code == 200:
            stats = response.json()

            # 用户统计
            user_stats = stats['user_stats']
            print(f"活跃用户数: {user_stats['total_users']}")

            # API调用统计
            api_stats = stats['api_stats']
            print(f"总API调用次数: {api_stats['total_api_calls']}")
            print(f"总字符数: {api_stats['total_chars']:,}")
            print(f"总收入: {format_currency(api_stats['total_revenue'])}元")

            # 今日统计
            today_stats = stats['today_stats']
            print(f"今日调用次数: {today_stats['today_calls']}")
            print(f"今日字符数: {today_stats['today_chars']:,}")
            print(f"今日收入: {format_currency(today_stats['today_revenue'])}元")

            # 按任务类型统计
            task_stats = stats['task_stats']
            if task_stats:
                print("\n按任务类型统计:")
                print("-" * 68)
                print(f"{'任务类型':<25} {'调用次数':<10} {'字符数':<12} {'收入':<15}")
                print("-" * 68)
                for task in task_stats:
                    task_type = task['task_type']
                    call_count = task['call_count']
                    total_chars = task['total_chars']
                    total_cost = format_currency(task['total_cost'])
                    print(f"{task_type:<25} {call_count:<10} {total_chars:<12} {total_cost:<15}")

            # 音色统计
            voice_stats = stats['voice_stats']
            if voice_stats:
                print("\n音色统计:")
                print("-" * 60)
                print(f"{'音色类型':<16} {'总数':<8} {'已收费':<10} {'收入':<15}")
                print("-" * 60)
                for voice in voice_stats:
                    task_type = voice['task_type']
                    total_voices = voice['total_voices']
                    charged_voices = voice['charged_voices']
                    voice_revenue = format_currency(voice['voice_revenue'])
                    print(f"{task_type:<16} {total_voices:<8} {charged_voices:<10} {voice_revenue:<15}")

        else:
            print(f"请求失败: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"查询失败: {e}")

def query_top_users(limit=5):
    """查询消费最高的用户"""
    print(f"\n=== 消费最高的{limit}位用户 ===\n")

    try:
        response = requests.get(f"{BASE_URL}/admin/top_users?limit={limit}")
        if response.status_code == 200:
            data = response.json()
            top_users = data['top_users']

            if not top_users:
                print("暂无消费数据")
                return

            print("-" * 88)
            # 表头统一处理
            header_rank = pad_text("排名", 6)
            header_username = pad_text("用户名", 16)
            header_email = pad_text("邮箱", 28)
            header_calls = pad_text("调用次数", 10)
            header_amount = pad_text("消费金额", 15)
            print(f"{header_rank} {header_username} {header_email} {header_calls} {header_amount}")
            print("-" * 88)

            for i, user in enumerate(top_users, 1):
                rank = pad_text(str(i), 6)
                username = pad_text(user['username'], 16)
                email = pad_text(user['email'], 28)
                total_calls = pad_text(str(user['total_calls']), 10)
                total_amount = pad_text(format_currency(user['total_amount']), 15)
                print(f"{rank} {username} {email} {total_calls} {total_amount}")

        else:
            print(f"请求失败: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"查询失败: {e}")

def query_user_detailed_calls(username, limit=10):
    """查询指定用户的详细API调用记录"""
    print(f"\n=== {username} 的最近{limit}条API调用记录 ===\n")

    try:
        response = requests.get(f"{BASE_URL}/admin/user_calls/{username}?limit={limit}")
        if response.status_code == 200:
            data = response.json()
            api_calls = data['api_calls']

            if not api_calls:
                print("暂无API调用记录")
                return

            print("-" * 150)
            # 表头统一处理
            header_task = pad_text("任务类型", 15)
            header_model = pad_text("模型", 25)
            header_chars = pad_text("字符数", 8)
            header_cost = pad_text("费用", 10)
            header_time = pad_text("时间", 20)
            header_text = pad_text("请求文本", 60)
            print(f"{header_task} {header_model} {header_chars} {header_cost} {header_time} {header_text}")
            print("-" * 150)

            for call in api_calls:
                task_type = pad_text(call['task_type'], 15)
                model_name = pad_text(call['model_name'] if call['model_name'] else "N/A", 25)
                char_count = pad_text(str(call['char_count']), 8)
                cost_amount = pad_text(format_currency(call['cost_amount']), 10)
                created_at = pad_text(format_datetime(call['created_at'])[:19], 20)
                # 显示请求文本，使用pad_text处理中文字符
                request_text = call.get('request_text', 'N/A')
                if not request_text:
                    request_text = "N/A"
                request_text = pad_text(request_text, 60)

                print(f"{task_type} {model_name} {char_count} {cost_amount} {created_at} {request_text}")

        else:
            print(f"请求失败: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"查询失败: {e}")

def main():
    """主函数"""
    print("MiniMax 管理员数据查询工具")
    print("=" * 50)

    # 1. 查询所有用户
    query_all_users()

    # 2. 查询系统统计
    query_system_statistics()

    # 3. 查询消费排行
    query_top_users(5)

    # 4. 查询特定用户详情（如果有用户的话）
    try:
        response = requests.get(f"{BASE_URL}/admin/all_users")
        if response.status_code == 200:
            users = response.json()['users']
            if users:
                # 取第一个有消费记录的用户作为示例
                sample_user = None
                for user in users:
                    if user['total_calls'] > 0:
                        sample_user = user['username']
                        break

                if sample_user:
                    query_user_detailed_calls("九州汇天", 10)
    except:
        pass

    print("\n" + "=" * 50)
    print("查询完成！")

if __name__ == "__main__":
    main()