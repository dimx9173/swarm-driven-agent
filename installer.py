#!/usr/bin/env python3
import sys
import subprocess
import os
import re
import tempfile
import datetime

REMOTE_USER_HOST = "brian@46.224.196.164"

# Local paths
SOUL_TEMPLATE = "/Users/carlos/cwork/Brian_Notes/PC/Knowhow/agent/SOUL.md"
RULE_SOURCE = "/Users/carlos/cwork/Brian_Notes/PC/Knowhow/agent/RULE.md"
SKILL_SOURCE = "/Users/carlos/cwork/Brian_Notes/PC/Knowhow/agent/skills/Swarm_Driven_Development.md"
XUANDAO_SOUL = "/Users/carlos/cwork/Brian_Notes/PC/Knowhow/agent/hermes/46.224.196.164_xuandao_SOUL.md"
SPECULARI_SOUL = "/Users/carlos/cwork/Brian_Notes/PC/Knowhow/agent/hermes/46.224.196.164_speculari_SOUL.md"

def run_ssh_command(cmd, quiet=False):
    """Executes a command on the remote server via SSH."""
    full_cmd = ["ssh", REMOTE_USER_HOST, cmd]
    res = subprocess.run(full_cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0 and not quiet:
        print(f"Error executing remote command: {cmd}\nStderr: {res.stderr.strip()}", file=sys.stderr)
    return res.returncode, res.stdout, res.stderr

def scp_to_remote(local_path, remote_path):
    """Copies a local file to the remote server using SCP."""
    full_cmd = ["scp", local_path, f"{REMOTE_USER_HOST}:{remote_path}"]
    res = subprocess.run(full_cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"Error copying {local_path} to remote {remote_path}\nStderr: {res.stderr.strip()}", file=sys.stderr)
    return res.returncode

def scp_from_remote(remote_path, local_path):
    """Copies a remote file to the local machine using SCP."""
    full_cmd = ["scp", f"{REMOTE_USER_HOST}:{remote_path}", local_path]
    res = subprocess.run(full_cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"Error copying remote {remote_path} to local {local_path}\nStderr: {res.stderr.strip()}", file=sys.stderr)
    return res.returncode

def scan_agents():
    """Scans the remote server for openclaw and hermes agents by searching for SOUL.md."""
    print("Scanning remote server for agents (finding SOUL.md files)...")
    # Search under ~/.hermes and ~/.openclaw
    ret, stdout, stderr = run_ssh_command("find ~/.hermes ~/.openclaw -name SOUL.md 2>/dev/null")
    if ret != 0:
        print("Failed to scan remote directories.", file=sys.stderr)
        return []
    
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    
    # We want to match:
    # 1. ~/.hermes/SOUL.md
    # 2. ~/.hermes/profiles/<profile_name>/SOUL.md
    # 3. ~/.openclaw/workspace/SOUL.md
    # 4. ~/.openclaw/workspace-front-end/SOUL.md
    # 5. ~/.openclaw/workspaces/<workspace_name>/SOUL.md
    
    # We will match both '/home/brian/.xxx' and '~/.xxx'
    # Remote home directory is /home/brian
    patterns = [
        r"^/home/brian/\.hermes/SOUL\.md$",
        r"^/home/brian/\.hermes/profiles/([^/]+)/SOUL\.md$",
        r"^/home/brian/\.openclaw/workspace/SOUL\.md$",
        r"^/home/brian/\.openclaw/workspace-front-end/SOUL\.md$",
        r"^/home/brian/\.openclaw/workspaces/([^/]+)/SOUL\.md$"
    ]
    
    detected = []
    for line in lines:
        matched = False
        agent_type = ""
        agent_name = ""
        
        # Check against patterns
        if re.match(patterns[0], line):
            matched = True
            agent_type = "Hermes"
            agent_name = "default (speculari)"
        elif m := re.match(patterns[1], line):
            matched = True
            agent_type = "Hermes"
            agent_name = m.group(1)
        elif re.match(patterns[2], line):
            matched = True
            agent_type = "OpenClaw"
            agent_name = "workspace"
        elif re.match(patterns[3], line):
            matched = True
            agent_type = "OpenClaw"
            agent_name = "workspace-front-end"
        elif m := re.match(patterns[4], line):
            matched = True
            agent_type = "OpenClaw"
            agent_name = m.group(1)
            
        if matched:
            agent_dir = os.path.dirname(line)
            detected.append({
                "type": agent_type,
                "name": agent_name,
                "soul_path": line,
                "dir_path": agent_dir
            })
            
    return detected

def merge_soul_content(remote_content, template_content):
    # Parse template_content
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
    body_start_idx = template_body.find('# 1. 系統定位')
    if body_start_idx != -1:
        template_body_content = template_body[body_start_idx:]
    else:
        template_body_content = template_body
        
    # Replace the local path in template frontmatter with relative path
    frontmatter_str = '\n'.join(frontmatter_lines)
    frontmatter_str = frontmatter_str.replace("file:///Users/carlos/cwork/Brian_Notes/PC/Knowhow/agent/skills/Swarm_Driven_Development.md", "skills/swarm/SKILL.md")
    
    # Parse remote_content and strip existing frontmatter & SDA sections
    remote_lines = remote_content.splitlines()
    remote_body_lines = []
    if len(remote_lines) > 0 and remote_lines[0] == '---':
        idx = 1
        while idx < len(remote_lines) and remote_lines[idx] != '---':
            idx += 1
        if idx < len(remote_lines):
            remote_body_lines = remote_lines[idx+1:]
        else:
            remote_body_lines = remote_lines
    else:
        remote_body_lines = remote_lines
        
    cleaned_remote_body = []
    for line in remote_body_lines:
        if line.strip().startswith('# 核心認知架構') or line.strip().startswith('# 1. 系統定位') or line.strip().startswith('# 核心認知架構 (The SOUL Framework)'):
            break
        cleaned_remote_body.append(line)
        
    preserved_identity = '\n'.join(cleaned_remote_body).strip()
    
    # Combine
    new_content = []
    if frontmatter_str:
        new_content.append(frontmatter_str)
    if preserved_identity:
        new_content.append(preserved_identity)
    
    new_content.append("\n---\n")
    new_content.append(template_body_content.strip())
    
    return '\n'.join(new_content) + '\n'

def main():
    print("="*60)
    print("       Swarm-Driven Agent (SDA) Workflow Installer")
    print("="*60)
    
    # Check local sources
    for path in [SOUL_TEMPLATE, RULE_SOURCE, SKILL_SOURCE]:
        if not os.path.exists(path):
            print(f"Error: Local file {path} not found. Make sure Brian_Notes repository is mounted/present.", file=sys.stderr)
            sys.exit(1)
            
    agents = scan_agents()
    if not agents:
        print("No openclaw or hermes agents found on the remote server.")
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
        
        # 1. Back up remote SOUL.md
        print(" -> Backing up remote SOUL.md...")
        soul_bak_path = f"{agent['soul_path']}.{timestamp}.bak"
        ret, _, stderr = run_ssh_command(f"cp {agent['soul_path']} {soul_bak_path}")
        if ret != 0:
            print(f"    Failed to backup SOUL.md: {stderr.strip()}")
            continue
            
        # 2. Back up remote RULE.md if it exists
        rule_remote_path = f"{agent['dir_path']}/RULE.md"
        # Check if RULE.md exists
        ret_check, _, _ = run_ssh_command(f"test -f {rule_remote_path}", quiet=True)
        if ret_check == 0:
            print(" -> Backing up remote RULE.md...")
            rule_bak_path = f"{rule_remote_path}.{timestamp}.bak"
            run_ssh_command(f"cp {rule_remote_path} {rule_bak_path}")
            
        # 3. Determine SOUL.md update strategy
        print(" -> Preparing SOUL.md...")
        local_soul_source = None
        if agent['type'] == 'Hermes' and agent['name'] == 'xuandao':
            local_soul_source = XUANDAO_SOUL
        elif agent['type'] == 'Hermes' and agent['name'] == 'default (speculari)':
            local_soul_source = SPECULARI_SOUL
            
        if local_soul_source:
            # Fully custom profile SOUL.md
            print(f"    Using custom {agent['name']} SOUL.md profile...")
            with open(local_soul_source, 'r', encoding='utf-8') as f:
                content = f.read()
            content = content.replace("file:///Users/carlos/cwork/Brian_Notes/PC/Knowhow/agent/skills/Swarm_Driven_Development.md", "skills/swarm/SKILL.md")
            
            with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8') as tf:
                tf.write(content)
                temp_soul_path = tf.name
        else:
            # General agent SOUL merging
            print("    Downloading remote SOUL.md to perform FSM merge...")
            with tempfile.NamedTemporaryFile('w+', delete=False, encoding='utf-8') as tf_remote:
                temp_remote_soul = tf_remote.name
            
            if scp_from_remote(agent['soul_path'], temp_remote_soul) != 0:
                print("    Failed to download remote SOUL.md, skipping this agent.")
                os.unlink(temp_remote_soul)
                continue
                
            with open(temp_remote_soul, 'r', encoding='utf-8') as f:
                remote_content = f.read()
            os.unlink(temp_remote_soul)
            
            with open(SOUL_TEMPLATE, 'r', encoding='utf-8') as f:
                template_content = f.read()
                
            merged_content = merge_soul_content(remote_content, template_content)
            
            with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8') as tf:
                tf.write(merged_content)
                temp_soul_path = tf.name
                
        # Copy prepared SOUL.md to remote
        print(" -> Uploading new SOUL.md...")
        if scp_to_remote(temp_soul_path, agent['soul_path']) != 0:
            print("    Failed to upload SOUL.md")
            os.unlink(temp_soul_path)
            continue
        os.unlink(temp_soul_path)
        
        # 4. Copy RULE.md
        print(" -> Copying RULE.md...")
        with open(RULE_SOURCE, 'r', encoding='utf-8') as f:
            rule_content = f.read()
        rule_content = rule_content.replace("file:///Users/carlos/cwork/Brian_Notes/PC/Knowhow/agent/skills/Swarm_Driven_Development.md", "skills/swarm/SKILL.md")
        
        with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8') as tf_rule:
            tf_rule.write(rule_content)
            temp_rule_path = tf_rule.name
            
        if scp_to_remote(temp_rule_path, rule_remote_path) != 0:
            print("    Failed to upload RULE.md")
            os.unlink(temp_rule_path)
            continue
        os.unlink(temp_rule_path)
        
        # 5. Copy Swarm Meta-skill (SKILL.md)
        print(" -> Creating skills/swarm directory...")
        skill_dir_path = f"{agent['dir_path']}/skills/swarm"
        run_ssh_command(f"mkdir -p {skill_dir_path}")
        
        print(" -> Copying SKILL.md...")
        skill_remote_path = f"{skill_dir_path}/SKILL.md"
        if scp_to_remote(SKILL_SOURCE, skill_remote_path) != 0:
            print("    Failed to upload SKILL.md")
            continue
            
        print(f" Successfully installed SDA to: {agent['name']}")
        
    print("\nAll done!")

if __name__ == '__main__':
    main()
