# AGENTS.md - Agent Architecture & Engineering Standards

## 1. Core Operating Philosophy
You are an expert systems engineer. High velocity without structural rigor is technical debt. Prioritize single source of truth, minimal cognitive load per file, and zero duplicate logic over quick localized patches.

---

## 2. Structural & File Invariants (Hard Limits)
- **Strict File Limit:** No source file may exceed **300 lines**. If an edit pushes a file over 300 lines, you must refactor and split it before completing the task.
- **Single Responsibility (One File, One Job):**
  - UI components render UI and capture events only. They never compute domain logic.
  - Business logic lives in pure, framework-agnostic domain modules.
  - Data access/API calls live in dedicated client/repository layers.
- **No God Files:** Never create utility dumping grounds (e.g., `utils.ts`, `helpers.py`, `common.js`). Group helpers by specific domain (e.g., `date-formatting.ts`, `currency-math.ts`).

---

## 3. Single Source of Truth (SSOT) & Zero Duplication
- **Business Logic Isolation:**
  - Critical logic (pricing, discounts, tax, status machines, validation rules) must live in exactly **one** designated canonical module.
  - If a rule or formula is needed across multiple screens or endpoints, import the canonical function. **Never copy-paste or re-derive formulas.**
- **Enforce DRY:** Before implementing any calculation, formatting, or validation, search the codebase for existing implementations. If two existing modules duplicate logic, unify them into a single module first.

---

## 4. Pure Functions & State Encapsulation
- **Decouple Logic from State:** Separate deterministic calculations from I/O and state management.
- Core logic functions must be **pure**: inputs as arguments, output as return value, zero side effects, zero external mutation.
- **Explicit Interfaces:** Every module must expose a minimal, strictly typed public API. Internal helpers must remain private/unexported.
- **Immutability by Default:** Do not mutate arguments or shared state in place. Return transformed data copies.

---

## 5. Token Efficiency & Planning Protocol
To minimize wasted tokens and prevent circular debugging:
1. **Search Before You Build:** Check existing types, services, and helpers before creating new ones.
2. **Plan Edits in Memory:** Do not guess-and-check by issuing 5 consecutive speculative file writes. Read the target files, verify line numbers and imports, and apply the complete patch in one pass.
3. **Minimize Context Overhead:** When reading files, target specific functions or line ranges rather than loading entire multi-thousand-line directories into context.

---

## 6. Pre-Commit / PR Checklist (Agent Self-Audit)
Before marking any task as complete, verify:
- [ ] No duplicated logic across components or routes.
- [ ] Canonical business rules reside in their designated single source file.
- [ ] No touched file exceeds 300 lines.
- [ ] All new functions are strictly typed and handle edge cases (null/undefined/empty arrays).
- [ ] Existing tests pass, and unit tests are added for any new pure domain logic.
- [ ] No debug statements (`console.log`, `print`, breakpoint remnants) left behind.
