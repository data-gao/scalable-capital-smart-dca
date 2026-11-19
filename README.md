# Scalable Capital Agentic Investing MCP 配置指南

本工作区已自动配置 Scalable Capital 的官方 MCP (Model Context Protocol) 服务。

---

## 1. 核心连接信息

- **MCP Endpoint URL**: `https://mcp.scalable.capital/mcp`
- **协议类型**: Streamable HTTP / MCP
- **配置文件位置**: 
  - 本地项目插件: [mcp_config.json](file:///Users/chair_kao/Antigravity/scalable-capital-smart-dca/.agents/plugins/scalable-capital/mcp_config.json)
  - 插件清单: [plugin.json](file:///Users/chair_kao/Antigravity/scalable-capital-smart-dca/.agents/plugins/scalable-capital/plugin.json)

---

## 2. 账号授权步骤（必须先在 Scalable Capital 开启）

在 AI 助手连接之前，必须先在 Scalable 账户中授权 Agentic Investing：

1. **登录网页版**：访问 [Scalable Capital Web 门户](https://de.scalable.capital/) 并登录账户。
2. **进入安全设置**：点击右上角 **Profil (Profile)** -> **Sicherheit (Security)** -> **Agentic Investing**。
3. **启用 MCP 访问**：
   - 打开 **MCP Access** 开关。
   - 选择权限范围：建议初始设置为 **Read-Only (只读权限)**，若需要通过 AI 下单或调整定投计划可开启交易/执行权限。
4. **App 确认**：在手机端 Scalable Capital App 上弹出的双重验证 (2FA) 提示中确认授权。

---

## 3. 在不同客户端中的配置方式

### A. Antigravity (当前环境)
已在本工作区配置完成：
```
.agents/plugins/scalable-capital/
├── plugin.json
└── mcp_config.json
```
如果需要全局生效，可将其内容复制到 `~/.gemini/config/mcp_config.json`。

### B. Claude (Web / Claude Desktop)
- **Claude Web (Connectors)**：
  1. 进入 **Settings / Customize** -> **Connectors**。
  2. 点击 **Add custom connector**。
  3. 输入名称 `Scalable Capital`，URL 填入 `https://mcp.scalable.capital/mcp`。
- **Claude Desktop (`claude_desktop_config.json`)**：
  ```json
  {
    "mcpServers": {
      "scalable-capital": {
        "url": "https://mcp.scalable.capital/mcp"
      }
    }
  }
  ```

### C. Cursor / Windsurf
在设置中的 MCP Server 配置中添加：
- **Type**: Remote (SSE / HTTP)
- **Name**: `scalable-capital`
- **URL**: `https://mcp.scalable.capital/mcp`

### D. ChatGPT (Custom Connector / Plugin)
在 ChatGPT Web 界面中通过添加自定义连接器填入 `https://mcp.scalable.capital/mcp`。

---

## 4. 官方 CLI 工具 (备用方案)

Scalable Capital 官方还提供了面向终端与自动化的命令行工具 `scalable-cli` (`sc`)：

```bash
# macOS 安装 (Homebrew)
brew tap ScalableCapital/tap
brew trust --formula ScalableCapital/tap/scalable-cli
brew install scalable-cli

# 登录授权
sc login

# 检查权限与功能
sc capabilities --json
```

---

## 5. 安全机制提示

- **资金安全**：出金、转账和充值依然被严格隔离在银行体系内，AI **无法**进行资金划转。
- **两步确认**：即使开启了交易权限，所有订单与定投修改都会先生成预览，必须获得您的显式授权确认后才会执行。
