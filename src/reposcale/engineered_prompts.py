from __future__ import annotations

from reposcale.schemas import TaskSpec


ENGINEERED_SYSTEM_PROMPT = """You are RepoScale's engineered coding agent.
Solve repository tasks with a disciplined software-engineering workflow.

Workflow:
1. Write a short todo plan.
2. Search for the smallest relevant context.
3. Read only files needed for the fix.
4. Make a focused patch with replace_line_range when line numbers are known.
5. Run the validation tool.
6. Stop when validation passes or when you can clearly explain the blocker.

Rules:
- Work only inside the task repository.
- Prefer grep/glob before broad file reads.
- Avoid unrelated docs/config edits unless the task asks for them.
- Do not keep searching after you have found the target function.
- Use replace_line_range when you know the target line numbers or exact edit_file replacement fails.
- Use the validation tool instead of inventing a test command.
"""


def build_engineered_prompt(task: TaskSpec) -> str:
    validation = task.test_command or "No validation command provided."
    return (
        f"Task ID: {task.task_id}\n"
        f"Title: {task.title}\n"
        "Repository root is mounted as the filesystem root.\n"
        f"Problem:\n{task.problem_statement}\n\n"
        f"Validation: use the run_validation tool. It runs: {validation}\n"
        "Editing: use replace_line_range(file_path, start_line, end_line, new_text) "
        "when a read_file result gives reliable line numbers. It rebases replacement "
        "indentation onto the original code block by default.\n"
    )
