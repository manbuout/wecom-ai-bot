"""
个人智能 AI 聊天机器人 - 命令行入口

用法:
    python main.py parse                    # 解析聊天记录，生成人设
    python main.py chat                     # 命令行对话测试
    python main.py wechat                   # 启动企业微信 Bot
"""

import sys
import os

# 确保在项目目录下运行
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml


def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def cmd_parse():
    """解析聊天记录并生成人设"""
    config = load_config()
    qq_dir = config.get("chat_records", {}).get("qq_dir")
    wechat_dir = config.get("chat_records", {}).get("wechat_dir")
    output_path = config["persona"]["profile_path"]

    from chatparser.chat_parser import parse_and_generate

    print("=" * 50)
    print("聊天记录解析器")
    print("=" * 50)

    persona = parse_and_generate(
        qq_dir=qq_dir,
        wechat_dir=wechat_dir,
        output_path=output_path,
    )

    if persona:
        print(f"\n请检查生成的人设文件: {output_path}")
        print("确认无误后运行 'python main.py chat' 测试效果")


def cmd_chat():
    """命令行对话测试"""
    config = load_config()

    from aicore.service import AIService

    print("=" * 50)
    print("对话测试模式")
    print("=" * 50)

    ai = AIService()
    print(f"人设: {ai.persona_name}")
    print("输入 'quit' 退出，'reset' 清空历史")
    print("-" * 50)

    while True:
        try:
            user_input = input("你: ").strip()
            if not user_input:
                continue
            if user_input.lower() == "quit":
                break
            if user_input.lower() == "reset":
                ai.reset_history()
                print("[已清空对话历史]")
                continue

            reply = ai.chat(user_input)
            print(f"{ai.persona_name}: {reply}")
            print()

        except KeyboardInterrupt:
            break

    print("\n再见！")


def cmd_wechat():
    """启动企业微信 Bot"""
    config = load_config()

    if not config.get("wechat", {}).get("enabled", False):
        print("[提示] 微信 Bot 未启用，请先在 config.yaml 中设置 wechat.enabled: true")
        return

    # 使用启动器（含隧道）
    import subprocess
    subprocess.run([sys.executable, "start_bot.py"])


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1].lower()

    if cmd == "parse":
        cmd_parse()
    elif cmd == "chat":
        cmd_chat()
    elif cmd == "wechat":
        cmd_wechat()
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
