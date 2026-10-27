# RepoPilot — Sandbox Security & Evaluation Integrity Policy (Phase 3)

> **Document Version:** 1.0.0  
> **Phase:** 3 — Harden the Execution Sandbox and Evaluation Boundary  
> **Status:** Active Standard

---

## 1. Motivation & Threat Model

When coding agents generate code, they execute unvetted Python code and shell commands. In an unhardened environment, two major risks arise:

1. **Security Vulnerabilities (Host Escape & Data Leakage):**
   - Untrusted agent code could attempt to read host secrets (`.env`, `~/.ssh/id_rsa`, cloud credentials).
   - Agent code could invoke network sockets to exfiltrate proprietary data or download unvetted binary dependencies.
   - Runaway loops or memory fork-bombs could freeze the host machine.
2. **Evaluation Tampering (Cheating):**
   - LLMs can easily modify, weaken, or delete test files (`assert x == 5` changed to `assert True`) to falsely claim a successful fix.
   - An agent could inspect ground-truth reference patches if they are placed in its writable workspace.

---

## 2. Hardened Sandbox Specifications

All task execution and evaluation run inside isolated Docker containers (or tightly controlled local sandboxes during smoke testing) subject to the following rules:

### 2.1 Container & Kernel Constraints

| Parameter | Configuration | Purpose |
| :--- | :--- | :--- |
| **Base Image** | `python:3.11-slim` (pinned digest) | Minimal attack surface, pure standard library. |
| **Networking** | `network_mode="none"` during test evaluation | Blocks all outbound/inbound network calls. |
| **Memory Limit** | `mem_limit="2g"` | Prevents out-of-memory (OOM) host crashes. |
| **CPU Limit** | `nano_cpus=2_000_000_000` (2 cores) | Prevents CPU starvation of the host. |
| **Process Limit** | `pids_limit=100` | Prevents fork-bomb attacks. |
| **Timeout** | 60 seconds (hard kill) | Terminates runaway infinite loops. |
| **Output Cap** | Max 50,000 characters (stdout/stderr) | Prevents log buffer memory exhaustion. |
| **Volume Mount** | Target workspace bound to `/repo` | Isolated bind mount; host filesystem not mounted. |

---

## 3. Host Protection Boundaries

1. **No Host Directory Exposure:**  
   The user's home directory (`~`), SSH keys (`~/.ssh`), cloud credentials (`~/.aws`, `~/.config`), and root directories are never mounted.
2. **No Docker Socket Mounting:**  
   `/var/run/docker.sock` is strictly forbidden inside the container. Agent code cannot control the host Docker daemon.
3. **No Credential Injection:**  
   LLM API keys (`GROQ_API_KEY`, `OPENAI_API_KEY`, `GITHUB_TOKEN`) reside only in the trusted host orchestrator and are never injected into the sandbox container environment variables.
4. **Path Traversal Defense:**  
   All file read/write operations performed by the agent are validated against `repo_path.resolve()`. Any path referencing `../` that escapes the repository root is rejected immediately with a `SecurityException`.

---

## 4. Evaluation Integrity & Anti-Tampering Standard

To guarantee scientific reproducibility and prevent self-evaluation cheating:

### 4.1 Authoritative Evaluation Tests Kept Outside Workspace
* The regression test patch (`test_patch`) and reference patch (`reference_patch`) are stored in `dataset/tasks.jsonl` outside the agent's workspace.
* The agent is provided only with:
  1. The clean repository checkout at `base_commit`.
  2. The issue title and description.
* The agent **never** receives the authoritative evaluation test files during its implementation phase.

### 4.2 Strict Tamper Detection Gate
When the agent submits its candidate patch, the evaluator runs an invariant check:
```python
def check_patch_tampering(patch_text: str) -> bool:
    """Returns True if patch touches ANY test file."""
    for line in patch_text.splitlines():
        if line.startswith("diff --git") or line.startswith("--- ") or line.startswith("+++ "):
            if any(t in line for t in ["test_", "_test.py", "tests/", "/test/"]):
                return True # TAMPERING DETECTED
    return False
```
If a patch touches test files, the run is immediately marked:
$$\text{Status: FAILED} \quad (\text{Reason: EVALUATION\_TAMPERING\_DETECTED})$$

### 4.3 Clean-Room Independent Evaluation
Once the candidate patch passes the tamper check:
1. A fresh, clean workspace is instantiated at `base_commit`.
2. The candidate patch is applied to source code.
3. The authoritative regression test is injected from the external dataset.
4. The test suite is executed in an isolated container with `--network none`.
5. The task succeeds **if and only if** the regression test passes and pre-existing tests do not regress.
