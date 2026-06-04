合同管理工具 EXE 版使用说明

文件：
ContractLedgerTool.exe

使用方法：
1. 将 ContractLedgerTool.exe 复制到目标 Windows 电脑上的任意文件夹。
2. 双击运行 ContractLedgerTool.exe。
3. 程序会启动本地服务，并自动打开浏览器。
4. 默认访问地址：http://127.0.0.1:5000/
5. 关闭程序窗口即可停止服务。

运行数据：
首次运行后，exe 同目录会自动生成以下文件夹：
- data：合同台账数据库
- output：生成的合同和导出的付款计划
- templates：合同模板定义
- uploads：模板源 Word 文件
- sessions：临时会话数据

说明：
1. EXE 已内置 Python 运行环境、页面资源和“订货合同模板”。
2. 目标电脑不需要安装 Python，也不需要联网安装依赖。
3. 如果 5000 端口被占用，可从命令行指定端口：
   ContractLedgerTool.exe --port 5050
4. 如果不想自动打开浏览器，可使用：
   ContractLedgerTool.exe --no-browser
