"""
企业微信 Bot - Web 服务器
部署到 Render 等云平台，提供稳定的公网回调地址
"""

import sys
import os
import hashlib
import base64
import struct
import xml.etree.ElementTree as ET
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import yaml

# 加载配置
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}

config = load_config()

# 从配置或环境变量读取
CORP_ID = os.environ.get("CORP_ID", config.get("wecom", {}).get("corp_id", ""))
AGENT_ID = int(os.environ.get("AGENT_ID", config.get("wecom", {}).get("agent_id", 0)))
SECRET = os.environ.get("SECRET", config.get("wecom", {}).get("secret", ""))
TOKEN = os.environ.get("WECOM_TOKEN", config.get("wecom", {}).get("token", "bot123"))
ENCODING_AES_KEY = os.environ.get("ENCODING_AES_KEY", config.get("wecom", {}).get("encoding_aes_key", ""))
AI_API_KEY = os.environ.get("AI_API_KEY", config.get("ai", {}).get("api_key", ""))
AI_BASE_URL = os.environ.get("AI_BASE_URL", config.get("ai", {}).get("base_url", ""))
AI_MODEL = os.environ.get("AI_MODEL", config.get("ai", {}).get("model", ""))

# 初始化 AI 服务（延迟加载）
ai_service = None
user_histories = {}

def get_ai():
    global ai_service
    if ai_service is None:
        from aicore.service import AIService
        ai_service = AIService()
    return ai_service


# Flask 应用
app = Flask(__name__)

# 获取 access_token
import requests as req

access_token_cache = {"token": None, "expires": 0}

def get_access_token():
    import time
    if access_token_cache["token"] and time.time() < access_token_cache["expires"]:
        return access_token_cache["token"]

    url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
    resp = req.get(url, params={"corpid": CORP_ID, "corpsecret": SECRET})
    data = resp.json()
    if data.get("errcode") != 0:
        raise Exception(f"获取 token 失败: {data}")

    access_token_cache["token"] = data["access_token"]
    access_token_cache["expires"] = time.time() + data.get("expires_in", 7200) - 300
    return access_token_cache["token"]


def send_message(user_id, content):
    """发送文本消息"""
    token = get_access_token()
    url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
    data = {
        "touser": user_id,
        "msgtype": "text",
        "agentid": AGENT_ID,
        "text": {"content": content},
    }
    resp = req.post(url, json=data)
    return resp.json()


@app.route("/")
def index():
    return "企业微信 AI Bot 运行中 ✅"


def decrypt_echostr(encrypted_echostr, encoding_aes_key, corp_id):
    """解密企业微信的 echostr"""
    # EncodingAESKey 是 43 字符，Base64 编码后得到 32 字节的 AES 密钥
    aes_key = base64.b64decode(encoding_aes_key + "=")
    # echostr 是 Base64 编码的
    encrypted_data = base64.b64decode(encrypted_echostr)
    # IV 是 AES 密钥的前 16 字节
    iv = aes_key[:16]
    # AES-CBC 解密
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted_data) + decryptor.finalize()
    # 去除 PKCS7 填充
    pad_len = decrypted[-1]
    decrypted = decrypted[:-pad_len]
    # 解密后的数据：16 字节随机 + 4 字节消息长度 + 消息内容 + corp_id
    content_len = struct.unpack(">I", decrypted[16:20])[0]
    content = decrypted[20:20 + content_len].decode("utf-8")
    from_corp_id = decrypted[20 + content_len:].decode("utf-8")
    if from_corp_id != corp_id:
        raise ValueError(f"corp_id 不匹配: {from_corp_id} != {corp_id}")
    return content


@app.route("/wecom/callback", methods=["GET"])
def verify():
    """企业微信验证回调 URL"""
    msg_signature = request.args.get("msg_signature", request.args.get("signature", ""))
    timestamp = request.args.get("timestamp", "")
    nonce = request.args.get("nonce", "")
    echostr = request.args.get("echostr", "")

    print(f"[验证] msg_signature={msg_signature}, timestamp={timestamp}, nonce={nonce}")
    print(f"[验证] ENCODING_AES_KEY 长度: {len(ENCODING_AES_KEY)}")

    # 签名验证
    tmp_list = sorted([TOKEN, timestamp, nonce, echostr])
    tmp_str = "".join(tmp_list)
    hash_str = hashlib.sha1(tmp_str.encode()).hexdigest()

    print(f"[验证] 计算: {hash_str}, 期望: {msg_signature}")

    if hash_str == msg_signature:
        # 解密 echostr
        try:
            decrypted = decrypt_echostr(echostr, ENCODING_AES_KEY, CORP_ID)
            print(f"[验证] ✅ 解密成功: {decrypted}")
            return decrypted
        except Exception as e:
            print(f"[验证] ❌ 解密失败: {e}")
            return f"decrypt error: {e}", 403
    else:
        print("[验证] ❌ 签名不匹配")
        return "signature mismatch", 403


@app.route("/wecom/callback", methods=["POST"])
def receive():
    """接收企业微信消息"""
    try:
        xml_content = request.data.decode("utf-8")
        root = ET.fromstring(xml_content)
        msg_type = root.find("MsgType").text

        if msg_type != "text":
            return "success"

        from_user = root.find("FromUserName").text
        content = root.find("Content").text.strip()

        if not content:
            return "success"

        print(f"[收到] {from_user}: {content}")

        # 获取用户对话历史
        ai = get_ai()
        if from_user not in user_histories:
            user_histories[from_user] = []

        original_history = ai.history
        ai.history = user_histories[from_user]

        reply = ai.chat(content)
        print(f"[回复] {reply}")

        user_histories[from_user] = ai.history[-ai.history_length * 2:]
        ai.history = original_history

        send_message(from_user, reply)
        return "success"

    except Exception as e:
        print(f"[错误] {e}")
        import traceback
        traceback.print_exc()
        return "success"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"启动于端口 {port}")
    app.run(host="0.0.0.0", port=port)
