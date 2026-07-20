# 文档兼容性基线

本项目把兼容性结论分为两层，避免把“库能够读写 DOCX”误报为“所有办公软件实机通过”。

## 自动结构矩阵

CI 每次验证以下 OOXML 场景：

- Microsoft Word 常见的跨多个 run 占位符；
- WPS/Word 常见的中文字体、页眉、页脚、分页和多节文档；
- 合并表头与可重复明细行；
- 中文、英文、人民币符号和带圈数字；
- DOCX 必需 OOXML 部件及压缩包安全检查；
- PDF 转换器成功、失败、超时和无效输出路径。

执行：

```powershell
python scripts/office_compatibility_check.py
```

报告写入 `build/office-compatibility.json`。

## 本机真实转换

安装 Microsoft Word 或 LibreOffice 的机器可运行：

```powershell
python scripts/office_compatibility_check.py --real-converters --require-pdf
```

该命令使用真实桌面转换器把兼容性基准 DOCX 转为 PDF，并检查输出文件头与有效长度。它验证当前机器的转换链路，不等同于对所有 Word/WPS 历史版本作无限兼容承诺。

当前自动基线覆盖 DOCX/OOXML 结构；WPS 的最终视觉排版仍应在准备正式发行时用目标 WPS 版本做人工抽检。

Word/WPS 自动化在独立子进程中执行，不连接用户已经打开的 Word 实例；打开外部旧版文档前强制禁用宏。
Word 转换默认超过 60 秒会终止隔离进程并清理半成品，可通过 `CT_WORD_COM_TIMEOUT` 在 15–180 秒内调整；
Word 与 LibreOffice 的错误会分别保留在诊断信息中。
