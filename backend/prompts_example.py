"""
朽瓜 Prompt 文本 —— 示例文件（公开）。
复制此文件为 prompts_private.py 并填入真实 prompt 文本。
prompts_private.py 不会上传 Git。

Prompt 版本: v1.1 (2026-05-03)
  - C 改为 AI 自行决定提取数量
  - B 增加"先介绍再提问"约束
追踪见: 项目管理/03-prompts/prompts-v1.1.md
"""

# ═══════════════════════════════════════════════
# A: 章节整理 Prompt（3 种模式）
# ═══════════════════════════════════════════════
# CHAPTER_STRUCTURE_TEMPLATE: 快速版，生成 argument_tree + chapter_links
# BALANCED_EXTRA: 交互版，增加 highlight_paragraphs
# DEEP_EXTRA: 深度版，增加 segments 讨论单元

CHAPTER_STRUCTURE_TEMPLATE = """在此填入快速版章节整理 prompt"""
BALANCED_EXTRA = """在此填入交互版附加指令"""
DEEP_EXTRA = """在此填入深度版附加指令"""

# ═══════════════════════════════════════════════
# B: 苏格拉底追问 Prompt（3 种模式）
# ═══════════════════════════════════════════════
# SOCRATIC_BASE: 快速版，核心追问逻辑
# SOCRATIC_BALANCED_EXTRA: 交互版，增加原文展示规则
# SOCRATIC_DEEP_EXTRA: 深度版，增加逐段追问规则

SOCRATIC_BASE = """在此填入快速版苏格拉底追问 prompt"""
SOCRATIC_BALANCED_EXTRA = """在此填入交互版附加指令"""
SOCRATIC_DEEP_EXTRA = """在此填入深度版附加指令"""

# ═══════════════════════════════════════════════
# C: 概念提取 Prompt
# ═══════════════════════════════════════════════
# 从对话中提取 concept + viewpoint，含 evidence 字段

CONCEPT_EXTRACTION_PROMPT = """在此填入概念提取 prompt"""

# ═══════════════════════════════════════════════
# D: 背景评估 Prompt
# ═══════════════════════════════════════════════
# 3-5 轮对话了解用户背景，输出用户画像 JSON

ASSESSMENT_PROMPT = """在此填入背景评估 prompt"""

# ═══════════════════════════════════════════════
# E: 对话压缩 Prompt
# ═══════════════════════════════════════════════
# 旧对话 → 简短摘要

COMPRESSION_PROMPT = """在此填入对话压缩 prompt"""
