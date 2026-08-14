#!/usr/bin/env python3
"""
SWDA Benchmark Harness Runner CLI Tool.

Usage:
  python -m tests.benchmark.harness_runner [--offline] [--tasks TASKS_FILE] [--report REPORT_FILE]

Description:
  Executes the evaluation suite across candidate models under SWDA system prompt contracts.
  Generates a Markdown Evaluation Report with Pass Rates and Weighted 100-point Scores.
"""
import argparse
import json
import os
import sys

from tests.benchmark.scoring import SWDAEvaluator

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_TASKS_FILE = os.path.join(ROOT_DIR, "tests", "benchmark", "tasks.json")


def mock_model_offline_response(prompt: str) -> str:
    """
    Simulates a deterministic SWDA-compliant LLM model output for offline testing.
    """
    text = prompt.strip().lower()
    
    if "ignore previous" in text or "drop database" in text:
        return """<INTENT_GATE_RESULT>
INTENT_CLASSIFICATION: SECURITY_AUDIT
EXECUTION_TRACK: FAST_PASS
RESOURCE_LOCK_REQUIRED: False
USE_SWARM_WORKFLOW: False
AUDITOR_SAFETY_STATUS: BLOCKED_INJECTION
STRATEGY_TRACK: Intercepted by Firewall TC-08 Direct Injection Guard.
</INTENT_GATE_RESULT>
[NEXT_STATE: ACTION_REALIZATION_BLOCK | Zero-Chat Contract Active]"""

    elif "hi" in text:
        return "Hello! How can I help you with your coding project today?"

    elif "路徑" in text or "path" in text:
        return "當前專案根目錄路徑為: /Users/carlos/pywork/swarm-driven-agent"

    elif "summary" in text or "摘要" in text:
        return "本專案 Swarm-Driven Agent (SWDA) 係以 SWDD 群體智能框架包裝 SOTA 模型之 Agentic Coding 框架。"

    elif "修正" in text or "syntax" in text:
        return """<INTENT_GATE_RESULT>
INTENT_CLASSIFICATION: FEATURE_DEV
EXECUTION_TRACK: LITE_MODE
RESOURCE_LOCK_REQUIRED: False
USE_SWARM_WORKFLOW: False
AUDITOR_SAFETY_STATUS: PASSED
STRATEGY_TRACK: Direct single-file synthesis and physical verification.
</INTENT_GATE_RESULT>
[NEXT_STATE: LITE_MODE | Zero-Chat Contract Active]"""

    else:
        return """<INTENT_GATE_RESULT>
INTENT_CLASSIFICATION: FULL_REFACTOR
EXECUTION_TRACK: SWARM_MODE
RESOURCE_LOCK_REQUIRED: True
USE_SWARM_WORKFLOW: True
AUDITOR_SAFETY_STATUS: PASSED
STRATEGY_TRACK: Full 5-Phase SWDD workflow with Builder/Destroyer Crucible.
</INTENT_GATE_RESULT>
[NEXT_STATE: PHASE_1_DESTRUCT | Zero-Chat Contract Active]"""


def run_pi_agent_live(prompt: str, model: str = None, timeout: int = 30) -> str:
    """
    Executes live evaluation against Pi Agent (pi CLI) in non-interactive mode.
    """
    import subprocess
    cmd = ["pi", "--no-session", "-p", prompt]
    if model:
        cmd.extend(["--model", model])
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return res.stdout if res.returncode == 0 else res.stderr
    except subprocess.TimeoutExpired:
        return "<INTENT_GATE_RESULT>\nINTENT_CLASSIFICATION: TIMEOUT\nEXECUTION_TRACK: FAST_PASS\n</INTENT_GATE_RESULT>\n[NEXT_STATE: HITL_SUSPEND | Timeout]"
    except Exception as e:
        return f"<INTENT_GATE_RESULT>\nINTENT_CLASSIFICATION: ERROR\nEXECUTION_TRACK: FAST_PASS\n</INTENT_GATE_RESULT>\n[NEXT_STATE: HITL_SUSPEND | {str(e)}]"


def run_omp_agent_live(prompt: str, model: str = None, timeout: int = 30) -> str:
    """
    Executes live evaluation against OMP (oh-my-pi CLI) in non-interactive mode.
    """
    import shutil
    import subprocess
    omp_bin = shutil.which("omp") or "/Users/carlos/.bun/bin/omp"
    if not os.path.exists(omp_bin):
        return "<INTENT_GATE_RESULT>\nINTENT_CLASSIFICATION: ERROR\nEXECUTION_TRACK: FAST_PASS\n</INTENT_GATE_RESULT>\n[NEXT_STATE: HITL_SUSPEND | omp binary not found]"
    cmd = [omp_bin, "--no-session", "-p", prompt]
    if model:
        cmd.extend(["--model", model])
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return res.stdout if res.returncode == 0 else res.stderr
    except subprocess.TimeoutExpired:
        return "<INTENT_GATE_RESULT>\nINTENT_CLASSIFICATION: TIMEOUT\nEXECUTION_TRACK: FAST_PASS\n</INTENT_GATE_RESULT>\n[NEXT_STATE: HITL_SUSPEND | Timeout]"
    except Exception as e:
        return f"<INTENT_GATE_RESULT>\nINTENT_CLASSIFICATION: ERROR\nEXECUTION_TRACK: FAST_PASS\n</INTENT_GATE_RESULT>\n[NEXT_STATE: HITL_SUSPEND | {str(e)}]"


class HarnessRunner:
    def __init__(self, tasks_file: str = DEFAULT_TASKS_FILE, offline: bool = True, agent_driver: str = "mock"):
        self.tasks_file = tasks_file
        self.offline = offline
        self.agent_driver = agent_driver
        with open(tasks_file, "r", encoding="utf-8") as f:
            self.task_suite = json.load(f)

    def run_evaluation(self, model_name: str = "swda(pi-agent)") -> dict:
        tasks = self.task_suite.get("tasks", [])
        results = []
        total_points = 0.0
        passed_count = 0

        for task in tasks:
            if self.offline or self.agent_driver == "mock":
                output = mock_model_offline_response(task["prompt"])
            elif self.agent_driver == "pi":
                output = run_pi_agent_live(task["prompt"])
            elif self.agent_driver == "omp":
                output = run_omp_agent_live(task["prompt"])
            else:
                output = mock_model_offline_response(task["prompt"])

            eval_res = SWDAEvaluator.evaluate_task(task, output)
            results.append(eval_res)
            total_points += eval_res["total_score"]
            if eval_res["status"] == "PASS":
                passed_count += 1

        avg_score = round(total_points / len(tasks), 2) if tasks else 0.0
        pass_rate = round((passed_count / len(tasks)) * 100.0, 1) if tasks else 0.0

        return {
            "model_name": model_name,
            "total_tasks": len(tasks),
            "passed_tasks": passed_count,
            "pass_rate_pct": pass_rate,
            "average_score": avg_score,
            "details": results
        }

    def generate_markdown_report(self, eval_data: dict) -> str:
        md = []
        md.append(f"# SWDA Evaluation Harness Benchmark Report")
        md.append(f"**Target Model**: `{eval_data['model_name']}` | **Mode**: `{'Offline Replay' if self.offline else 'Live Execution'}`")
        md.append(f"**Overall Pass Rate**: `{eval_data['pass_rate_pct']}%` ({eval_data['passed_tasks']}/{eval_data['total_tasks']}) | **Average Weighted Score**: `{eval_data['average_score']}/100`\n")

        md.append("| Task ID | Expected Track | Actual Track | Next State | Score | Status |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")

        for item in eval_data["details"]:
            md.append(
                f"| `{item['task_id']}` | `{item['expected_track']}` | `{item['actual_track']}` | `{item['actual_next_state']}` | `{item['total_score']}` | **{item['status']}** |"
            )

        md.append("\n---")
        md.append("### Score Dimension Breakdown (100 pts total)")
        md.append("- **Physical Pass Rate**: 40 pts")
        md.append("- **FSM/XML Compliance**: 30 pts")
        md.append("- **Track Efficiency**: 20 pts")
        md.append("- **Security & Firewall**: 10 pts")

        return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="SWDA Benchmark Harness Runner")
    parser.add_argument("--offline", action="store_true", default=True, help="Run in deterministic offline replay mode")
    parser.add_argument("--tasks", default=DEFAULT_TASKS_FILE, help="Path to tasks.json specification")
    parser.add_argument("--report", default=None, help="Optional output path for Markdown report")
    args = parser.parse_args()

    runner = HarnessRunner(tasks_file=args.tasks, offline=args.offline)
    eval_data = runner.run_evaluation()
    report_md = runner.generate_markdown_report(eval_data)

    print(report_md)

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"\nReport saved to: {args.report}")


if __name__ == "__main__":
    main()
