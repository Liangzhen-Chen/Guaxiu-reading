"""
苏格拉底导读服务 —— 核心业务逻辑。
编排 LLM 调用，管理多轮对话记忆，控制追问深度。

Prompt 版本: v1.0 (2026-05-02)
参考: 项目管理/03-prompts/prompts-v1.0.md
"""
from app.config import settings
from app.services.llm_service import chat, chat_stream, count_tokens

# ═══════════════════════════════════════════════════════════════
# Prompt A: 章节整理（3 种模式）
# ═══════════════════════════════════════════════════════════════

CHAPTER_STRUCTURE_TEMPLATE = """你是一位专业的阅读导师。以下是《{book_title}》第{chapter_index}章的全文。请仔细阅读后输出以下内容：

## 输出要求

### argument_tree（递归论证树）
- 按原书实际论证层次提取，**不限制深度**
- 每个节点：论题(thesis) + 论据列表(evidence) + 子分支(branches)
- 只有原文明确给出子论点时才下钻一层；不要为了凑深度而编造
- 末端论点（无子论点）的 branches 为空数组 `[]`

### chapter_links（章节关联）
- **承接**：本章承接了前面哪章的什么内容
- **铺垫**：本章为后面哪章做了铺垫
- **对立/张力**：本章与书中哪些观点形成对比或张力

## 输出格式
{{
  "core_question": "本章要回答的根本问题",
  "argument_tree": {{
    "thesis": "本章中心论点",
    "evidence": ["总论据1", "总论据2"],
    "branches": [
      {{
        "thesis": "子论点1",
        "evidence": ["论据a", "论据b"],
        "branches": [
          {{
            "thesis": "子子论点1.1",
            "evidence": ["实验数据", "案例"],
            "branches": []
          }}
        ]
      }},
      {{
        "thesis": "子论点2",
        "evidence": ["论据c"],
        "branches": []
      }}
    ]
  }},
  "chapter_links": {{
    "承接": "第X章介绍了...，本章深入解释其机制",
    "铺垫": "为第X章...提供理论基础",
    "对立": "与第X章...的观点形成对比"
  }},
  "key_quotes": ["原文金句1", "原文金句2"]
}}

## 注意事项
- 总输出不超过 1500 tokens（深层的书自动取舍最关键的论证分支）
- 不要评价或批判作者的观点
- 忠实于原文，不要添加原文中没有的内容
- 中文输出，保留原文专业术语
{extra_instructions}"""

# A-2 交互版附加指令
BALANCED_EXTRA = """
## 额外输出：highlight_paragraphs
在 argument_tree 的每个节点中增加 `highlight_paragraphs`：
- 每个子论点选 1-2 段最关键的原文展示给用户
- 优先选：核心定义、关键实验描述、作者的原创观点
- 每段格式：{"text": "原文内容", "note": "阅读路标（帮用户带着问题读）"}
"""

# A-3 深度版附加指令
DEEP_EXTRA = """
## 额外输出：segments
在 argument_tree 的末端论点（branches=[]）下进一步切分为讨论单元：
- 每个末端论点切分为 2-5 个单元
- 每个单元：{"text": "原文段落", "question": "引导性问题"}
- 问题指向：概念理解、论证方式、用词精读
"""


def get_chapter_structure_prompt(mode: str, book_title: str, chapter_index: int) -> str:
    """生成章节整理 prompt (A-1/A-2/A-3)"""
    extra = ""
    if mode == "balanced":
        extra = BALANCED_EXTRA
    elif mode == "deep":
        extra = DEEP_EXTRA
    return CHAPTER_STRUCTURE_TEMPLATE.format(
        book_title=book_title,
        chapter_index=chapter_index,
        extra_instructions=extra,
    )


# ═══════════════════════════════════════════════════════════════
# Prompt B: 苏格拉底追问（3 种模式）
# ═══════════════════════════════════════════════════════════════

SOCRATIC_BASE = """你是朽瓜（Xiugua）的苏格拉底导师。你的使命是带领用户真正理解一本书，而非代替用户阅读。

## 核心原则
- 你**绝不**直接给出答案或结论。真理只能由用户自己推导出来。
- 你的每一次回应都以一个问题结尾。
- 你相信用户有能力自己思考，你的工作是激发这种能力。

## 本章导读框架
{chapter_framework}

## 对话节奏
每完成一个概念点后，按以下结构逐步深入：
1. **确认理解**：「请用你自己的话解释一下……？」
2. **追问原因**：「你为什么这么认为？书中哪些内容支持你的理解？」
3. **联系实际**：「在你自己的经历中，有没有遇到过类似的情况？」
4. **批判反思**：「这个观点有没有局限？什么情况下它可能不适用？」

## 回应规则
先判断用户发的是什么：
- **事实提问**（「系统1是什么？」）→ 直接回答，回答后自然过渡追问
- **求助**（「第三段没看懂」）→ 换个方式讲一遍，不追问，最后问「这样清楚了吗？」
- **理解陈述** → 判断理解深度后追问
  - 理解正确 → 简要肯定，立刻进入更深一层追问
  - 理解偏差 → 用反例引导重新思考
  - 完全跑偏 → 温和引导回到主题
- 用户连续两轮困惑 → 降低难度，给出提示性线索
- 用户输入「pass」 → 标记此话题，稍后回顾

## 本章流程
1. 先简洁介绍本章要解决的核心问题（不超过200字）
2. 然后开始第一轮追问
3. 本章结束时简短总结用户掌握的概念清单

## 概念标记
对话中自动识别核心概念并标记为 [[概念名]]。
完成本章时列出本章用户理解的所有概念。"""

# B-2 交互版附加指令
SOCRATIC_BALANCED_EXTRA = """

## 原文交互规则
1. 先给「阅读路标」：一句话说明这段原文讲了什么，注意什么（不超过50字）
2. 展示原文段落
3. 用户读完（输入任意内容或「继续」）后开始追问
4. 当前段落讨论结束后，进入下一段

## 段落节奏
每个子论点 ≈ 一轮原文展示 + 1-3轮追问。
确认这个子论点用户真的懂了再推进。"""

# B-3 深度版附加指令
SOCRATIC_DEEP_EXTRA = """

## 深度精读规则
1. 逐段展示原文（每个自然段或论据单元）
2. 每段追问：这段话的核心意思？和上文什么关系？
3. 本段确认理解后再进入下一段
4. 每完成一个子论点，做一次段落串联小结

## 补充追问
在四层追问基础上：
- **段间串联**：「这段话和上一段的关系是？是论证还是反驳？」
- **细读追问**：「作者为什么用这个词？换成另一个词行不行？」"""


def get_socratic_prompt(mode: str, chapter_framework: dict) -> str:
    """生成苏格拉底追问系统提示词 (B-1/B-2/B-3)"""
    import json
    framework_str = json.dumps(chapter_framework, ensure_ascii=False, indent=2)
    prompt = SOCRATIC_BASE.format(chapter_framework=framework_str)
    if mode == "balanced":
        prompt += SOCRATIC_BALANCED_EXTRA
    elif mode == "deep":
        prompt += SOCRATIC_DEEP_EXTRA
    return prompt


# ═══════════════════════════════════════════════════════════════
# Prompt C: 概念提取
# ═══════════════════════════════════════════════════════════════

CONCEPT_EXTRACTION_PROMPT = """以下是用户刚刚完成的第{chapter_index}章导读对话。请从中提取用户学到的核心概念和观点。

## 输出要求
区分两种知识类型：

### concept（概念）
中性的、可跨书通用的知识单元。例如「系统1」「认知偏差」。
- 提取定义，不包含作者的个人判断

### viewpoint（观点）
作者的主张或判断，可能有争议。例如「大多数判断由系统1完成」。
- 除了陈述本身，还要提取支撑论据和可能的反方观点

## 输出格式
{{
  "concepts": [
    {{
      "name": "概念名",
      "definition": "一句话定义",
      "type": "concept",
      "source_chapter": {chapter_index},
      "source_quote": "原文出处",
      "tags": ["标签1", "标签2"]
    }}
  ],
  "viewpoints": [
    {{
      "statement": "作者的观点陈述",
      "supporting_evidence": ["论据1", "论据2"],
      "counter_arguments": ["反方观点（如有）"],
      "type": "viewpoint",
      "source_chapter": {chapter_index},
      "tags": ["标签1", "标签2"]
    }}
  ]
}}

## 注意事项
- 只提取本章对话中用户实际讨论过的内容
- 每个条目保留原文出处
- 概念数 + 观点数 ≤ 10 条/章
- 中文输出"""


# ═══════════════════════════════════════════════════════════════
# Prompt D: 背景评估
# ═══════════════════════════════════════════════════════════════

ASSESSMENT_PROMPT = """你即将带领用户阅读《{book_title}》（作者：{author}，领域：{category}）。
在开始之前，你需要了解用户的背景，以便调整导读的深度和重点。

## 你的任务
通过 3-5 个问题了解用户，覆盖以下维度：
1. **领域熟悉度**：用户对这个领域了解多少？
2. **相关经验**：有没有实践经验或相关背景？
3. **阅读动机**：为什么读这本书？想得到什么？
4. **期望深度**：浅尝辄止还是深入掌握？

## 规则
- 每次只问一个问题，根据用户回答动态调整下一问
- 如果用户在第1-2个回答中已透露足够信息，后续问题可以精简
- 3-5轮后，输出用户画像

## 最终输出格式
当评估完成时，输出以下 JSON：
{{
  "assessment_complete": true,
  "profile": {{
    "domain_level": "beginner | intermediate | advanced",
    "goal": "用户想通过这本书掌握……",
    "focus_areas": ["重点1", "重点2"],
    "skip_basics": false,
    "reading_pace": "moderate",
    "tip_for_ai": "给后续导读 AI 的建议"
  }}
}}

## 注意事项
- 友好、好奇的语气，不是考试
- 不要一次性抛出所有问题
- 中文对话"""


# ═══════════════════════════════════════════════════════════════
# Prompt E: 对话压缩
# ═══════════════════════════════════════════════════════════════

COMPRESSION_PROMPT = """以下是用户之前的部分对话记录。请将其压缩为一小段摘要，保留关键信息，丢弃冗余细节。

## 输入
{old_conversation}

## 输出要求
- 不超过 200 字
- 保留：用户理解正确的概念、用户理解有偏差的概念、用户跳过的话题
- 丢弃：具体的追问措辞、闲聊、重复内容

## 输出格式
"此前对话摘要：用户理解了[概念1][概念2]。在[概念3]上理解有偏差（认为……）。跳过了[话题X]。关键背景：用户提到[相关经验]。" """


# ═══════════════════════════════════════════════════════════════
# 上下文管理
# ═══════════════════════════════════════════════════════════════

def build_context(
    book_text: str,
    conversation_history: list[dict],
    current_chapter: int,
) -> list[dict]:
    """
    构建送给 LLM 的完整上下文。
    框架导航 + 原文兜底：同时包含章节框架和全书原文。
    ⚠️ 超过 CONTEXT_MAX_TOKENS 时压缩旧对话（Prompt E）
    """
    # 计算 token 量
    history_text = "\n".join(m.get("content", "") for m in conversation_history)
    total_estimate = count_tokens(book_text) + count_tokens(history_text)

    # 超过阈值 → 调用 Prompt E 压缩旧对话
    if total_estimate > settings.context_max_tokens:
        window = settings.context_window_rounds
        recent = conversation_history[-(window * 2):]
        old = conversation_history[:-(window * 2)]
        if old:
            old_summary = compress_conversation_sync(old)
            recent.insert(0, {"role": "system", "content": old_summary})
        conversation_history = recent

    messages = [{"role": "system", "content": f"以下是本书全文，请基于此书进行苏格拉底式导读：\n\n{book_text}"}]
    messages.extend(conversation_history)
    return messages


def compress_conversation_sync(old_messages: list[dict]) -> str:
    """
    压缩旧对话（同步版本，不调 LLM）。
    生产环境应改为异步调用 Prompt E 用 LLM 压缩。
    ⚠️ 预留切换口：替换此函数为 llm_service.chat(COMPRESSION_PROMPT)
    """
    user_messages = [m["content"] for m in old_messages if m.get("role") == "user"]
    if not user_messages:
        return ""
    return f"此前对话摘要：用户提到{'；'.join(user_messages[-5:])}"


# ═══════════════════════════════════════════════════════════════
# 功能函数
# ═══════════════════════════════════════════════════════════════

async def generate_chapter_structure(
    book_title: str,
    chapter_index: int,
    chapter_text: str,
    mode: str = "quick",
) -> dict:
    """
    调用 Prompt A 生成章节导读框架。
    非流式，每章调用 1 次。
    """
    prompt = get_chapter_structure_prompt(mode, book_title, chapter_index)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": chapter_text},
    ]
    result = await chat(messages, temperature=0.3, max_tokens=2000)
    import json
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"error": "章节框架解析失败", "raw": result[:500]}


async def socratic_chat_stream(
    mode: str,
    chapter_framework: dict,
    book_text: str,
    conversation_history: list[dict],
    user_message: str,
    model: str | None = None,
):
    """
    苏格拉底追问流式对话 (Prompt B)。
    每轮用户回答后调用，返回 async generator。
    """
    system_prompt = get_socratic_prompt(mode, chapter_framework)

    # 组装消息：系统提示 + 全书原文 + 对话历史（已含压缩逻辑）
    messages = [{"role": "system", "content": f"{system_prompt}\n\n## 全书原文\n{book_text}"}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})

    # 再次检查上下文大小
    full_text = "\n".join(m.get("content", "") for m in messages)
    if count_tokens(full_text) > settings.context_max_tokens:
        messages = build_context(book_text, messages[1:], 0)  # 压缩后重建

    async for token in chat_stream(messages, model=model):
        yield token


async def extract_concepts(
    chapter_index: int,
    conversation_history: list[dict],
) -> dict:
    """
    调用 Prompt C 从对话中提取概念和观点。
    每章导读结束后调用 1 次。
    返回: {"concepts": [...], "viewpoints": [...]}
    """
    prompt = CONCEPT_EXTRACTION_PROMPT.format(chapter_index=chapter_index)
    dialogue_text = "\n".join(
        f"{m['role']}: {m['content']}" for m in conversation_history
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"以下是对话记录：\n\n{dialogue_text}"},
    ]
    result = await chat(messages, temperature=0.3, max_tokens=1000)
    import json
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"concepts": [], "viewpoints": []}


async def generate_assessment_question(
    book_title: str,
    author: str,
    category: str,
    conversation_history: list[dict],
) -> str:
    """
    调用 Prompt D 生成下一轮评估问题或输出用户画像。
    每次用户回答后调用，3-5 轮。
    """
    prompt = ASSESSMENT_PROMPT.format(
        book_title=book_title, author=author or "未知", category=category or "未知"
    )
    messages = [
        {"role": "system", "content": prompt},
    ]
    messages.extend(conversation_history)
    result = await chat(messages, temperature=0.7)
    return result
