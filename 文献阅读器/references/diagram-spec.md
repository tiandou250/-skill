# 图表 JSON 规格（figures.json）

渲染器 `scripts/render_diagram.py` 的输入契约。所有字段均为中文文本，UTF-8 编码。

## 调用

```bash
"C:\Users\14986\.workbuddy\binaries\python\envs\default\Scripts\python.exe" \
  "C:\Users\14986\.workbuddy\skills\文献阅读器\scripts\render_diagram.py" \
  "<输出目录>\figures.json" --outdir "<输出目录>\figs" --fit-ratio 0.72
```

| 参数 | 说明 |
|------|------|
| `spec` | JSON 文件路径。可以是单个图对象，也可以是 `{"diagrams": [...]}` 装多张图 |
| `--outdir` / `-o` | PNG 输出目录。默认为 spec 文件所在目录 |
| `--fit-ratio` | 最小长宽比，默认 `0.70`。低于该值则横向补白，保证按页宽放进 Word 时不会超页高。本技能统一用 `0.72` |

成功输出：

```json
{"ok": true,
 "images": [{"id":"fig1","type":"tree","path":"D:\\...\\figs\\fig1_tree.png",
             "width":876,"height":1217,"ratio":0.72}],
 "warnings": []}
```

失败输出 `{"ok": false, "error": "..."}`，退出码 1。`warnings` 非空时必须处理后再交付。

输出文件命名为 `<id>_<type>.png`，例如 `fig1_tree.png`。

---

## 通用字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 否 | 文件名前缀，默认 `fig1`、`fig2`… |
| `type` | string | **是** | `tree` / `flow` / `concept` |
| `title` | string | 否 | 图题，如「图 1　文献结构导图」 |
| `fit_ratio` | number | 否 | 单张图覆盖全局 `--fit-ratio`；`0` 表示不补白 |

---

## type: tree　文献结构导图

层级树。**默认左→右布局**（层级沿 x 推进，兄弟沿 y 排开），最适合呈现文献大纲。

| 字段 | 类型 | 说明 |
|------|------|------|
| `root` | object | 根节点，必填 |
| `direction` | string | `horizontal`（默认）/ `vertical` |

节点对象递归结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | string | 节点文字 |
| `children` | array | 子节点数组，可为空或省略 |

```json
{
  "id": "fig1",
  "type": "tree",
  "title": "图 1　文献结构导图",
  "root": {
    "text": "论文标题核心词",
    "children": [
      { "text": "1 引言", "children": [
        { "text": "1.1 研究背景" },
        { "text": "1.2 问题定义" }
      ]},
      { "text": "2 方法", "children": [
        { "text": "2.1 架构总览" },
        { "text": "2.2 触发条件" }
      ]},
      { "text": "3 结论" }
    ]
  }
}
```

**约束**：总节点数 ≤ 14，层级 ≤ 2 层（不含根节点）。节点文字 ≤ 16 字。
超了就会渲染成细长条，在 Word 里缩到看不清。宁可合并同级小节，也不要铺满目录。

---

## type: flow　研究流程图

步骤链，每个步骤一个盒子，带序号圆标。可含一行补充说明。

| 字段 | 类型 | 说明 |
|------|------|------|
| `steps` | array | 步骤数组，必填，建议 4–7 个 |
| `direction` | string | `vertical`（默认）/ `horizontal` |

步骤对象：

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | string | 步骤名，≤ 14 字 |
| `detail` | string | 补充说明，≤ 45 字，灰色小字显示 |

也可以直接给字符串数组，等价于只有 `text`。

```json
{
  "id": "fig2",
  "type": "flow",
  "title": "图 2　研究流程图",
  "direction": "vertical",
  "steps": [
    { "text": "构造实验环境", "detail": "三张地图 × 60 回合，含资源刷新与事件注入" },
    { "text": "基线方案运行", "detail": "纯程序化决策，不调用大模型" },
    { "text": "分层方案运行", "detail": "仅高影响、低置信度决策交给大模型" },
    { "text": "结果评估", "detail": "对比行为多样性熵值与单回合平均成本" }
  ]
}
```

---

## type: concept　核心概念关系图

中心辐射式：一个中心概念，周围一圈相关概念，辐条上标关系词；可额外画节点之间的交叉连线。

| 字段 | 类型 | 说明 |
|------|------|------|
| `center` | object | `{"text": "..."}`，中心概念，≤ 12 字 |
| `nodes` | array | 周围概念，4–7 个 |
| `links` | array | 可选，节点之间的交叉连线 |
| `center_max_width` / `node_max_width` | number | 可选，覆盖默认文字宽度上限（逻辑像素） |

节点对象：

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | string | 概念名，≤ 12 字 |
| `relation` | string | 从中心到该节点的关系词，2–5 字。也接受 `label` |
| `accent` | number | 可选，0–7 指定配色下标 |

连线对象：

| 字段 | 类型 | 说明 |
|------|------|------|
| `from` | string | 起点节点的 `text`，**必须完全一致** |
| `to` | string | 终点节点的 `text` |
| `label` | string | 关系词，可选 |

```json
{
  "id": "fig3",
  "type": "concept",
  "title": "图 3　核心概念关系图",
  "center": { "text": "分层调用架构" },
  "nodes": [
    { "text": "程序化决策", "relation": "承担 95%" },
    { "text": "大模型推理", "relation": "承担 5%" },
    { "text": "Token 成本", "relation": "核心约束" },
    { "text": "行为多样性", "relation": "体验目标" },
    { "text": "触发条件设计", "relation": "关键变量" }
  ],
  "links": [
    { "from": "触发条件设计", "to": "大模型推理", "label": "决定调用频次" },
    { "from": "大模型推理", "to": "行为多样性", "label": "提升" },
    { "from": "大模型推理", "to": "Token 成本", "label": "推高" },
    { "from": "程序化决策", "to": "Token 成本", "label": "压低" }
  ]
}
```

**约束**：`links` 的 `from` / `to` 必须逐字匹配某个节点的 `text`，否则该连线被跳过并在 `warnings` 里报出来。
节点文字超过 12 字会挤在一起，标签避让可能失效。

---

## 多图一次渲染

把三张图放进一个文件，一次调用全部渲染：

```json
{
  "diagrams": [
    { "id": "fig1", "type": "tree",    "title": "图 1　文献结构导图",   "root": { "...": "..." } },
    { "id": "fig2", "type": "flow",    "title": "图 2　研究流程图",     "steps": [] },
    { "id": "fig3", "type": "concept", "title": "图 3　核心概念关系图", "center": {}, "nodes": [] }
  ]
}
```

---

## 配色与版式（已固化，无需配置）

- 浅色主题：白底、深色文字，适配浅色 IDE 与打印。
- 8 色强调色按层级/序号循环：靛蓝、天蓝、青绿、琥珀、品红、紫罗兰、深绿、红。
- 中文自动换行：ASCII 单词整体不拆，CJK 逐字断行。
- 字体自动探测：微软雅黑 → 黑体 → 宋体 → PingFang → Noto Sans CJK。
- 输出 2 倍分辨率（默认），PNG 写入 300 dpi 元数据。
