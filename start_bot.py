"""
一键启动企业微信 Bot
1. 启动 Flask 回调服务器（后台线程）
2. 启动 SSH 隧道（serveo.net）
3. 显示回调 URL 配置信息
"""

import sys
import os
import time
import subprocess
import threading
import re

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PORT = 8080


def start_flask_server(bot):
    """在后台线程启动 Flask 服务器"""
    bot.start_callback_server(port=PORT)


def start_tunnel():
    """启动 serveo.net SSH 隧道，返回公网 URL"""
    print("[隧道] 正在启动 serveo.net 隧道...")
    proc = subprocess.Popen(
        ["ssh", "-o", "StrictHostKeyChecking=no", "-R", f"80:localhost:{PORT}", "serveo.net"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    url = None
    for line in iter(proc.stdout.readline, ""):
        line = line.strip()
        # 提取 Forwarding URL
        match = re.search(r"(https://[\w.-]+\.serveousercontent\.com)", line)
        if match:
            url = match.group(1)
            callback_url = f"{url}/wecom/callback"
            print(f"\n{'='*60}")
            print(f"[隧道] 公网地址: {url}")
            print(f"[隧道] 回调 URL: {callback_url}")
            print(f"{'='*60}")
            print(f"\n[配置] 请在企业微信管理后台配置:")
            print(f"  1. 应用管理 → 自建应用 → 接收消息")
            print(f"  2. 点击「设置API接收」")
            print(f"  3. 填写:")
            print(f"     URL: {callback_url}")
            print(f"     Token: bot123（随意填写）")
            print(f"     EncodingAESKey: 点「随机生成」")
            print(f"  4. 点「保存」")
            print(f"\n[提示] 配置完成后，在企业微信里给应用发消息就能收到回复！")
            print(f"[提示] 按 Ctrl+C 退出\n")
            break

    return proc, url


def main():
    print("=" * 60)
    print("  企业微信 AI Bot - 启动器")
    print("=" * 60)
    print()

    # 初始化 Bot
    from wxbot.bot import WeChatBot
    bot = WeChatBot()

    # 测试 API 连接
    try:
        bot._get_access_token()
        print("[Bot] 企业微信 API 连接成功")
    except Exception as e:
        print(f"[Bot] 企业微信 API 连接失败: {e}")
        return

    # 启动 Flask 服务器（后台线程）
    flask_thread = threading.Thread(target=start_flask_server, args=(bot,), daemon=True)
    flask_thread.start()
    time.sleep(1)  # 等 Flask 启动

    # 启动隧道
    tunnel_proc, tunnel_url = start_tunnel()

    if not tunnel_url:
        print("[错误] 无法获取隧道 URL")
        return

    # 保持运行
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[退出] 正在关闭...")
        tunnel_proc.terminate()


if __name__ == "__main__":
    main()
