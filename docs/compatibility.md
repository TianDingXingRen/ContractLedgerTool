# 文档兼容性基线

本项目把兼容性结论分为两层，避免把“库能够读写 DOCX”误报为“所有办公软件实机通过”。

## 自动结构矩阵

CI 每次验证以下 OOXML 场景：

- Microsoft Word 常见的跨多个 run 占位符；
- WPS/Word 常见的中文字体、页眉、页脚、分页和多节文档；
- 合并表头与可重复明细行；
- 中文、英文、人民币符号和带圈数字；
- DOCX 必需 OOXML 部件及压缩包安全检查；

执行：

```powershell
python scripts/office_compatibility_check.py
```

报告写入 `build/office-compatibility.json`。

当前自动基线覆盖 DOCX/OOXML 结构；WPS 的最终视觉排版仍应在准备正式发行时用目标 WPS 版本做人工抽检。

旧版 `.doc` 模板转换使用独立的 Word/WPS 子进程，不连接用户已经打开的 Office 实例；打开外部文档前强制禁用宏，失败时清理半成品。
