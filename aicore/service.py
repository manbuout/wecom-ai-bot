"""
AI 服务模块
使用小米 MiMo API（Anthropic 兼容格式）
"""

import os
import yaml
import anthropic


def load_config(config_path: str = "config.yaml") -> dict:
    """加载配置文件"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_persona(profile_path: str) -> dict:
    """加载人设文件"""
    with open(profile_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_system_prompt(persona: dict) -> str:
    """从人设数据构建 System Prompt"""
    name = persona["name"]
    style = persona.get("style", [])
    examples = persona.get("examples", [])

    prompt = f"""你是 {name}，现在正在和用户聊天。你要完全模仿这个人的说话方式、语气、用词习惯来回复。

## 你的说话风格特征：
"""
    for s in style:
        prompt += f"- {s}\n"

    prompt += f"""
## 重要规则：
1. 你就是 {name}，不是 AI，不是助手，不要暴露自己是 AI
2. 严格按照上面的说话风格回复，不要用正式、书面的语气
3. 回复要自然、简短，像日常聊天一样
4. 不要用"作为xxx"、"我很乐意"、"当然可以"这类 AI 味很重的表达
5. 如果对方说的话你不知道怎么回，就用 {name} 的方式敷衍或转移话题
6. 可以用表情符号，但不要用太多
7. 学习下面对话示例中的用词、句式、语气，尽量贴近

## 你和用户的真实对话示例（严格模仿这个风格）：
"""

    # 从各阶段均匀取示例
    selected_examples = []
    phase_groups = {}
    for ex in examples:
        phase = ex.get("phase", "")
        if phase not in phase_groups:
            phase_groups[phase] = []
        phase_groups[phase].append(ex)

    # 每个阶段取最多3条
    for phase, group in phase_groups.items():
        for ex in group[:3]:
            selected_examples.append(ex)

    for ex in selected_examples[:20]:
        dialogue = ex.get("dialogue", "")
        if dialogue:
            prompt += f"{dialogue}\n\n---\n\n"

    return prompt


class AIService:
    """AI 聊天服务"""

    def __init__(self, config_path: str = "config.yaml"):
        # 尝试加载配置文件，如果不存在则用环境变量
        try:
            self.config = load_config(config_path)
        except FileNotFoundError:
            self.config = {}

        ai_config = self.config.get("ai", {})

        self.client = anthropic.Anthropic(
            api_key=os.environ.get("AI_API_KEY", ai_config.get("api_key", "")),
            base_url=os.environ.get("AI_BASE_URL", ai_config.get("base_url", "")),
        )
        self.model = os.environ.get("AI_MODEL", ai_config.get("model", ""))
        self.temperature = ai_config.get("temperature", 0.7)
        self.max_tokens = ai_config.get("max_tokens", 2048)

        # 加载人设
        persona_path = self.config.get("persona", {}).get("profile_path", "profiles/pig头.yaml")
        persona = load_persona(persona_path)
        self.system_prompt = build_system_prompt(persona)
        self.persona_name = persona["name"]

        # 对话历史
        self.history_length = self.config.get("persona", {}).get("history_length", 20)
        self.history = []

    def chat(self, user_message: str) -> str:
        """发送消息并获取回复"""
        # 构建消息列表（Anthropic 格式）
        messages = []

        # 添加历史对话
        for msg in self.history[-self.history_length:]:
            messages.append(msg)

        # 添加当前用户消息
        messages.append({"role": "user", "content": user_message})

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=self.system_prompt,
                messages=messages,
            )
            reply = response.content[0].text.strip()

            # 保存对话历史
            self.history.append({"role": "user", "content": user_message})
            self.history.append({"role": "assistant", "content": reply})

            return reply

        except Exception as e:
            return f"[AI 错误] {e}"

    def reset_history(self):
        """清空对话历史"""
        self.history = []
