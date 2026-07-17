#!/usr/bin/env python3
import sys
import os
import re
import shutil
import datetime

# Determine local script paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SOUL_TEMPLATE = os.path.join(SCRIPT_DIR, "template", "modular", "SOUL.en.md")
RULE_SOURCE = os.path.join(SCRIPT_DIR, "template", "modular", "RULE.en.md")
SKILL_SOURCE = os.path.join(SCRIPT_DIR, "template", "modular", "SKILL.en.md")

def parse_semver(version_str):
    if not version_str:
        return (0, 0, 0)
    digits = re.findall(r'\d+', version_str)
    if not digits:
        return (0, 0, 0)
    parts = [int(d) for d in digits[:3]]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)

def extract_version(file_path):
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read(4096)
        lines = content.splitlines()
        # Scan the first 20 lines (frontmatter or top headers) for the version: key
        for i in range(min(20, len(lines))):
            line = lines[i].strip()
            if line.startswith('version:'):
                val = line.split(':', 1)[1].strip()
                val = val.strip('"').strip("'")
                return val
    except Exception:
        pass
    return None

def get_agent_status(agent, template_versions):
    rule_path = os.path.join(agent['dir_path'], "RULE.md")
    skill_path = os.path.join(agent['dir_path'], "skills", "swarm", "SKILL.md")
    soul_path = agent['soul_path']
    
    soul_ver = extract_version(soul_path)
    rule_ver = extract_version(rule_path) if os.path.exists(rule_path) else None
    skill_ver = extract_version(skill_path) if os.path.exists(skill_path) else None
    
    is_installed = os.path.exists(rule_path) and os.path.exists(skill_path)
    
    t_soul_ver = template_versions.get("SOUL.md")
    t_rule_ver = template_versions.get("RULE.md")
    t_skill_ver = template_versions.get("SKILL.md")
    
    p_t_soul = parse_semver(t_soul_ver)
    p_t_rule = parse_semver(t_rule_ver)
    p_t_skill = parse_semver(t_skill_ver)
    
    p_soul = parse_semver(soul_ver)
    p_rule = parse_semver(rule_ver)
    p_skill = parse_semver(skill_ver)
    
    soul_status = "ok" if p_soul >= p_t_soul else "update"
    
    if not os.path.exists(rule_path):
        rule_status = "missing"
    else:
        rule_status = "ok" if p_rule >= p_t_rule else "update"
        
    if not os.path.exists(skill_path):
        skill_status = "missing"
    else:
        skill_status = "ok" if p_skill >= p_t_skill else "update"
        
    if not is_installed:
        status = "Not Installed"
    elif soul_status == "update" or rule_status == "update" or skill_status == "update":
        status = "Update Available"
    else:
        status = "Up-to-date"
        
    return {
        "status": status,
        "soul_ver": soul_ver,
        "rule_ver": rule_ver,
        "skill_ver": skill_ver,
        "soul_status": soul_status,
        "rule_status": rule_status,
        "skill_status": skill_status
    }

def get_installed_agents_config_path():
    home_dir = os.path.expanduser("~")
    config_dir = os.path.join(home_dir, ".swda")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "installed_agents.json")

def load_installed_agents(agents_list=None):
    import json
    path = get_installed_agents_config_path()
    if not os.path.exists(path):
        # Auto-discovery fallback: if no config file exists,
        # scan the system and record any agents that already have RULE.md installed.
        installed = []
        if agents_list:
            for agent in agents_list:
                rule_path = os.path.join(agent['dir_path'], "RULE.md")
                if os.path.exists(rule_path):
                    installed.append(agent['dir_path'])
            save_installed_agents(installed)
        return installed
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []

def save_installed_agents(installed_paths):
    import json
    path = get_installed_agents_config_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(installed_paths, f, indent=4)
    except Exception as e:
        print(f"Warning: Failed to save installed agents config: {e}", file=sys.stderr)

def record_agent_installed(agent_dir_path):
    # Normalize path
    norm_path = os.path.abspath(agent_dir_path).replace("\\", "/")
    installed = load_installed_agents()
    # Normalize paths in list
    installed = [os.path.abspath(p).replace("\\", "/") for p in installed]
    if norm_path not in installed:
        installed.append(norm_path)
        save_installed_agents(installed)

def record_agent_uninstalled(agent_dir_path):
    norm_path = os.path.abspath(agent_dir_path).replace("\\", "/")
    installed = load_installed_agents()
    installed = [os.path.abspath(p).replace("\\", "/") for p in installed]
    if norm_path in installed:
        installed.remove(norm_path)
        save_installed_agents(installed)

def scan_agents():
    """Scans the local system for openclaw and hermes agents by searching for SOUL.md."""
    home_dir = os.path.expanduser("~")
    print("Scanning local system for agents...")
    
    hermes_path = os.path.join(home_dir, ".hermes")
    openclaw_path = os.path.join(home_dir, ".openclaw")
    
    detected = []
    
    # Helper to scan a directory
    def scan_dir(root_path):
        if not os.path.isdir(root_path):
            return []
        found_paths = []
        for root, dirs, files in os.walk(root_path):
            # Skip nested directories under workspaces/xxxx/home/ or profiles/xxxx/home/
            # to avoid picking up temp workspaces of agents.
            # To avoid matching the user's real home directory path on Linux (e.g. /home/carlos),
            # we strip the real home prefix before checking for "/home/".
            norm_root = root.replace("\\", "/")
            norm_home = home_dir.replace("\\", "/")
            relative_part = norm_root[len(norm_home):] if norm_root.startswith(norm_home) else norm_root
            if "/home/" in relative_part:
                continue
            if "SOUL.md" in files:
                full_path = os.path.join(root, "SOUL.md")
                norm_path = os.path.abspath(full_path).replace("\\", "/")
                found_paths.append(norm_path)
        return found_paths

    all_paths = scan_dir(hermes_path) + scan_dir(openclaw_path)
    
    escaped_home = re.escape(home_dir.replace("\\", "/"))
    patterns = [
        rf"^{escaped_home}/\.hermes/SOUL\.md$",
        rf"^{escaped_home}/\.hermes/profiles/([^/]+)/SOUL\.md$",
        rf"^{escaped_home}/\.openclaw/workspace/SOUL\.md$",
        rf"^{escaped_home}/\.openclaw/workspace\-front\-end/SOUL\.md$",
        rf"^{escaped_home}/\.openclaw/workspaces/([^/]+)/SOUL\.md$"
    ]
    
    for path in all_paths:
        matched = False
        agent_type = ""
        agent_name = ""
        
        # Check against patterns
        if re.match(patterns[0], path):
            matched = True
            agent_type = "Hermes"
            agent_name = "default (speculari)"
        elif m := re.match(patterns[1], path):
            matched = True
            agent_type = "Hermes"
            agent_name = m.group(1)
        elif re.match(patterns[2], path):
            matched = True
            agent_type = "OpenClaw"
            agent_name = "workspace"
        elif re.match(patterns[3], path):
            matched = True
            agent_type = "OpenClaw"
            agent_name = "workspace-front-end"
        elif m := re.match(patterns[4], path):
            matched = True
            agent_type = "OpenClaw"
            agent_name = m.group(1)
            
        if matched:
            agent_dir = os.path.dirname(path)
            detected.append({
                "type": agent_type,
                "name": agent_name,
                "soul_path": path,
                "dir_path": agent_dir
            })
            
    return detected

def merge_soul_content(target_content, template_content):
    begin_marker = "<!-- swda-begin -->"
    end_marker = "<!-- swda-end -->"
    
    # Check if template has block markers
    if begin_marker in template_content and end_marker in template_content:
        # 1. Extract frontmatter from template
        template_lines = template_content.splitlines()
        frontmatter_str = ""
        template_body = template_content
        if len(template_lines) > 0 and template_lines[0] == '---':
            idx = 1
            while idx < len(template_lines) and template_lines[idx] != '---':
                idx += 1
            if idx < len(template_lines):
                frontmatter_str = '\n'.join(template_lines[:idx+1]) + '\n'
                template_body = '\n'.join(template_lines[idx+1:])

        # 2. Extract swda block from template
        block_start = template_body.find(begin_marker)
        block_end = template_body.find(end_marker)
        template_block = template_body[block_start:block_end + len(end_marker)].strip()

        # 3. Extract preserved user identity from target
        target_lines = target_content.splitlines()
        target_body = target_content
        if len(target_lines) > 0 and target_lines[0] == '---':
            idx = 1
            while idx < len(target_lines) and target_lines[idx] != '---':
                idx += 1
            if idx < len(target_lines):
                target_body = '\n'.join(target_lines[idx+1:])

        # Clean target body from swda block or legacy FSM rules
        t_start = target_body.find(begin_marker)
        t_end = target_body.find(end_marker)
        if t_start != -1 and t_end != -1:
            user_identity = target_body[:t_start].strip() + "\n" + target_body[t_end + len(end_marker):].strip()
        else:
            # Legacy fallback for target content
            cleaned_target_body = []
            for line in target_body.splitlines():
                if line.strip().startswith('# 2. 核心運作原則') or line.strip().startswith('# 2. 認知合約'):
                    break
                cleaned_target_body.append(line)
            # Remove trailing separators/empty lines
            while cleaned_target_body and (cleaned_target_body[-1].strip() == '' or cleaned_target_body[-1].strip() == '---'):
                cleaned_target_body.pop()
            user_identity = '\n'.join(cleaned_target_body).strip()

        # 4. Reconstruct new SOUL.md content
        new_content = []
        if frontmatter_str:
            new_content.append(frontmatter_str.strip())
        if user_identity.strip():
            new_content.append(user_identity.strip())
        if template_block:
            new_content.append(template_block)
            
        return '\n\n'.join(new_content) + '\n'
        
    else:
        # --- LEGACY HEADER-BASED MERGE (Fallback for legacy templates/tests) ---
        template_lines = template_content.splitlines()
        frontmatter_lines = []
        template_body_lines = []
        
        if len(template_lines) > 0 and template_lines[0] == '---':
            idx = 1
            while idx < len(template_lines) and template_lines[idx] != '---':
                idx += 1
            if idx < len(template_lines):
                frontmatter_lines = template_lines[:idx+1]
                template_body_lines = template_lines[idx+1:]
            else:
                template_body_lines = template_lines
        else:
            template_body_lines = template_lines
            
        template_body = '\n'.join(template_body_lines)
        frontmatter_str = '\n'.join(frontmatter_lines)
        
        target_lines = target_content.splitlines()
        target_body_lines = []
        if len(target_lines) > 0 and target_lines[0] == '---':
            idx = 1
            while idx < len(target_lines) and target_lines[idx] != '---':
                idx += 1
            if idx < len(target_lines):
                target_body_lines = target_lines[idx+1:]
            else:
                target_body_lines = target_lines
        else:
            target_body_lines = target_lines
            
        target_body = '\n'.join(target_body_lines)
        has_system_identity = "# 1. 系統定位" in target_body
        
        cleaned_target_body = []
        if has_system_identity:
            for line in target_body_lines:
                if line.strip().startswith('# 2. 核心運作原則') or line.strip().startswith('# 2. 認知合約'):
                    break
                cleaned_target_body.append(line)
            preserved_identity = '\n'.join(cleaned_target_body).strip()
            
            body_start_idx = template_body.find('# 2. 認知合約與運行規範')
            if body_start_idx == -1:
                body_start_idx = template_body.find('# 2. 核心運作原則')
                
            if body_start_idx != -1:
                template_to_append = template_body[body_start_idx:]
            else:
                template_to_append = template_body
        else:
            for line in target_body_lines:
                if (line.strip().startswith('# 核心認知架構') or 
                    line.strip().startswith('# 1. 系統定位') or 
                    line.strip().startswith('# 核心認知架構 (The SOUL Framework)')):
                    break
                cleaned_target_body.append(line)
            preserved_identity = '\n'.join(cleaned_target_body).strip()
            
            body_start_idx = template_body.find('# 1. 系統定位')
            if body_start_idx != -1:
                template_to_append = template_body[body_start_idx:]
            else:
                template_to_append = template_body
                
        new_content = []
        if frontmatter_str:
            new_content.append(frontmatter_str)
        if preserved_identity:
            new_content.append(preserved_identity)
        
        new_content.append("\n---\n")
        new_content.append(template_to_append.strip())
        
        return '\n'.join(new_content) + '\n'

def uninstall_soul_content(soul_content):
    """Strips FSM rules and metadata links from SOUL.md content, keeping only the frontmatter and System Identity."""
    begin_marker = "<!-- swda-begin -->"
    end_marker = "<!-- swda-end -->"
    
    # 1. Separate frontmatter from body
    lines = soul_content.splitlines()
    frontmatter_str = ""
    body_str = soul_content
    if len(lines) > 0 and lines[0].strip() == '---':
        idx = 1
        while idx < len(lines) and lines[idx].strip() != '---':
            idx += 1
        if idx < len(lines):
            # Do not keep the 'related' section in uninstalled frontmatter
            frontmatter_lines = []
            frontmatter_lines.append(lines[0])
            in_related_block = False
            for f_idx in range(1, idx):
                line = lines[f_idx]
                stripped = line.strip()
                if stripped.startswith("related:") or stripped.startswith("related_skills:"):
                    in_related_block = True
                elif in_related_block and stripped.startswith("-"):
                    pass
                else:
                    in_related_block = False
                    frontmatter_lines.append(line)
            frontmatter_lines.append(lines[idx])
            frontmatter_str = '\n'.join(frontmatter_lines) + '\n'
            body_str = '\n'.join(lines[idx+1:])

    # 2. Strip swda block from body
    t_start = body_str.find(begin_marker)
    t_end = body_str.find(end_marker)
    if t_start != -1 and t_end != -1:
        cleaned_body = body_str[:t_start].strip() + "\n" + body_str[t_end + len(end_marker):].strip()
        
        new_content = []
        if frontmatter_str.strip():
            new_content.append(frontmatter_str.strip())
        if cleaned_body.strip():
            new_content.append(cleaned_body.strip())
        return '\n\n'.join(new_content) + '\n'
        
    else:
        # Fallback to legacy parser
        cleaned_lines = []
        if frontmatter_str:
            cleaned_lines.extend(frontmatter_str.splitlines())
            
        body_lines = body_str.splitlines()
        for line in body_lines:
            if line.strip().startswith('# 2. 核心運作原則') or line.strip().startswith('# 2. 認知合約'):
                break
            cleaned_lines.append(line)
            
        while cleaned_lines and (cleaned_lines[-1].strip() == '' or cleaned_lines[-1].strip() == '---'):
            cleaned_lines.pop()
            
        return '\n'.join(cleaned_lines).strip() + '\n'


def create_new_agent(name, agent_type, identity, template_versions, yes_bypass):
    """Creates a new agent profile/workspace directory and installs the SWDA workflow files."""
    if not re.match(r"^[a-zA-Z0-9_\-]+$", name):
        print(f"Error: Invalid agent name '{name}'. Only alphanumeric characters, underscores, and hyphens are allowed.", file=sys.stderr)
        sys.exit(1)
        
    home_dir = os.path.expanduser("~")
    
    if agent_type.lower() == "hermes":
        dest_dir = os.path.join(home_dir, ".hermes", "profiles", name)
    else:
        dest_dir = os.path.join(home_dir, ".openclaw", "workspaces", name)
        
    soul_dest_path = os.path.join(dest_dir, "SOUL.md")
    rule_dest_path = os.path.join(dest_dir, "RULE.md")
    skill_dir_path = os.path.join(dest_dir, "skills", "swarm")
    skill_dest_path = os.path.join(skill_dir_path, "SKILL.md")
    
    if os.path.exists(soul_dest_path):
        print(f"Error: Agent workspace '{name}' already exists at: {dest_dir} (found SOUL.md)", file=sys.stderr)
        sys.exit(1)
        
    print(f"\nCreating new {agent_type} agent:")
    print(f"  Name: {name}")
    print(f"  Path: {dest_dir}")
    
    if not identity:
        if yes_bypass:
            identity = "你是一個全能的智慧 Agent，旨在協同執行軟體工程任務與狀態運作。"
        else:
            print("\nEnter System Identity / 定位 for the new agent (press Enter for default):")
            input_identity = input("> ").strip()
            identity = input_identity if input_identity else "你是一個全能的智慧 Agent，旨在協同執行軟體工程任務與狀態運作。"
            
    print(f"  System Identity: {identity}")
    
    if not yes_bypass:
        confirm = input("\nProceed with creation? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Cancelled.")
            sys.exit(0)
            
    print(f"\n -> Initializing directory: {dest_dir}...")
    os.makedirs(skill_dir_path, exist_ok=True)
    
    print(" -> Creating SOUL.md...")
    try:
        with open(SOUL_TEMPLATE, 'r', encoding='utf-8') as f:
            template_content = f.read()
    except Exception as e:
        print(f"Error: Failed to read SOUL.md template: {e}", file=sys.stderr)
        sys.exit(1)
        
    initial_soul = f"# 1. 系統定位 (System Identity)\n{identity}\n"
    merged_soul = merge_soul_content(initial_soul, template_content)
    
    try:
        with open(soul_dest_path, 'w', encoding='utf-8') as f:
            f.write(merged_soul)
        print(f"    Created SOUL.md (v{template_versions['SOUL.md']})")
    except Exception as e:
        print(f"Error: Failed to write SOUL.md: {e}", file=sys.stderr)
        sys.exit(1)
        
    print(" -> Creating RULE.md...")
    try:
        with open(RULE_SOURCE, 'r', encoding='utf-8') as f:
            rule_content = f.read()
        rule_content = rule_content.replace("file:///Users/carlos/cwork/Brian_Notes/PC/Knowhow/agent/skills/Swarm_Driven_Development.md", "skills/swarm/SKILL.md")
        with open(rule_dest_path, 'w', encoding='utf-8') as f:
            f.write(rule_content)
        print(f"    Created RULE.md (v{template_versions['RULE.md']})")
    except Exception as e:
        print(f"Error: Failed to write RULE.md: {e}", file=sys.stderr)
        sys.exit(1)
        
    print(" -> Creating SKILL.md...")
    try:
        shutil.copy2(SKILL_SOURCE, skill_dest_path)
        print(f"    Created SKILL.md (v{template_versions['SKILL.md']})")
    except Exception as e:
        print(f"Error: Failed to copy SKILL.md: {e}", file=sys.stderr)
        sys.exit(1)
        
    print(f"\nSuccessfully created and installed SWDA workflow for new agent: {name}!")
    record_agent_installed(dest_dir)

def upgrade_swda():
    """Performs self-upgrade of swda CLI by pulling from git and re-installing."""
    import subprocess
    import sys
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print("="*60)
    print("             Self-Upgrading swda CLI Tool")
    print("="*60)
    print(f"Repository directory: {script_dir}\n")
    
    # 1. Run git pull
    print(" -> Pulling latest changes from git remote...")
    try:
        result = subprocess.run(["git", "pull"], cwd=script_dir, capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"Error pulling from git:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Failed to execute git pull: {e}", file=sys.stderr)
        sys.exit(1)
        
    # 2. Re-install using pip in editable mode
    print(" -> Re-installing the package...")
    
    # Check if pip is available
    has_pip = True
    try:
        pip_check = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, text=True)
        if pip_check.returncode != 0:
            has_pip = False
    except Exception:
        has_pip = False
        
    if not has_pip:
        if "pipx" in sys.executable:
            pipx_path = shutil.which("pipx")
            if pipx_path:
                print(" -> Missing 'pip' inside the virtualenv. Trying 'pipx reinstall swda' as fallback...")
                try:
                    result = subprocess.run([pipx_path, "reinstall", "swda"])
                    if result.returncode == 0:
                        print("\nswda upgraded successfully via pipx!")
                        sys.exit(0)
                except Exception as e:
                    print(f"Failed to run pipx reinstall: {e}", file=sys.stderr)
                    
        print("\n[Error] Python environment is missing the 'pip' module.", file=sys.stderr)
        if "pipx" in sys.executable:
            print("This happens because swda was installed via pipx, which prunes pip by default.", file=sys.stderr)
            print("Please run the following command in your terminal to fix this:", file=sys.stderr)
            print("  pipx inject swda pip", file=sys.stderr)
            print("Then try 'swda update' again.\n", file=sys.stderr)
        else:
            print("Please install pip in your current Python environment.\n", file=sys.stderr)
        sys.exit(1)
        
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], cwd=script_dir, capture_output=True, text=True)
        if result.returncode != 0:
            if "externally-managed-environment" in result.stderr or "break-system-packages" in result.stderr:
                print(" -> Retrying with --break-system-packages...")
                result = subprocess.run([sys.executable, "-m", "pip", "install", "--break-system-packages", "-e", "."], cwd=script_dir, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("\nswda upgraded successfully!")
            sys.exit(0)
        else:
            print(f"Error during package re-installation:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Failed to run pip install: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    import argparse
    
    # Pre-process arguments for subcommand mapping & backward compatibility
    if len(sys.argv) > 1:
        first_arg = sys.argv[1]
        known_commands = {"install", "doctor", "update", "-h", "--help"}
        if first_arg not in known_commands:
            if first_arg in {"-c", "--check"}:
                # Map old --check or -c to doctor command
                sys.argv[1] = "doctor"
            else:
                # Default to install command
                sys.argv.insert(1, "install")

    parser = argparse.ArgumentParser(description="Universal Swarm-Driven Agent (SWDA) CLI Tool (swda)")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # Install sub-command
    install_parser = subparsers.add_parser("install", help="Install or update SWDA workflow on agents.")
    install_parser.add_argument("agents", nargs="?", help="Comma-separated list of agent names (e.g. xuandao,finance). Runs in interactive mode if omitted.")
    install_parser.add_argument("-y", "--yes", action="store_true", help="Bypass confirmation prompt.")
    install_parser.add_argument("-u", "--uninstall", action="store_true", help="Uninstall SWDA workflow from selected agents.")
    install_parser.add_argument("--create", help="Create a new agent with the specified name and install the SWDA workflow.")
    install_parser.add_argument("--type", choices=["hermes", "openclaw"], default="openclaw", help="The type of agent to create (default: openclaw).")
    install_parser.add_argument("--identity", help="The system identity description of the new agent.")

    # Update sub-command (Self-upgrade or update agents)
    update_parser = subparsers.add_parser("update", help="Self-upgrade swda or update specific agents.")
    update_parser.add_argument("--agents", nargs="?", const="_interactive_", help="Update specified agents (comma-separated) or prompt for interactive selection if no agents are specified.")
    update_parser.add_argument("-y", "--yes", action="store_true", help="Bypass confirmation prompt.")
    update_parser.add_argument("-u", "--uninstall", action="store_true", help="Uninstall SWDA workflow from selected agents.")

    # Doctor sub-command
    doctor_parser = subparsers.add_parser("doctor", help="Check agent status and optionally fix mismatches.")
    doctor_parser.add_argument("--fix", action="store_true", help="Automatically fix/upgrade agent rules and schemas.")
    doctor_parser.add_argument("-y", "--yes", action="store_true", help="Bypass confirmation prompt when fixing.")

    args = parser.parse_args()

    # If no command is provided, default to install (interactive mode)
    if not args.command:
        args.command = "install"
        args.agents = None
        args.yes = False
        args.uninstall = False
        args.create = None
        args.type = "openclaw"
        args.identity = None

    # Map command behaviors to old variables for minimal code churn:
    if args.command == "doctor":
        if args.fix:
            args.check = False
            args.agents = ["all"]
            args.uninstall = False
        else:
            args.check = True
            args.agents = []
            args.uninstall = False
            args.yes = False
    elif args.command == "update" and args.agents is None:
        # Self-upgrade swda itself
        upgrade_swda()
    else:
        # install command, or update command with --agents specified
        args.check = False
        if args.agents and args.agents != "_interactive_":
            args.agents = [t.strip() for t in args.agents.split(",") if t.strip()]
        else:
            args.agents = []

    # Safe default fallback for attributes not defined by the active subparser
    if not hasattr(args, "create"):
        args.create = None
    if not hasattr(args, "type"):
        args.type = "openclaw"
    if not hasattr(args, "identity"):
        args.identity = None


    print("="*60)
    print("       Swarm-Driven Agent (SWDA) Workflow Installer")
    print("="*60)
    
    # Verify local sources exist in the root directory
    for path in [SOUL_TEMPLATE, RULE_SOURCE, SKILL_SOURCE]:
        if not os.path.exists(path):
            print(f"Error: Required source file {path} not found in the root directory.", file=sys.stderr)
            sys.exit(1)
            
    # Extract template versions
    template_versions = {
        "SOUL.md": extract_version(SOUL_TEMPLATE),
        "RULE.md": extract_version(RULE_SOURCE),
        "SKILL.md": extract_version(SKILL_SOURCE)
    }
    
    if args.create:
        create_new_agent(args.create, args.type, args.identity, template_versions, args.yes)
        sys.exit(0)
        
    agents = scan_agents()
    if args.command == "doctor":
        installed_paths = load_installed_agents(agents)
        # Normalize installed paths to absolute paths with forward slashes for matching
        installed_paths = [os.path.abspath(p).replace("\\", "/") for p in installed_paths]
        agents = [a for a in agents if os.path.abspath(a['dir_path']).replace("\\", "/") in installed_paths]
        if not agents:
            print("No installed agents tracked. Run 'swda install' to install on an agent.")
            sys.exit(0)
    elif not agents:
        print("No openclaw or hermes agents found on the local machine.")
        sys.exit(0)
        
    # Get status for all agents
    agent_statuses = []
    for agent in agents:
        status_info = get_agent_status(agent, template_versions)
        agent_statuses.append(status_info)
        
    # Print status list
    print(f"\nDetected {len(agents)} agents:")
    for idx, (agent, status_info) in enumerate(zip(agents, agent_statuses), start=1):
        print(f" [{idx}] Type: {agent['type']:<8} | Name: {agent['name']:<20}")
        print(f"     Status:  {status_info['status']}")
        
        # Format details
        soul_detail = f"{status_info['soul_ver'] or 'missing'} -> {template_versions['SOUL.md']}" if status_info['soul_status'] == 'update' else f"{status_info['soul_ver']}"
        rule_detail = f"{status_info['rule_ver'] or 'missing'} -> {template_versions['RULE.md']}" if status_info['rule_status'] in ('update', 'missing') else f"{status_info['rule_ver']}"
        skill_detail = f"{status_info['skill_ver'] or 'missing'} -> {template_versions['SKILL.md']}" if status_info['skill_status'] in ('update', 'missing') else f"{status_info['skill_ver']}"
        
        print(f"     Details: SOUL: {soul_detail} | RULE: {rule_detail} | SKILL: {skill_detail}")
        print(f"     Path:    {agent['dir_path']}\n")
        
    if args.check:
        print("Check completed.")
        sys.exit(0)
        
    selected_indices = []
    
    if args.agents:
        # Match agents specified in command line arguments
        if len(args.agents) == 1 and args.agents[0].lower() == "all":
            selected_indices = list(range(len(agents)))
        else:
            for term in args.agents:
                term_lower = term.lower()
                found = False
                # 1. Try exact name match or exact type:name match
                for i, agent in enumerate(agents):
                    name_lower = agent['name'].lower()
                    full_id = f"{agent['type'].lower()}:{name_lower}"
                    if term_lower == name_lower or term_lower == full_id:
                        if i not in selected_indices:
                            selected_indices.append(i)
                        found = True
                
                if not found:
                    # 2. Try substring match on name
                    for i, agent in enumerate(agents):
                        name_lower = agent['name'].lower()
                        if term_lower in name_lower:
                            if i not in selected_indices:
                                selected_indices.append(i)
                            found = True
                            
                if not found:
                    print(f"Error: No agent found matching '{term}'.", file=sys.stderr)
                    sys.exit(1)
    else:
        # Interactive mode
        action_verb = "uninstall" if args.uninstall else "install/update"
        print(f"Select agents to {action_verb} SWDA workflow:")
        print("  Enter comma-separated numbers (e.g. 1,3,4)")
        print("  Enter 'all' to select all agents")
        print("  Enter 'q' to quit")
        
        selection = input("\nYour choice: ").strip()
        if selection.lower() == 'q' or not selection:
            print("Cancelled.")
            sys.exit(0)
            
        if selection.lower() == 'all':
            selected_indices = list(range(len(agents)))
        else:
            try:
                parts = selection.split(",")
                for part in parts:
                    idx = int(part.strip()) - 1
                    if 0 <= idx < len(agents):
                        selected_indices.append(idx)
                    else:
                        print(f"Warning: Invalid index {part.strip()} ignored.")
            except ValueError:
                print("Invalid input format.")
                sys.exit(1)
                
    if not selected_indices:
        print("No valid agents selected.")
        sys.exit(0)
        
    action_noun = "uninstallation" if args.uninstall else "installation/upgrade"
    print(f"\nYou selected {len(selected_indices)} agent(s) for {action_noun}:")
    for idx in selected_indices:
        agent = agents[idx]
        status_info = agent_statuses[idx]
        print(f"  - {agent['name']} ({agent['type']}) [{status_info['status']}]")
        
    if args.yes:
        confirm = 'y'
    else:
        confirm = input(f"\nProceed with {action_noun}? (y/n): ").strip().lower()
        
    if confirm != 'y':
        print("Cancelled.")
        sys.exit(0)
        
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for idx in selected_indices:
        agent = agents[idx]
        status_info = agent_statuses[idx]
        
        if args.uninstall:
            print(f"\nUninstalling SWDA from: {agent['name']} ({agent['type']})")
            
            # 1. Back up target SOUL.md
            print(" -> Backing up SOUL.md...")
            soul_bak_path = f"{agent['soul_path']}.{timestamp}.bak"
            try:
                shutil.copy2(agent['soul_path'], soul_bak_path)
            except Exception as e:
                print(f"    Failed to backup SOUL.md: {e}")
                continue
                
            # 2. Back up target RULE.md if it exists
            rule_dest_path = os.path.join(agent['dir_path'], "RULE.md")
            if os.path.exists(rule_dest_path):
                print(" -> Backing up RULE.md...")
                rule_bak_path = f"{rule_dest_path}.{timestamp}.bak"
                try:
                    shutil.copy2(rule_dest_path, rule_bak_path)
                except Exception as e:
                    print(f"    Failed to backup RULE.md: {e}")
            
            # 3. Revert SOUL.md content
            print(" -> Reverting SOUL.md...")
            try:
                with open(agent['soul_path'], 'r', encoding='utf-8') as f:
                    content = f.read()
                reverted_content = uninstall_soul_content(content)
                with open(agent['soul_path'], 'w', encoding='utf-8') as f:
                    f.write(reverted_content)
                print("    SOUL.md rules stripped.")
            except Exception as e:
                print(f"    Failed to revert SOUL.md: {e}")
                
            # 4. Remove RULE.md
            if os.path.exists(rule_dest_path):
                print(" -> Removing RULE.md...")
                try:
                    os.remove(rule_dest_path)
                    print("    RULE.md removed.")
                except Exception as e:
                    print(f"    Failed to remove RULE.md: {e}")
                    
            # 5. Remove SKILL.md
            skill_dir_path = os.path.join(agent['dir_path'], "skills", "swarm")
            skill_dest_path = os.path.join(skill_dir_path, "SKILL.md")
            if os.path.exists(skill_dest_path):
                print(" -> Removing SKILL.md...")
                try:
                    os.remove(skill_dest_path)
                    print("    SKILL.md removed.")
                except Exception as e:
                    print(f"    Failed to remove SKILL.md: {e}")
                    
            # 6. Clean up directories if empty
            if os.path.exists(skill_dir_path) and not os.listdir(skill_dir_path):
                try:
                    os.rmdir(skill_dir_path)
                    print("    Removed empty skills/swarm directory.")
                except Exception:
                    pass
            skills_parent_dir = os.path.join(agent['dir_path'], "skills")
            if os.path.exists(skills_parent_dir) and not os.listdir(skills_parent_dir):
                try:
                    os.rmdir(skills_parent_dir)
                    print("    Removed empty skills directory.")
                except Exception:
                    pass
                    
            print(f" Successfully uninstalled SWDA from: {agent['name']}")
            record_agent_uninstalled(agent['dir_path'])
            
        else:
            print(f"\nInstalling/Upgrading SWDA for: {agent['name']} ({agent['type']})")
            
            # 1. Back up target SOUL.md
            print(" -> Backing up SOUL.md...")
            soul_bak_path = f"{agent['soul_path']}.{timestamp}.bak"
            try:
                shutil.copy2(agent['soul_path'], soul_bak_path)
            except Exception as e:
                print(f"    Failed to backup SOUL.md: {e}")
                continue
                
            # 2. Back up target RULE.md if it exists
            rule_dest_path = os.path.join(agent['dir_path'], "RULE.md")
            if os.path.exists(rule_dest_path):
                print(" -> Backing up RULE.md...")
                rule_bak_path = f"{rule_dest_path}.{timestamp}.bak"
                try:
                    shutil.copy2(rule_dest_path, rule_bak_path)
                except Exception as e:
                    print(f"    Failed to backup RULE.md: {e}")
                
            # 3. Merge SOUL.md
            print(" -> Preparing SOUL.md...")
            try:
                with open(agent['soul_path'], 'r', encoding='utf-8') as f:
                    target_content = f.read()
            except Exception as e:
                print(f"    Failed to read target SOUL.md: {e}, skipping.")
                continue
                
            try:
                with open(SOUL_TEMPLATE, 'r', encoding='utf-8') as f:
                    template_content = f.read()
            except Exception as e:
                print(f"    Failed to read SOUL.md template: {e}, skipping.")
                continue
                
            merged_content = merge_soul_content(target_content, template_content)
            
            # Write merged SOUL.md
            print(" -> Writing new SOUL.md...")
            try:
                with open(agent['soul_path'], 'w', encoding='utf-8') as f:
                    f.write(merged_content)
                # Log version upgrade
                old_ver = status_info['soul_ver'] or "missing"
                new_ver = template_versions['SOUL.md']
                print(f"    SOUL.md: {old_ver} -> {new_ver}")
            except Exception as e:
                print(f"    Failed to write SOUL.md: {e}")
                continue
            
            # 4. Copy RULE.md
            print(" -> Copying RULE.md...")
            try:
                with open(RULE_SOURCE, 'r', encoding='utf-8') as f:
                    rule_content = f.read()
                rule_content = rule_content.replace("file:///Users/carlos/cwork/Brian_Notes/PC/Knowhow/agent/skills/Swarm_Driven_Development.md", "skills/swarm/SKILL.md")
                with open(rule_dest_path, 'w', encoding='utf-8') as f:
                    f.write(rule_content)
                # Log version upgrade
                old_ver = status_info['rule_ver'] or "missing"
                new_ver = template_versions['RULE.md']
                print(f"    RULE.md: {old_ver} -> {new_ver}")
            except Exception as e:
                print(f"    Failed to write RULE.md: {e}")
                continue
            
            # 5. Copy Swarm Meta-skill (SKILL.md)
            print(" -> Creating skills/swarm directory...")
            skill_dir_path = os.path.join(agent['dir_path'], "skills", "swarm")
            os.makedirs(skill_dir_path, exist_ok=True)
            
            print(" -> Copying SKILL.md...")
            skill_dest_path = os.path.join(skill_dir_path, "SKILL.md")
            try:
                shutil.copy2(SKILL_SOURCE, skill_dest_path)
                # Log version upgrade
                old_ver = status_info['skill_ver'] or "missing"
                new_ver = template_versions['SKILL.md']
                print(f"    SKILL.md: {old_ver} -> {new_ver}")
            except Exception as e:
                print(f"    Failed to copy SKILL.md: {e}")
                continue
                
            print(f" Successfully installed/upgraded SWDA for: {agent['name']}")
            record_agent_installed(agent['dir_path'])
            
    print("\nAll done!")

if __name__ == '__main__':
    main()
