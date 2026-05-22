1. 经典混合任务（DR + codeact + 出图）


对比 2025-2026 年主流推理芯片：NVIDIA B200、AMD MI325X、华为昇腾 910C、Groq LPU v2，从 FP8/INT8 算力、HBM 容量带宽、单卡功耗、tokens/J 能效、Llama-70B 实测吞吐、单位 token 成本这几个维度做研究，然后基于研究结论生成一份带图的 HTML 报告，保存到 ./output/chip-compare/。
压点：plan 是否拆成 2 步（不是 5 步），DR 是否单次 fan-out 覆盖 4 款芯片，HTML 是否落到 workspace。

2. 时效性强 + 多来源


帮我研究 2026 年 Q1 全球 AI Agent 框架的格局变化：LangGraph、LlamaIndex Workflows、Microsoft Autogen、OpenAI Swarm/Agents SDK、CrewAI、Anthropic Claude Agent SDK 的最新动向、GitHub stars 与采用情况、各自的差异化定位。输出一份 markdown 简报，附主要来源链接。
压点：DR 是否真的能聚合多源信息、evaluator 能否过滤无关结果、report 是否带 citation。

3. 纯 codeact，数据 → 分析 → 可视化


生成一段模拟的电商订单数据（10000 条，包含 order_id、user_id、category、price、timestamp 跨 30 天），保存为 CSV；然后做以下分析并出图：1) 每天 GMV 趋势 2) 各品类销售占比 3) 用户消费金额分布（直方图 + log scale）4) 复购用户占比。最后输出一份 HTML dashboard 把 4 张图嵌进去。
压点：codeact 多步骤组合（生成 → 分析 → 画图 → HTML 拼装）是否一次跑完，文件是否真的落到 workspace。

4. 触发 skill（看 list_skills 走没走通）


我要给一个内部 workshop 做 PPT，主题是"LLM Agent 的工程化挑战"，内容大致 6-8 页：背景、agent loop 原理、planning/memory/tool use 三大组件、工程难点（成本、可观测性、HITL）、当前主流框架对比、我们团队的实践方向。帮我生成这个 PPT。
压点：协调器是否识别出该用 skill（你项目里有 ppt skill 的话），codeact 进去之后是否走 list_skills → get_skills_desc → list_skill_files → read_skill_file 这套流程而不是自己瞎拼。

5. 重度混合任务（最综合）


我在做一份"国产大模型 2025 全年回顾"的内部分享，需要你：
1) 研究 2025 年发布的主要国产模型（DeepSeek 系列、Qwen 系列、GLM、Kimi、MiniMax、豆包、Step、文心），覆盖参数规模、训练数据、benchmark 表现、开源策略、商业化进展；
2) 把研究结果整理成结构化数据（JSON），保存到 ./output/cn-llm-2025/data.json；
3) 基于数据生成 3 张图：MMLU/CMMLU 跑分对比柱状图、开源 vs 闭源时间线、参数规模 vs 性能散点图；
4) 最后拼成一份 HTML 长报告，包含文字综述 + 图表 + 数据表 + 引用来源，保存为 ./output/cn-llm-2025/report.html。
压点：整条 pipeline——长 plan、单次大 DR、codeact 多产物、跨步骤的数据流转（DR 发现要在 task 里被显式喂给 codeact，因为 codeact 看不到外层 state）。

如果想先看协调器的"判断力"而不是产出质量，跑 1 和 4；想看 DR 子图本身的健壮性，跑 2；想看 codeact 是否稳，跑 3；想看整套体系会不会哪一环散架，跑 5。