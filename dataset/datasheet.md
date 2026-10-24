# RepoPilot Benchmark Dataset Datasheet (v0.1 Pilot)

## 1. Motivation

* **For what purpose was the dataset created?**  
  To provide a trustworthy, reproducible benchmark of real-world GitHub bug-fixing tasks for evaluating coding agents (B0 Naive Baseline, B1 Retrieval, B2 Multi-Agent, and B3 Dynamic Model Routing).
* **Who created the dataset?**  
  The RepoPilot project maintainers using automated mining (`dataset/mining.py`) and empirical ground-truth verification (`dataset/verification.py`).

---

## 2. Dataset Composition & Scope

* **What do the instances that comprise the dataset represent?**  
  Each instance is a real-world Python bug-fixing task derived from merged GitHub pull requests. Each instance contains:
  1. Target repository URL and license.
  2. Pinned buggy base commit (`base_commit`).
  3. Pinned merged fix commit (`fixed_commit`).
  4. Real issue title and description.
  5. Regression test patch (`test_patch`).
  6. Reference code patch (`reference_patch`).
  7. Exact test command and fail-to-pass test function IDs.
* **How many instances are in dataset v0.1?**  
  **3 pilot tasks** across 2 mature, pure-Python open-source libraries:
  - `tinydb-635` (`msiemens/tinydb`, MIT License)
  - `tinydb-641` (`msiemens/tinydb`, MIT License)
  - `more-itertools-1309` (`more-itertools/more-itertools`, MIT License)
* **What language and runtime environment are required?**  
  Python 3.10 / 3.11 with `pytest`. Evaluation requires no internet connectivity once the repository is checked out.

---

## 3. Inclusion and Exclusion Rules

### Inclusion Criteria
1. **Real-world origin:** Derived directly from closed GitHub issues and merged pull requests.
2. **Deterministic reproduction:** The buggy base commit **must fail** the regression test with a reproducible error.
3. **Reference patch verification:** Applying the reference code patch **must pass** the regression test cleanly with 0 regressions in pre-existing tests.
4. **Clean separation:** Code changes and test changes must be cleanly separable into `reference_patch` and `test_patch`.
5. **Execution time:** The test suite for the task must execute in under 30 seconds.
6. **No network dependency:** Evaluation does not require external network access or external database services.

### Exclusion Criteria
1. Flaky tests or non-deterministic race conditions.
2. Large refactors touching more than 4 source files.
3. Repositories requiring proprietary dependencies or complex binary compilation.
4. Tasks where the reference patch modifies evaluation test files.

---

## 4. Verification Evidence (Ground Truth)

Every task in `dataset/tasks.jsonl` was verified end-to-end using `python dataset/verification.py --dataset dataset/tasks.jsonl`.

| Task ID | Repository | Buggy Base SHA | Regression Test Command | Pre-fix Status | Post-fix Status | Wall Time |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `tinydb-635` | `msiemens/tinydb` | `4aa53111d72c` | `pytest tests/test_utils.py -k test_lru_cache_none_value` | **FAILED** (`KeyError`) | **PASSED** (0 regressions) | 20.56s |
| `tinydb-641` | `msiemens/tinydb` | `18d73a15066a` | `pytest tests/test_queries.py -k test_any` | **FAILED** (`AssertionError`) | **PASSED** (0 regressions) | 16.85s |
| `more-itertools-1309` | `more-itertools/more-itertools` | `1ea82a711c69` | `pytest tests/test_more.py -k test_falsey_validator_is_honoured` | **FAILED** (`AssertionError`) | **PASSED** (0 regressions) | 17.86s |

---

## 5. Security & Evaluation Integrity

* **Test Isolation:** The `test_patch` is applied as authoritative ground truth. During agent evaluation (Phase 3+), evaluation tests are kept **outside the agent's writable workspace** to prevent the agent from tampering with the tests to score a false success.
* **No Leaks:** The reference patch is stored in `reference_patch` and is strictly hidden from the agent during execution.

---

## 6. Attribution & Licensing

* `msiemens/tinydb` is released under the **MIT License** (Copyright 2013-2026 Markus Siemens).
* `more-itertools/more-itertools` is released under the **MIT License** (Copyright 2012-2026 Erik Rose).
* The dataset metadata, mining, and verification tools are released under the RepoPilot **MIT License**.
