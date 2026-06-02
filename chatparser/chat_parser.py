"""
聊天记录解析器
支持 QQ 和微信的 HTML 格式聊天记录导出
按时间阶段分组提取人设示例
"""

import re
import json
import os
from collections import Counter, defaultdict
from bs4 import BeautifulSoup


def parse_qq(html_path: str) -> list[dict]:
    """解析 QQ 聊天记录 HTML 文件"""
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "lxml")

    messages = []
    for msg_div in soup.find_all("div", class_="message"):
        is_self = "self" in msg_div.get("class", [])
        sender_tag = msg_div.find("span", class_="sender")
        time_tag = msg_div.find("span", class_="time")
        text_tag = msg_div.find("span", class_="text-content")

        if not text_tag:
            continue

        sender = sender_tag.get_text(strip=True) if sender_tag else ("我" if is_self else "对方")
        time_str = time_tag.get_text(strip=True) if time_tag else ""
        text = text_tag.get_text(strip=True)

        if text and text != "你撤回了一条消息":
            messages.append({
                "sender": sender,
                "time": time_str,
                "text": text,
                "is_self": is_self,
            })

    return messages


def parse_wechat(html_path: str) -> list[dict]:
    """解析微信聊天记录 HTML 文件（WeFlow 导出格式）"""
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    match = re.search(r"window\.WEFLOW_DATA\s*=\s*(\[.*?\]);", content, re.DOTALL)
    if not match:
        raise ValueError("无法找到 WEFLOW_DATA，请确认是 WeFlow 导出的微信聊天记录")

    data = json.loads(match.group(1))
    messages = []

    for item in data:
        is_self = item.get("s", 0) == 1
        body_html = item.get("b", "")

        avatar_html = item.get("a", "")
        alt_match = re.search(r'alt="([^"]*)"', avatar_html)
        sender = alt_match.group(1) if alt_match else ("我" if is_self else "对方")

        time_match = re.search(r'<div class="message-time">(.*?)</div>', body_html)
        time_str = time_match.group(1) if time_match else ""

        text_match = re.search(r'<div class="message-text">(.*?)</div>', body_html, re.DOTALL)
        if text_match:
            text = text_match.group(1).strip()
            text = re.sub(r'<[^>]+>', '', text)
            if text and text != "[表情包]" and "撤回了一条消息" not in text:
                messages.append({
                    "sender": sender,
                    "time": time_str,
                    "text": text,
                    "is_self": is_self,
                })

    return messages


def is_valid_text(t: str) -> bool:
    """过滤系统消息和无意义内容"""
    skip_patterns = [
        "撤回了一条消息", "你已添加了", "现在可以开始聊天了",
        "[转发的聊天记录]", "[链接]", "[文件]", "[语音消息]",
        "系统提示", "[object Object]", "[自动回复]",
        "吃美食 分享赚现金", "mp://",
    ]
    return len(t) > 1 and not any(p in t for p in skip_patterns)


def normalize_time(time_str: str) -> str:
    """统一时间格式为 YYYY-MM-DD HH:MM:SS"""
    # QQ 格式: 2023/11/04 08:45:50
    time_str = time_str.replace("/", "-")
    return time_str


def get_phase(time_str: str) -> str:
    """根据时间判断属于哪个阶段"""
    if not time_str:
        return "未知"

    # 提取 YYYY-MM-DD
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', time_str)
    if not m:
        return "未知"

    ymd = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    ym = f"{m.group(1)}-{m.group(2)}"

    # 7月出游期间单独标记
    if ymd in JULY_OUTING_DATES:
        return "3.热聊期-7月出游"

    phases = {
        "1.初识期": ["2023-11", "2023-12"],
        "2.磨合期": ["2024-01", "2024-02", "2024-03"],
        "3.热聊期": ["2024-04", "2024-05", "2024-06"],
        "4.降温期": ["2024-07", "2024-08"],
        "5.沉默期": ["2024-09", "2024-10", "2024-11", "2024-12"],
        "6.后续":   ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05",
                     "2025-06", "2025-07", "2025-08", "2025-09", "2025-10",
                     "2025-11", "2025-12", "2026-01", "2026-02", "2026-03"],
    }

    # 7月非出游期间归入降温期
    if ym == "2024-07":
        return "4.降温期"

    for phase, months in phases.items():
        if ym in months:
            return phase
    return "未知"


# 每个阶段取多少条详细示例
PHASE_EXAMPLE_COUNT = {
    "1.初识期": 8,
    "2.磨合期": 18,
    "3.热聊期": 18,
    "3.热聊期-7月出游": 15,
    "4.降温期": 6,
    "5.沉默期": 3,
    "6.后续":   4,
}

# 7月出游的特殊时间范围
JULY_OUTING_DATES = ["2024-07-10", "2024-07-11", "2024-07-12", "2024-07-13",
                     "2024-07-14", "2024-07-15", "2024-07-16", "2024-07-17",
                     "2024-07-18", "2024-07-19", "2024-07-20", "2024-07-21",
                     "2024-07-22", "2024-07-23", "2024-07-24", "2024-07-25"]


def extract_detailed_conversations(messages: list[dict], max_turns: int = 6) -> list[dict]:
    """
    提取连续多轮对话（而不是单条 pair）
    返回: [{"turns": [{"role": "user"/"other", "text": "..."}, ...], "phase": "...", "time": "..."}]
    """
    conversations = []
    current_conv = []

    for i, msg in enumerate(messages):
        if not is_valid_text(msg["text"]):
            continue

        role = "self" if msg["is_self"] else "other"

        # 如果是连续同一个角色说话，合并
        if current_conv and current_conv[-1]["role"] == role:
            current_conv[-1]["text"] += "\n" + msg["text"]
        else:
            current_conv.append({"role": role, "text": msg["text"]})

        # 检查是否应该结束这段对话
        # 条件：达到 max_turns*2 条，或者出现明显间隔
        if len(current_conv) >= max_turns * 2:
            if len(current_conv) >= 2:
                phase = get_phase(msg["time"])
                conversations.append({
                    "turns": current_conv[:],
                    "phase": phase,
                    "time": msg["time"],
                })
            current_conv = []

    # 收尾
    if len(current_conv) >= 2:
        phase = get_phase(messages[-1]["time"]) if messages else "未知"
        conversations.append({
            "turns": current_conv,
            "phase": phase,
            "time": messages[-1]["time"] if messages else "",
        })

    return conversations


def score_conversation(conv: dict) -> float:
    """给对话打分，越高越有代表性"""
    score = 0
    turns = conv["turns"]

    # 有来有回加分（轮次多）
    score += len(turns) * 0.5

    # 对方回复有内容加分（不只是"嗯"、"哦"）
    for t in turns:
        if t["role"] == "other" and len(t["text"]) > 5:
            score += 1
        # 包含情感表达加分
        if t["role"] == "other" and any(w in t["text"] for w in ["哈哈", "嘻嘻", "嘿嘿", "呜呜", "呜", "啊", "嘛", "呢", "吧"]):
            score += 0.5

    # 对话总字数适中加分（太短没内容，太长可能是刷屏）
    total_chars = sum(len(t["text"]) for t in turns)
    if 20 < total_chars < 500:
        score += 2

    return score


def select_phase_examples(conversations: list[dict], phase: str, count: int) -> list[dict]:
    """
    从某个阶段中选取高质量示例
    count=-1 表示全部提取（用于7月出游等特殊阶段）
    """
    phase_convs = [c for c in conversations if c["phase"] == phase]

    if not phase_convs:
        return []

    # 打分排序
    scored = [(score_conversation(c), c) for c in phase_convs]
    scored.sort(key=lambda x: -x[0])

    # 7月出游：全部提取，按时间排序
    if "7月出游" in phase:
        # 按时间排序后全部返回
        phase_convs.sort(key=lambda c: c["time"])
        return phase_convs[:count] if count > 0 else phase_convs

    # 其他阶段：从 top 中均匀采样
    top_pool = scored[:len(scored) * 3 // 4]  # 取前3/4
    if len(top_pool) <= count:
        return [c for _, c in top_pool]

    step = max(1, len(top_pool) // count)
    selected = [top_pool[i][1] for i in range(0, len(top_pool), step)][:count]
    return selected


def extract_persona(messages: list[dict], target_name: str = None) -> dict:
    """
    从消息列表中提取某人的说话风格，按阶段分组
    """
    if target_name:
        target_msgs = [m for m in messages if m["sender"] == target_name]
    else:
        target_msgs = [m for m in messages if not m["is_self"]]

    if not target_msgs:
        raise ValueError(f"找不到目标消息，target_name={target_name}")

    name = target_msgs[0]["sender"]
    valid_texts = [m["text"] for m in target_msgs if is_valid_text(m["text"])]
    total_chars = sum(len(t) for t in valid_texts)
    avg_len = total_chars / len(valid_texts) if valid_texts else 0

    # 高频词统计（2-gram）
    bigrams = []
    for text in valid_texts:
        clean = re.sub(r'[^一-鿿]', '', text)
        for i in range(len(clean) - 1):
            bigrams.append(clean[i:i+2])
    bigram_freq = Counter(bigrams).most_common(30)

    # 语气词/口头禅统计
    filler_patterns = [
        (r'哈+', '哈'), (r'嘻+', '嘻'), (r'嘿+', '嘿'), (r'呜+', '呜'),
        (r'嗯+', '嗯'), (r'哦+', '哦'), (r'噢+', '噢'), (r'额+', '额'),
        (r'呃+', '呃'), (r'啊+', '啊'), (r'哇+', '哇'), (r'em+', 'em'),
    ]
    filler_counter = Counter()
    for text in valid_texts:
        for pattern, label in filler_patterns:
            if re.search(pattern, text):
                filler_counter[label] += 1
    filler_freq = filler_counter.most_common(10)

    # 句式特征统计
    ending_counter = Counter()
    for text in valid_texts:
        if text.endswith("~") or text.endswith("～"):
            ending_counter["波浪号结尾"] += 1
        if text.endswith("！") or text.endswith("!"):
            ending_counter["感叹号结尾"] += 1
        if text.endswith("？") or text.endswith("?"):
            ending_counter["问号结尾"] += 1
        if re.search(r'[。\.]{2,}', text):
            ending_counter["省略号"] += 1
    ending_freq = ending_counter.most_common(10)

    # 消息长度分布
    len_dist = {"1-5字": 0, "6-15字": 0, "16-30字": 0, "30字以上": 0}
    for text in valid_texts:
        l = len(text)
        if l <= 5:
            len_dist["1-5字"] += 1
        elif l <= 15:
            len_dist["6-15字"] += 1
        elif l <= 30:
            len_dist["16-30字"] += 1
        else:
            len_dist["30字以上"] += 1

    # 按阶段统计消息量
    phase_stats = defaultdict(int)
    for m in target_msgs:
        phase = get_phase(m["time"])
        phase_stats[phase] += 1

    # 提取详细多轮对话
    print("  -> 提取多轮对话...")
    conversations = extract_detailed_conversations(messages, max_turns=8)

    # 按阶段选取示例
    all_examples = []
    for phase, count in PHASE_EXAMPLE_COUNT.items():
        selected = select_phase_examples(conversations, phase, count)
        for conv in selected:
            # 转换为 user/other 格式
            turns_text = []
            for t in conv["turns"]:
                role = "我" if t["role"] == "self" else name
                turns_text.append(f"{role}：{t['text']}")
            all_examples.append({
                "phase": phase,
                "time": conv["time"],
                "dialogue": "\n".join(turns_text),
            })
        candidate_count = len([c for c in conversations if c["phase"] == phase])
        print(f"  -> {phase}: 取 {len(selected)} 条（共 {candidate_count} 条候选）")

    return {
        "name": name,
        "style": {
            "avg_length": round(avg_len, 1),
            "total_messages": len(target_msgs),
            "valid_messages": len(valid_texts),
            "length_dist": len_dist,
            "top_words": bigram_freq[:15],
            "filler_words": filler_freq,
            "sentence_endings": ending_freq,
            "phase_stats": dict(phase_stats),
        },
        "examples": all_examples,
    }


def generate_persona_yaml(persona_data: dict, output_path: str):
    """从分析结果生成人设 YAML 文件"""
    import yaml

    name = persona_data["name"]
    style = persona_data["style"]
    examples = persona_data["examples"]

    # 构建风格描述
    style_desc = []
    style_desc.append(f"平均回复长度 {style['avg_length']} 字，偏{'简短' if style['avg_length'] < 15 else '详细'}")

    if style["length_dist"]:
        dist = style["length_dist"]
        main_len = max(dist, key=dist.get)
        style_desc.append(f"消息长度以{main_len}为主")

    if style["top_words"]:
        top = ", ".join([w for w, c in style["top_words"][:8]])
        style_desc.append(f"常用词：{top}")

    if style["filler_words"]:
        fillers = ", ".join([f"{w}({c}次)" for w, c in style["filler_words"][:6]])
        style_desc.append(f"语气词/口头禅：{fillers}")

    for ending, count in style.get("sentence_endings", []):
        if count > 10:
            style_desc.append(f"经常{ending}（{count}次）")

    # 构建 YAML 数据
    persona = {
        "name": name,
        "style": style_desc,
        "examples": examples,
        "stats": {
            "total_messages": style["total_messages"],
            "valid_messages": style["valid_messages"],
            "avg_length": style["avg_length"],
            "length_dist": style["length_dist"],
            "phase_stats": style["phase_stats"],
        },
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(persona, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return persona


def parse_and_generate(qq_dir: str = None, wechat_dir: str = None,
                       target_name: str = None, output_path: str = "profiles/persona.yaml"):
    """主函数：解析聊天记录并生成人设"""
    all_messages = []

    if qq_dir and os.path.exists(qq_dir):
        for f in os.listdir(qq_dir):
            if f.endswith(".html"):
                path = os.path.join(qq_dir, f)
                print(f"[解析] QQ: {f}")
                msgs = parse_qq(path)
                all_messages.extend(msgs)
                print(f"  -> 解析到 {len(msgs)} 条消息")

    if wechat_dir and os.path.exists(wechat_dir):
        texts_dir = os.path.join(wechat_dir, "texts")
        if os.path.exists(texts_dir):
            for f in os.listdir(texts_dir):
                if f.endswith(".html"):
                    path = os.path.join(texts_dir, f)
                    print(f"[解析] 微信: {f}")
                    msgs = parse_wechat(path)
                    all_messages.extend(msgs)
                    print(f"  -> 解析到 {len(msgs)} 条消息")

    if not all_messages:
        print("[错误] 没有解析到任何消息")
        return None

    # 统一时间格式
    for m in all_messages:
        m["time"] = normalize_time(m["time"])

    print(f"\n[统计] 共 {len(all_messages)} 条消息")
    print(f"[分析] 正在提取说话风格（按阶段分组）...")
    persona = extract_persona(all_messages, target_name)

    print(f"[生成] 人设文件 -> {output_path}")
    generate_persona_yaml(persona, output_path)

    style = persona["style"]
    print(f"\n{'='*50}")
    print(f"人设生成完成！")
    print(f"名字：{persona['name']}")
    print(f"消息总数：{style['total_messages']}（有效：{style['valid_messages']}）")
    print(f"平均回复长度：{style['avg_length']} 字")
    print(f"长度分布：{style['length_dist']}")
    print(f"阶段分布：{style['phase_stats']}")
    print(f"示例对话：{len(persona['examples'])} 条")
    print(f"文件位置：{output_path}")
    print(f"{'='*50}")

    return persona
