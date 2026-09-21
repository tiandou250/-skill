# -skill

WorkBuddy 自建技能集合。

## 技能列表

| 技能 | 说明 | 触发 |
|------|------|------|
| [文献阅读器](./文献阅读器) | 把一篇文献读透，产出中文 Word 总结报告：三张自绘图表（结构导图 / 研究流程图 / 概念关系图）+ 大白话解读 | 「帮我总结文献」 |

## 安装

把技能目录整个复制到 WorkBuddy 的技能目录下：

```bash
# Windows
xcopy /E /I "文献阅读器" "%USERPROFILE%\.workbuddy\skills\文献阅读器"

# macOS / Linux
cp -r "文献阅读器" ~/.workbuddy/skills/
```

然后在该目录的注册表 `agent-created-skills.json` 里追加一条记录，这样技能才能被后续修改/删除：

```json
{
  "skills": [
    {
      "name": "文献阅读器",
      "createdAt": "2026-09-21T17:27:16+08:00",
      "skillDir": "文献阅读器"
    }
  ]
}
```

重启会话后，说「帮我总结文献」即可触发。

## 依赖

| 技能 | 依赖 |
|------|------|
| 文献阅读器 | Python 3.10+ 与 `Pillow`（绘图）；输出 .docx 需 WorkBuddy 的 `tencent-docx` 插件 |

```bash
python -m pip install Pillow
```

## 关于路径

`文献阅读器/SKILL.md` 里的解释器路径、插件路径是**按作者本机环境写死的**（Windows，托管 Python venv）。
换机器使用时需要改这几处：

- 渲染器解释器：`C:\Users\<你>\.workbuddy\binaries\python\envs\default\Scripts\python.exe`
- 技能目录：`C:\Users\<你>\.workbuddy\skills\文献阅读器\scripts\render_diagram.py`
- 输出目录：默认 `D:\file\文献阅读报告\`，可改成任意路径

`render_diagram.py` 本身是跨平台的，脚本会自动探测中文衬线/黑体字体（Windows 微软雅黑 / macOS PingFang / Linux Noto Sans CJK）。

## 许可

MIT
