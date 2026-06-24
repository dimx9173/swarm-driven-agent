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
        # Split at "# 2. 核心運作原則"
        for line in target_body_lines:
            if line.strip().startswith('# 2. 核心運作原則'):
                break
            cleaned_target_body.append(line)
        preserved_identity = '\n'.join(cleaned_target_body).strip()
        
        # Extract template body starting from "# 2. 核心運作原則"
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

def main():
    print("="*60)
    print("       Swarm-Driven Agent (SDA) Workflow Installer")
    print("="*60)
    
    # Verify local sources exist in the root directory
    for path in [SOUL_TEMPLATE, RULE_SOURCE, SKILL_SOURCE]:
        if not os.path.exists(path):
            print(f"Error: Required source file {path} not found in the root directory.", file=sys.stderr)
            sys.exit(1)
            
    agents = scan_agents()
    if not agents:
        print("No openclaw or hermes agents found on the local machine.")
        sys.exit(0)
        
    print(f"\nDetected {len(agents)} agents:")
    for idx, agent in enumerate(agents, start=1):
        print(f" [{idx}] Type: {agent['type']:<8} | Name: {agent['name']:<20} | Path: {agent['dir_path']}")
        
    print("\nSelect agents to install SDA workflow:")
    print("  Enter comma-separated numbers (e.g. 1,3,4)")
    print("  Enter 'all' to select all agents")
    print("  Enter 'q' to quit")
    
    selection = input("\nYour choice: ").strip()
    if selection.lower() == 'q' or not selection:
        print("Cancelled.")
        sys.exit(0)
        
    selected_indices = []
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
        
    print(f"\nYou selected {len(selected_indices)} agent(s) for installation.")
    confirm = input("Proceed with installation? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        sys.exit(0)
        
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for idx in selected_indices:
        agent = agents[idx]
        print(f"\nInstalling SDA to: {agent['name']} ({agent['type']})")
        
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
        except Exception as e:
            print(f"    Failed to write SOUL.md: {e}")
            continue
        
        # 4. Copy RULE.md
        print(" -> Copying RULE.md...")
        try:
            with open(RULE_SOURCE, 'r', encoding='utf-8') as f:
                rule_content = f.read()
            # Replace local path with relative skill path
            rule_content = rule_content.replace("file:///Users/carlos/cwork/Brian_Notes/PC/Knowhow/agent/skills/Swarm_Driven_Development.md", "skills/swarm/SKILL.md")
            with open(rule_dest_path, 'w', encoding='utf-8') as f:
                f.write(rule_content)
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
        except Exception as e:
            print(f"    Failed to copy SKILL.md: {e}")
            continue
            
        print(f" Successfully installed SDA to: {agent['name']}")
        
    print("\nAll done!")

if __name__ == '__main__':
    main()
