import asyncio
import websockets
import json
import ssl
import subprocess
import os

model = "speech-2.5-hd-preview"
file_format = "mp3"

class StreamAudioPlayer:
    def __init__(self):
        self.mpv_process = None
        
    def start_mpv(self):
        """Start MPV player process"""
        try:
            mpv_command = ["mpv", "--no-cache", "--no-terminal", "--", "fd://0"]
            self.mpv_process = subprocess.Popen(
                mpv_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print("MPV player started")
            return True
        except FileNotFoundError:
            print("Error: mpv not found. Please install mpv")
            return False
        except Exception as e:
            print(f"Failed to start mpv: {e}")
            return False
    
    def play_audio_chunk(self, hex_audio):
        """Play audio chunk"""
        try:
            if self.mpv_process and self.mpv_process.stdin:
                audio_bytes = bytes.fromhex(hex_audio)
                self.mpv_process.stdin.write(audio_bytes)
                self.mpv_process.stdin.flush()
                return True
        except Exception as e:
            print(f"Play failed: {e}")
            return False
        return False
    
    def stop(self):
        """Stop player"""
        if self.mpv_process:
            if self.mpv_process.stdin and not self.mpv_process.stdin.closed:
                self.mpv_process.stdin.close()
            try:
                self.mpv_process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.mpv_process.terminate()

async def establish_connection(api_key):
    """Establish WebSocket connection"""
    url = "ws://minimax-vinky-ws.xiaosuai.com"

    try:
        # 连接到本地WebSocket代理（不需要SSL）
        ws = await websockets.connect(url)

        # 发送认证信息（代理服务器期望的格式）
        auth_msg = {"bearer_token": api_key}
        await ws.send(json.dumps(auth_msg))

        # 接收认证响应
        connected = json.loads(await ws.recv())
        if connected.get("event") == "connected_success":
            print("Connection successful")
            return ws
        else:
            print(f"Authentication failed: {connected}")
            return None
    except Exception as e:
        print(f"Connection failed: {e}")
        return None

async def start_task(websocket):
    """Send task start request"""
    start_msg = {
        "event": "task_start",
        "model": model,
        "voice_setting": {
            "voice_id": "male-qn-qingse",
            "speed": 1,
            "vol": 1,
            "pitch": 0,
            "english_normalization": False
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": file_format,
            "channel": 1
        }
    }
    await websocket.send(json.dumps(start_msg))
    response = json.loads(await websocket.recv())
    return response.get("event") == "task_started"

async def continue_task_with_stream_play(websocket, text, player):
    """Send continue request and stream play audio"""
    await websocket.send(json.dumps({
        "event": "task_continue",
        "text": text
    }))

    chunk_counter = 1
    total_audio_size = 0
    audio_data = b""
    
    while True:
        try:
            response = json.loads(await websocket.recv())
            
            if "data" in response and "audio" in response["data"]:
                audio = response["data"]["audio"]
                if audio:
                    print(f"Playing chunk #{chunk_counter}")
                    audio_bytes = bytes.fromhex(audio)
                    if player.play_audio_chunk(audio):
                        total_audio_size += len(audio_bytes)
                        audio_data += audio_bytes
                        chunk_counter += 1
            
            if response.get("is_final"):
                print(f"Audio synthesis completed: {chunk_counter-1} chunks")
                if player.mpv_process and player.mpv_process.stdin:
                    player.mpv_process.stdin.close()
                
                # Save audio to file
                with open(f"output.{file_format}", "wb") as f:
                    f.write(audio_data)
                print(f"Audio saved as output.{file_format}")
                    
                estimated_duration = total_audio_size * 0.0625 / 1000
                wait_time = max(estimated_duration + 5, 10)
                return wait_time
                
        except Exception as e:
            print(f"Error: {e}")
            break
    
    return 10

async def close_connection(websocket):
    """Close connection"""
    if websocket:
        try:
            await websocket.send(json.dumps({"event": "task_finish"}))
            await websocket.close()
        except Exception:
            pass

async def main():
    API_KEY = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhNTI0OWZjMi0zMjU3LTQ5NWMtOTA1Yy03OWIwMjkzYzFhNWIiLCJ1c2VyX25hbWUiOiJtaW5pbWF4X3Rlc3QiLCJpYXQiOjE3NTg2MTE3ODAsImV4cCI6MTgxOTA5MTc4MCwiZ3JvdXBfbmFtZSI6IiIsImdyb3VwX2lkIjoiIiwibWFpbCI6Im1pbmltYXhAZXhhbXBsZS5jb20iLCJ0b2tlbl90eXBlIjoxLCJpc3MiOiJjbG91ZHN3YXkifQ.oRsoTn4rpemcZBalDJdl57nNS-HTFlyfGQzbXqfStWrVkO3lp_IQ8YmMpVwakCZB6NVr505fYle5MOog2x1Z3BQqLY5OTtBKncTFatghbMcD7J6RtYlj4PIWr1P7KfaJKffQi_zarQ5kdhAQWK35WHJ9FYYLGfoEjdPq7qxCHWxj4h5fm1v5dkjmZfMlH_yhPl3i823v929uY2sqKM9UlCcvxnarjXzmN-0cPKKWhyuhYyuiSM3FedAGaTGHrl1PlOGEdtCxnDKNwNmKPR2eGlJP0TTZsNwWa09krpQBt63WmLVN1gQb1Nxs938A0kYHYSZxBF8XeTdA9ENvpOiICg"
    TEXT = "真正的危险不是计算机开始像人一样思考，而是人开始像计算机一样思考。计算机只是可以帮我们处理一些简单事务。"

    player = StreamAudioPlayer()
    
    try:
        if not player.start_mpv():
            return
        
        ws = await establish_connection(API_KEY)
        if not ws:
            return

        if not await start_task(ws):
            print("Task startup failed")
            return

        wait_time = await continue_task_with_stream_play(ws, TEXT, player)
        await asyncio.sleep(wait_time)
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        player.stop()
        if 'ws' in locals():
            await close_connection(ws)

if __name__ == "__main__":
    asyncio.run(main())
