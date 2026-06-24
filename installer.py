#!/usr/bin/env python3
import sys
import os
import re
import shutil
import datetime

# Determine local script paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SOUL_TEMPLATE = os.path.join(SCRIPT_DIR, "SOUL.md")
RULE_SOURCE = os.path.join(SCRIPT_DIR, "RULE.md")
SKILL_SOURCE = os.path.join(SCRIPT_DIR, "SKILL.md")

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
        if len(lines) > 0 and lines[0].strip() == '---':
            idx = 1
            while idx < len(lines) and lines[idx].strip() != '---':
                line = lines[idx].strip()
                if line.startswith('version:'):
                    val = line.split(':', 1)[1].strip()
                    val = val.strip('"').strip("'")
                    return val
                idx += 1
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
            # to avoid picking up temp workspaces of agents
            norm_root = root.replace("\\", "/")
            if "/home/" in norm_root:
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
    
    # Replace the local path in template frontmatter with relative path
    frontmatter_str = '\n'.join(frontmatter_lines)
    frontmatter_str = frontmatter_str.replace("file:///Users/carlos/cwork/Brian_Notes/PC/Knowhow/agent/skills/Swarm_Driven_Development.md", "skills/swarm/SKILL.md")
    
    # Parse target_content and strip existing frontmatter & FSM rules
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
        # Split at "# 2. 核心運作原則" or "# 2. 認知合約"
        for line in target_body_lines:
            if line.strip().startswith('# 2. 核心運作原則') or line.strip().startswith('# 2. 認知合約'):
                break
            cleaned_target_body.append(line)
        preserved_identity = '\n'.join(cleaned_target_body).strip()
        
        # Extract template body starting from "# 2. 認知合約" or "# 2. 核心運作原則"
        body_start_idx = template_body.find('# 2. 認知合約與運行規範')
        if body_start_idx == -1:
            body_start_idx = template_body.find('# 2. 核心運作原則')
            
        if body_start_idx != -1:
            template_to_append = template_body[body_start_idx:]
        else:
            template_to_append = template_body
    else:
        # Split at "# 核心認知架構" or "# 1. 系統定位" or "# 核心認知架構 (The SOUL Framework)"
        for line in target_body_lines:
            if (line.strip().startswith('# 核心認知架構') or 
                line.strip().startswith('# 1. 系統定位') or 
                line.strip().startswith('# 核心認知架構 (The SOUL Framework)')):
                break
            cleaned_target_body.append(line)
        preserved_identity = '\n'.join(cleaned_target_body).strip()
        
        # Extract entire template body starting from "# 1. 系統定位"
        body_start_idx = template_body.find('# 1. 系統定位')
        if body_start_idx != -1:
            template_to_append = template_body[body_start_idx:]
        else:
            template_to_append = template_body
            
    # Combine
    new_content = []
    if frontmatter_str:
        new_content.append(frontmatter_str)
    if preserved_identity:
        new_content.append(preserved_identity)
    
    new_content.append("\n---\n")
    new_content.append(template_to_append.strip())
    
    return '\n'.join(new_content) + '\n'

def create_new_agent(name, agent_type, identity, template_versions, yes_bypass):
    """Creates a new agent profile/workspace directory and installs the SDA workflow files."""
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
        
    print(f"\nSuccessfully created and installed SDA workflow for new agent: {name}!")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Universal Swarm-Driven Agent (SDA) Workflow Installer")
    parser.add_argument("agents", nargs="*", help="Names of agents to install (e.g. xuandao finance). Runs in interactive mode if omitted.")
    parser.add_argument("-y", "--yes", action="store_true", help="Bypass confirmation prompt.")
    parser.add_argument("-c", "--check", action="store_true", help="Check and print agent status without installing.")
    parser.add_argument("--create", help="Create a new agent with the specified name and install the SDA workflow.")
    parser.add_argument("--type", choices=["hermes", "openclaw"], default="openclaw", help="The type of agent to create (default: openclaw).")
    parser.add_argument("--identity", help="The system identity description of the new agent.")
    args = parser.parse_args()

    print("="*60)
    print("       Swarm-Driven Agent (SDA) Workflow Installer")
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
    if not agents:
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
        print("Select agents to install/update SDA workflow:")
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
        
    print(f"\nYou selected {len(selected_indices)} agent(s) for installation/upgrade:")
    for idx in selected_indices:
        agent = agents[idx]
        status_info = agent_statuses[idx]
        print(f"  - {agent['name']} ({agent['type']}) [{status_info['status']}]")
        
    if args.yes:
        confirm = 'y'
    else:
        confirm = input("\nProceed with installation/upgrade? (y/n): ").strip().lower()
        
    if confirm != 'y':
        print("Cancelled.")
        sys.exit(0)
        
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for idx in selected_indices:
        agent = agents[idx]
        status_info = agent_statuses[idx]
        print(f"\nInstalling/Upgrading SDA for: {agent['name']} ({agent['type']})")
        
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
            
        print(f" Successfully installed/upgraded SDA for: {agent['name']}")
        
    print("\nAll done!")

if __name__ == '__main__':
    main()
