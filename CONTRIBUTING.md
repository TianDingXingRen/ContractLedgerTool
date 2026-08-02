# 参与贡献

感谢你帮助改进 ContractLedgerTool。提交代码前，请先搜索现有 Issue 和 Pull Request，避免重复工作。

## 开发环境

项目以 Windows 10/11 和 Python 3.10+ 为主要运行环境。建议使用 Python 3.12：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
npm ci
python -m playwright install chromium
```

运行应用：

```powershell
python app.py --no-browser
```

## 提交修改

1. 从最新 `master` 创建主题分支。
2. 保持修改范围单一，避免夹带生成文件、运行时数据、合同文件或密钥。
3. Python 代码遵循现有 Ruff 与架构预算；前端沿用 Jinja、Tailwind CSS 3 和 DaisyUI 4。
4. 修改模板中的样式类后，运行 `npm run build:css` 并提交生成的 `static/css/app.min.css`。
5. 为行为变化增加测试，并运行：

```powershell
python scripts/quality_gate.py commit
python scripts/quality_gate.py ci
```

Pull Request 请说明修改原因、用户影响和验证方式。界面变化请附截图；数据迁移、导入、导出或安装器变化请说明失败与回滚路径。

## 安全与隐私

不要在 Issue、日志、截图或测试夹具中提交真实合同、供应商信息、银行账户、身份证号、手机号、密钥或其他敏感数据。安全漏洞请按 [SECURITY.md](SECURITY.md) 私下报告。

## 许可证与署名

提交贡献即表示你同意按本项目的 [MIT 许可证](LICENSE) 发布贡献。分发源代码或二进制时，必须保留原始著作权声明和许可证文本：`Copyright (c) 2026 Shao`。
