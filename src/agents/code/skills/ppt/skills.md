# PPT Skill 索引

这是一个**过程型 skill**（不是 Python 函数库）。核心工作流写在 `SKILL.md`，按需读取 `references/` 下的参考文档，并从 `assets/` 拷贝模板到 workspace。

## 工作流总览

完整 6 步流程见 `SKILL.md`：
1. 需求澄清（7 问对齐风格、受众、时长、素材、主题色等）
2. 拷贝模板到 workspace 的 `index.html`
3. 填充内容（选 layout、改文案、配图）
4. 对照 checklist 自检
5. 浏览器本地预览
6. 根据反馈迭代

## 关键文件（按需 read_skill_file）

| 路径 | 用途 | 何时读 |
|---|---|---|
| `SKILL.md` | 完整工作流与硬规则 | 接到 PPT 任务的第一件事 |
| `references/themes.md` | 风格 A 的 5 套主题色预设 | 选风格 A 后 |
| `references/themes-swiss.md` | 风格 B 的 4 套主题色预设 | 选风格 B 后 |
| `references/layouts.md` | 风格 A 的 10 种 layout 骨架 + Pre-flight 类名清单 | 风格 A 写 slide 前 |
| `references/swiss-layout-lock.md` | 风格 B 的 22 个登记版式锁 | 风格 B 写 slide 前必读 |
| `references/layouts-swiss.md` | 风格 B 的 S01-S22 版式骨架 | 风格 B 选版式 |
| `references/swiss-map-component.md` | 风格 B 的 S08 地图扩展（路线/地点） | 需要地图页时 |
| `references/components.md` | 风格 A 的组件细节（字体、网格、动效） | 风格 A 调细节 |
| `references/image-prompts.md` | GPT 配图类型、比例、提示词 | 需要生成配图时 |
| `references/screenshot-framing.md` | 截图美化的内置背景资产映射 | 处理用户截图时 |
| `references/checklist.md` | P0/P1/P2/P3 分级质量检查清单 | 生成完自检前 |

## 模板与资产（用 get_skill_root + shutil.copy 拷贝）

| 路径 | 用途 |
|---|---|
| `assets/template.html` | 风格 A 完整可运行的种子 HTML |
| `assets/template-swiss.html` | 风格 B 完整可运行的种子 HTML |
| `assets/motion.min.js` | Motion One 离线兜底 |
| `assets/screenshot-backgrounds/` | 截图美化的 WebP 背景资产 |

## 校验脚本（用 subprocess 调用）

| 路径 | 用途 |
|---|---|
| `scripts/validate-swiss-deck.mjs` | 风格 B 静态校验（登记版式、图片槽位、SVG 文本、标题对齐）。需要本机有 `node`。 |

## 工作目录约定

输出物（`index.html` + `images/`）写到 agent 当前 workspace 下的 `ppt/` 子目录，不要写到 skill 目录本身。

## 与 CommonAgent 适配的注意事项

SKILL.md 中部分内容是为 Claude Code / Codex 环境编写，在 CommonAgent 中：
- "Ask Question / `ask_question`" 工具不可用——澄清问题以 final message 形式返回给用户，由 REPL 下一轮接收。
- `<SKILL_ROOT>` 占位符 = `get_skill_root("ppt")` 的返回值。
- SKILL.md 里出现的绝对路径（如 `/Users/guohao/...`）是原作者环境的硬编码，忽略即可。
