---
name: 文献阅读器
description: >
  文献阅读器：把用户提供的一篇文献（PDF / Word / Markdown / 纯文本 / 网页链接 / 扫描件图片）读透，
  自动产出一份中文 Word 总结报告——内含三张自绘图表（文献结构导图、研究流程图、核心概念关系图），
  并用大白话解释文献大意。
  触发场景：用户说「帮我总结文献」「总结一下这篇文献」「读一下这篇论文」「帮我读文献」「这篇文献讲了什么」
  「梳理一下这篇文章」「literature summary」，或用户提供文献文件/链接并希望得到结构化摘要、
  图表梳理或通俗解读时，一律使用本技能。
description_zh: 文献阅读器
description_en: Literature Reader
display_name: 文献阅读器
version: 1.0.0
disable: false
disable-model-invocation: false
user-invocable: true
agent_created: true
---

# 文献阅读器

把一篇文献读透，交付一份中文 Word 总结报告：三张自绘图表 + 大白话解读。

判断标准只有一条：**用户读完报告，能不能不看原文就说明白这篇文献在干什么、怎么干的、结论是什么、有什么坑。**

## 触发条件

命中任一即启用：

1. 用户说「帮我总结文献」「总结一下这篇文献」「帮我读文献」「这篇文献讲了什么」。
2. 用户给出一篇文献（文件路径、附件、链接、粘贴的正文）并要求总结、梳理、摘要、解读。
3. 用户要「文献结构图」「研究流程图」「概念关系图」这类基于文献的图表。

## 工作流

按顺序执行，不要跳步。

### Step 0　准备输出目录

默认输出根目录 `D:\file\文献阅读报告\`（本机约定：新增文件一律落 D 盘，不要写 C 盘）。
该篇文献一个子目录：`D:\file\文献阅读报告\<文献短名>\`，内部结构：

```
<文献短名>\
├── <文献短名>_总结报告.docx     ← 最终交付物
├── figs\                        ← 三张图表 PNG
├── figures.json                 ← 图表规格（可复现）
└── report.html                  ← 中间产物，Word 就是由它转出来的
```

`<文献短名>` 取文献标题的核心词，去掉副标题与标点，控制在 20 字以内。
用户若明确指定了输出位置，以用户指定为准。

### Step 1　读取文献

按文件类型选读取方式：

| 来源 | 读取方式 |
|------|----------|
| PDF（含扫描件） | `Read` 工具直接读，支持逐页图文解析；表格复杂时改用 `pdf` 技能 |
| .docx / .doc | 先加载 `tencent-docs-routing` 技能，按其路由读取 |
| .md / .txt / .html | `Read` 工具 |
| 网页链接 | `WebFetch` 工具 |
| 图片型文献（拍照/截图） | `Read` 工具（多模态） |
| 用户直接粘贴正文 | 直接用，不必落盘 |

**必须读完全文再动笔。** 只读摘要会漏掉方法细节与局限，而这恰恰是报告最有价值的部分。
长文献可分段读取，边读边记录，不要靠印象下笔。

### Step 2　结构化拆解

在脑中（或草稿里）产出以下素材，它们是三张图的原料：

1. **章节树**：一级标题 + 二级标题，最多 2 层。若原文层级更深，压缩合并。
2. **研究流程**：从「研究起点」到「结论」的 4–7 个关键环节，每个环节配一句细节说明。
3. **核心概念**：1 个中心概念 + 4–7 个相关概念，外加它们之间的关系词（如「决定」「推高」「压低」）。
4. **关键结论**：3–5 条，每条一句话。
5. **关键数据/证据**：实验规模、样本量、关键指标、对比结果。
6. **局限与存疑**：作者自己承认的 + 你看出来的。
7. **术语表**：英文原词 → 中文含义。

**语言规则：全中文输出。** 专业术语保留英文原词并在括号里给中文，例如「效用 AI（Utility AI）」。

### Step 3　生成三张图表

用本技能自带的渲染器，把 JSON 规格渲染成 PNG。**不要手写 SVG，不要用画图工具，一律走脚本。**

渲染器：`scripts/render_diagram.py`（在本技能目录下）
解释器：`C:\Users\14986\.workbuddy\binaries\python\envs\default\Scripts\python.exe`（已装 Pillow）

```bash
<上面的解释器> "C:\Users\14986\.workbuddy\skills\文献阅读器\scripts\render_diagram.py" \
  "<输出目录>\figures.json" --outdir "<输出目录>\figs" --fit-ratio 0.72
```

`figures.json` 里放三张图：`tree`（结构导图）、`flow`（流程图）、`concept`（概念关系图）。
字段定义与完整示例见 `references/diagram-spec.md`，动手前**先读它**。

脚本成功时在 stdout 输出 JSON：

```json
{"ok": true, "images": [{"id":"fig1","type":"tree","path":"...","width":876,"height":1217,"ratio":0.72}], "warnings": []}
```

`warnings` 非空时必须处理：长宽比告警说明图太扁或太长，应合并层级或精简节点文字后重渲染。

### Step 4　写报告 HTML

以 `references/report-template.html` 为骨架，把 Step 2 的素材填进去。

- 图表用 `<img src="figs/xxx.png" width="528">` 引用。**宽度必须显式写 `width="528"`**（= 13.97cm，这是转换引擎内置的图片宽度上限，写更大的值也会被截到 13.97cm）。要更小的图就写更小的 px 值，按 `px × 0.75 ÷ 72` 英寸换算。
- 图片前加 `<h2>` 小标题，图片后加一行 `<p class="figcap">图 N　说明</p>`，再跟一段解读正文。
- 只使用模板里出现过的标签与类名（h1/h2/p/table/ul/ol/li/img/div data-component="callout"），不要引入模板外的复杂 CSS。
- 报告 HTML 要保存在 `<输出目录>` 下，且 `figs/` 是它的同级子目录——图片用的是相对路径。
- 图片居中靠 inline style：`style="display: block; margin-left: auto; margin-right: auto;"`。转换引擎识别这个固定写法并转为居中对齐，其他居中写法（如 `text-align`）无效。

### Step 5　转为 Word

先加载 `tencent-docs-routing` 技能确认路由，再按 `tencent-docx` 的 `html-to-docx` 引擎执行转换。

**主路径**（bash 可用时）：

```bash
bash "<plugin_root>/scripts/wb/local/setup-html-to-docx.sh"
cd "<plugin_root>/skills/html-to-docx/scripts"
"$HOME/.venv-html-to-docx/bin/python" -m html_to_docx convert "<输出目录>\report.html" -o "<输出目录>\<文献短名>_总结报告.docx"
```

`<plugin_root>` 用 Glob 在 `C:\Users\14986\.workbuddy\plugins\cache\workbuddy-builtin\tencent-docx\*\` 下取版本号最大的那个目录。

> Windows 上 venv 的解释器是 `Scripts\python.exe` 而不是 `bin/python`（`setup-html-to-docx.sh` 打印的 `Python runner:` 那行才是准的，以它为准）。

**备用路径**（本机 bash 缺 coreutils，`ls`/`head`/`cp`/`bash` 均不可用，setup 脚本会失败）：

```bash
"C:\Users\14986\.workbuddy\binaries\python\envs\html2docx\Scripts\python.exe" \
  -m html_to_docx convert "<输出目录>\report.html" -o "<输出目录>\<文献短名>_总结报告.docx"
```
cwd 需设为 `<plugin_root>\skills\html-to-docx\scripts`，或用 `PYTHONPATH` 指向该目录。

转换成功后 stdout 输出 `{"success": true, "docx_path": "..."}`。若 `success` 为 false，读 `error` 字段定位问题；`markdown_fallback` 是降级文本，不要拿它当交付物。

### Step 6　大白话解读

**这一步不能省。** 在对话回复里用大白话把文献讲一遍：

1. **一句话结论**：这篇文献想证明什么，成没成。
2. **一个类比**：用日常生活场景打比方（例如「景区里一千个群众演员 + 一个导演」），让完全外行也能懂。
3. **一个提醒**：这篇文献最值得质疑的一点是什么。

控制在 5 句话以内，不要复述报告内容。用户要的是「所以呢」。

### Step 7　交付

调用 `present_files` 打开 `.docx`。回复里给一句话摘要 + 文件路径 + 遗留问题。

## 报告结构

固定十个部分，顺序不要改（模板已内置）：

1. 标题 + 元信息行（文献类型 / 阅读日期）
2. 一句话说清楚（callout 组件）
3. 一、文献速览（表格：研究问题 / 核心主张 / 研究方法 / 主要结论 / 局限）
4. 二、文献结构导图（图 1 + 解读）
5. 三、研究流程图（图 2 + 解读）
6. 四、核心概念关系图（图 3 + 解读）
7. 五、大白话解读（打比方讲一遍）
8. 六、关键结论（编号列表）
9. 七、关键证据与数据
10. 八、局限与存疑
11. 九、对我的启发
12. 十、术语对照（表格）

## Pitfalls

- **SKILL.md 里的 `${...}` 会在技能加载时被替换掉。** 技能正文会过一遍 `substituteLoadTimeVariables`：`${XXX}` 形式的片段会被就地求值（`$HOME`、`$VAR` 这类裸变量则原样保留）。所以正文里不要写 `${...}`，需要变量就写裸 `$HOME`。
- **本机 bash 不可用。** `ls`、`head`、`cp`、`grep` 等命令都不存在，别用 bash 做文件操作或管道。用 Python 一行式、或 Read/Write/Glob 工具。
- **结构图别塞太多节点。** 超过 14 个节点或 3 层，图会被拉成竖条，在 Word 里缩得很小、字看不清。宁可把「3.1 / 3.2 / 3.3」合并成「3 方法」一个节点的三个子项，也不要铺满全文目录。
- **图片宽度写 `width="528"`（上限 13.97cm）。** 转换引擎把图片宽度硬顶在 5.5 英寸，写更大无效、不写则按 PNG 的 300dpi 元数据推算成 14.8cm——反而会轻微超出版心。写 `528` 最稳。
- **概念图节点文字要短。** 每个节点控制在 12 字以内，关系词 2–5 字。太长会互相挤，标签避让会失效。
- **别改 `figures.json` 的 `type` 取值**，只支持 `tree` / `flow` / `concept` 三种。
- **`--fit-ratio 0.72` 不要去掉。** 竖长的图会被补白到安全长宽比，保证在 Word 里按页宽放置不会溢出页面。补白是白底，视觉上看不出来。
- **术语不要硬译。** 遇到没有通用中文译名的词，保留英文原词，后面括号补一句解释，不要自己造词。

## 完成检查

交付前逐条核对：

1. `figures.json` 存在，且三张图都渲染成功（脚本 `ok: true`，`warnings` 为空）。
2. `figs\` 下三张 PNG 都存在，肉眼看过一遍，没有文字重叠、没有标签压线。
3. `report.html` 里每个 `<img>` 都是 `width="528"`，且 `src` 指向 `figs/` 下的真实文件。
4. `.docx` 转换成功，用 `Read` 工具打开确认三张图都在、没有被替换成 `[图片无法加载]`。
5. 对话回复里有大白话解读，不是只丢了个文件。
6. 已调用 `present_files`。
