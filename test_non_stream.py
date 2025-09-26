import requests
import json

api_key = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhNTI0OWZjMi0zMjU3LTQ5NWMtOTA1Yy03OWIwMjkzYzFhNWIiLCJ1c2VyX25hbWUiOiJtaW5pbWF4X3Rlc3QiLCJpYXQiOjE3NTg2MTE3ODAsImV4cCI6MTgxOTA5MTc4MCwiZ3JvdXBfbmFtZSI6IiIsImdyb3VwX2lkIjoiIiwibWFpbCI6Im1pbmltYXhAZXhhbXBsZS5jb20iLCJ0b2tlbl90eXBlIjoxLCJpc3MiOiJjbG91ZHN3YXkifQ.oRsoTn4rpemcZBalDJdl57nNS-HTFlyfGQzbXqfStWrVkO3lp_IQ8YmMpVwakCZB6NVr505fYle5MOog2x1Z3BQqLY5OTtBKncTFatghbMcD7J6RtYlj4PIWr1P7KfaJKffQi_zarQ5kdhAQWK35WHJ9FYYLGfoEjdPq7qxCHWxj4h5fm1v5dkjmZfMlH_yhPl3i823v929uY2sqKM9UlCcvxnarjXzmN-0cPKKWhyuhYyuiSM3FedAGaTGHrl1PlOGEdtCxnDKNwNmKPR2eGlJP0TTZsNwWa09krpQBt63WmLVN1gQb1Nxs938A0kYHYSZxBF8XeTdA9ENvpOiICg"
url = f"https://minimax-vinky.xiaosuai.com/v1/t2a_v2"

payload = json.dumps({
    "model": "speech-2.5-hd-preview",
    "text": "今天是不是很开心呀，当然了！我今天去上海玩了，我感觉上海好繁华！!",
    "stream": False,
    "voice_setting":{
        "voice_id": "male-qn-qingse",
        "speed": 1,
        "vol": 1,
        "pitch": 0,
        "emotion": "happy"
    },
    "pronunciation_dict":{
        "tone": ["处理/(chu3)(li3)", "危险/dangerous"]
    },
    "audio_setting":{
        "sample_rate": 32000,
        "bitrate": 128000,
        "format": "mp3",
        "channel": 1
    },
    "subtitle_enable": False
  })
headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json'
}

response = requests.request("POST", url, stream=True, headers=headers, data=payload)

print(f"响应内容: {response.text}")
parsed_json = json.loads(response.text)

# get audio
audio_value = bytes.fromhex(parsed_json['data']['audio'])
with open('output.mp3', 'wb') as f:
    f.write(audio_value)

