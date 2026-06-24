# Swarm-Driven Agent (SDA) Installer & Workflow

A universal, local-first installer and manager for **SDA** (Swarm-Driven Agent) configurations and **SWDD** (Swarm-Driven Development) workflows. It simplifies scanning, version checking, upgrading, and creating Hermes and OpenClaw agents on your local machine.

---

## 🌟 Architecture & Nomenclature

To ensure consistent logic and governance, this project strictly distinguishes between the agent's runtime structure and its development methodology:

| Term | Context | File | Purpose |
| :--- | :--- | :--- | :--- |
| **SDA** | Swarm-Driven Agent | [SOUL.md](SOUL.md) | Streamlined entry point focusing strictly on **System Identity** (定位) and dual-core references. |
| **SDA Contract** | System Contract | [RULE.md](RULE.md) | Defines FSM transition hooks, attention anchors, memory decay, safety firewalls, and self-diagnosis. |
| **SWDD** | Swarm-Driven Development | [SKILL.md](SKILL.md) | The supreme development meta-skill (做事方法) describing parallel planning, Builder/Destroyer reviews, and sandbox execution. |

---

## 🚀 Key Features

* 🔒 **Strictly Local & Offline**: Operates 100% locally on your file system using `os.walk` to find agent profiles under `~/.hermes` and `~/.openclaw`.
* 🔄 **Smart FSM Merging**: Upgrades agent configurations while preserving customized system positioning (`# 1. 系統定位` such as specific Quant profiles), merging only the updated FSM rules and contracts.
* 📊 **Version Tracking & Status check**: Uses semantic version parsing to compare installed files against templates, reporting `Not Installed`, `Update Available`, or `Up-to-date` statuses.
* ➕ **Agent Creation**: Spin up brand new Hermes or OpenClaw agents from scratch with auto-configured workflows using a single command.
* 🛡️ **Auto-Backup System**: Creates timestamped backups (e.g. `SOUL.md.20260624_150000.bak`) automatically before editing any file.

---

## 📂 Repository Layout

```
swarm-driven-agent/
├── installer.py     # CLI installer, version manager & creator
├── SOUL.md          # SDA System Identity template (streamlined)
├── RULE.md          # SDA System Instruction Contract
├── SKILL.md         # SWDD Swarm meta-skill workflow
└── .gitignore       # Standard git ignore definitions
```

---

## 🛠️ Usage Instructions

Ensure the script is executable:
```bash
chmod +x installer.py
```

### 1. Interactive Selection Menu
Run the installer with no arguments to scan your system and choose which agents to update interactively:
```bash
./installer.py
```

### 2. Check Agent Statuses
Print a detailed report showing the installation status and version breakdown of all detected agents:
```bash
./installer.py --check
```

### 3. Create a Brand New Agent
Initialize a new agent workspace folder, set its system identity, and install the SDA workflow:
```bash
# Initialize an OpenClaw agent
./installer.py --create my_coder_agent --type openclaw --identity "A senior software engineering assistant specializing in Python refactoring."

# Initialize a Hermes agent
./installer.py --create my_analyst_agent --type hermes
```

### 4. Direct/Quiet Agent Upgrades
Install or upgrade specific agents directly via CLI arguments:
```bash
# Upgrade xuandao and finance agents
./installer.py xuandao finance

# Quietly upgrade all detected agents without prompting for confirmation
./installer.py -y all
```

---

## 📄 License

This project is licensed under the MIT License.
