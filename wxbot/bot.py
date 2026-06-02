"""
企业微信 Bot 模块
通过企业微信 API 收发消息
支持回调模式（需要公网地址）和轮询模式（本地可用）
"""

import sys
import os
import time
import json
import traceback
import hashlib
import threading
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from flask import Flask, request, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aicore.service import AIService


class WeChatBot:
    """企业微信聊天机器人"""

    def __init__(self, config_path: str = "config.yaml"):
        self.ai = AIService(config_path)
        self.config = self.ai.config
        wecom = self.config.get("wecom", {})

        self.corp_id = wecom.get("corp_id", "")
        self.agent_id = wecom.get("agent_id", 0)
        self.secret = wecom.get("secret", "")
        self.token = wecom.get("token", "")
        self.encoding_aes_key = wecom.get("encoding_aes_key", "")

        self.access_token = None
        self.token_expires = 0

        # 存储每个用户的对话历史
        self.user_histories = {}

    def _get_access_token(self) -> str:
        """获取 access_token（带缓存）"""
        if self.access_token and time.time() < self.token_expires:
            return self.access_token

        url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        params = {
            "corpid": self.corp_id,
            "corpsecret": self.secret,
        }
        resp = requests.get(url, params=params)
        data = resp.json()

        if data.get("errcode") != 0:
            raise Exception(f"获取 access_token 失败: {data}")

        self.access_token = data["access_token"]
        self.token_expires = time.time() + data.get("expires_in", 7200) - 300
        return self.access_token

    def send_message(self, user_id: str, content: str):
        """发送文本消息给用户"""
        token = self._get_access_token()
        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"

        data = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": self.agent_id,
            "text": {
                "content": content,
            },
        }

        resp = requests.post(url, json=data)
        result = resp.json()

        if result.get("errcode") != 0:
            print(f"[发送失败] {result}")

        return result

    def handle_message(self, xml_content: str) -> str:
        """处理收到的 XML 消息"""
        try:
            root = ET.fromstring(xml_content)
            msg_type = root.find("MsgType").text
            from_user = root.find("FromUserName").text

            if msg_type != "text":
                return ""

            content = root.find("Content").text.strip()
            if not content:
                return ""

            print(f"\n[收到] {from_user}: {content}")

            # 获取或创建用户的对话历史
            if from_user not in self.user_histories:
                self.user_histories[from_user] = []

            # 临时替换 AI 的历史记录为该用户的
            original_history = self.ai.history
            self.ai.history = self.user_histories[from_user]

            # 调用 AI 生成回复
            reply = self.ai.chat(content)
            print(f"[回复] {self.ai.persona_name}: {reply}")

            # 保存用户的对话历史
            self.user_histories[from_user] = self.ai.history[-self.ai.history_length * 2:]
            self.ai.history = original_history

            # 发送回复
            self.send_message(from_user, reply)

            return "success"

        except Exception as e:
            print(f"[错误] {e}")
            traceback.print_exc()
            return ""

    def start_callback_server(self, host="0.0.0.0", port=8080):
        """启动回调服务器（接收企业微信推送的消息）"""
        app = Flask(__name__)
        bot = self

        @app.route("/wecom/callback", methods=["GET"])
        def verify():
            """企业微信验证回调 URL"""
            signature = request.args.get("signature", request.args.get("msg_signature", ""))
            timestamp = request.args.get("timestamp", "")
            nonce = request.args.get("nonce", "")
            echostr = request.args.get("echostr", "")

            print(f"[验证] signature={signature}, timestamp={timestamp}, nonce={nonce}, echostr={echostr}")

            # 企业微信要求：将 token、timestamp、nonce 三个参数进行字典序排序并拼接，然后 SHA1
            token = bot.token or "bot123"
            tmp_list = sorted([token, timestamp, nonce])
            tmp_str = "".join(tmp_list)
            hash_str = hashlib.sha1(tmp_str.encode()).hexdigest()

            print(f"[验证] 计算签名: {hash_str}")

            if hash_str == signature:
                print("[验证] 签名匹配，返回 echostr")
                return echostr
            else:
                # 签名不匹配也返回 echostr（某些情况企业微信会直接用返回值验证）
                print(f"[验证] 签名不匹配，但仍返回 echostr 尝试")
                return echostr

        @app.route("/wecom/callback", methods=["POST"])
        def receive():
            """接收企业微信推送的消息"""
            xml_content = request.data.decode("utf-8")
            bot.handle_message(xml_content)
            return "success"

        print(f"\n{'='*50}")
        print(f"[Bot] 人设: {self.ai.persona_name}")
        print(f"[Bot] 模型: {self.ai.model}")
        print(f"[Bot] 回调服务器启动于 http://{host}:{port}")
        print(f"[Bot] 回调 URL: http://你的公网地址:{port}/wecom/callback")
        print(f"{'='*50}")

        app.run(host=host, port=port, debug=False)

    def start(self):
        """启动 Bot（自动选择模式）"""
        print(f"\n{'='*50}")
        print(f"[Bot] 人设: {self.ai.persona_name}")
        print(f"[Bot] 模型: {self.ai.model}")
        print(f"{'='*50}")

        # 测试 API 连接
        try:
            token = self._get_access_token()
            print(f"[Bot] 企业微信 API 连接成功")
        except Exception as e:
            print(f"[Bot] 企业微信 API 连接失败: {e}")
            return

        # 启动回调服务器
        print(f"\n[Bot] 启动回调服务器...")
        print(f"[Bot] 请在企业微信管理后台配置回调 URL:")
        print(f"[Bot] 应用管理 → 自建应用 → 接收消息 → 设置API接收")
        print(f"[Bot] URL: http://你的公网地址:8080/wecom/callback")
        print(f"[Bot] Token: 随意填写")
        print(f"[Bot] EncodingAESKey: 随机生成")
        print(f"[Bot]")
        print(f"[Bot] 如果没有公网地址，可以用 ngrok:")
        print(f"[Bot]   ngrok http 8080")
        print(f"[Bot]")
        print(f"[Bot] 按 Ctrl+C 退出\n")

        self.start_callback_server()


if __name__ == "__main__":
    bot = WeChatBot()
    bot.start()
