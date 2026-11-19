# Scalable Capital Agentic Investing MCP Setup Guide

This workspace supports Scalable Capital's official MCP (Model Context Protocol) service.

---

## 1. Connection Details

- **MCP Endpoint URL**: `https://mcp.scalable.capital/mcp`
- **Protocol Type**: Streamable HTTP / MCP
- **Config Files**:
  - Local Project Plugin: `.agents/plugins/scalable-capital/mcp_config.json`
  - Plugin Manifest: `.agents/plugins/scalable-capital/plugin.json`

---

## 2. Authorization Steps (Scalable Capital Account)

Before connecting:

1. **Log in to Web Portal**: Visit [Scalable Capital Web Portal](https://de.scalable.capital/) and log in.
2. **Open Security Settings**: Go to **Profile** -> **Security** -> **Agentic Investing**.
3. **Enable MCP Access**:
   - Turn on the **MCP Access** toggle.
   - Choose permission scope: **Read-Only** recommended initially. Enable trading/execution permissions if you want AI to submit orders or modify savings plans.
4. **App 2FA Confirmation**: Confirm authorization on your mobile Scalable Capital app when prompted.

---

## 3. Official CLI Tool (`sc`)

Scalable Capital also provides the official command-line tool `scalable-cli` (`sc`):

```bash
# macOS installation via Homebrew
brew tap ScalableCapital/tap
brew trust --formula ScalableCapital/tap/scalable-cli
brew install scalable-cli

# Login and authentication
sc login

# Inspect CLI capabilities
sc capabilities --json
```

---

## 4. Safety Architecture

- **Fund Isolation**: Cash deposits, withdrawals, and bank transfers remain strictly isolated within the banking infrastructure. AI has **no** ability to transfer funds externally.
- **Two-Phase Confirmation**: All orders and plan modifications generate an ex-ante preview first, requiring explicit confirmation before execution.
