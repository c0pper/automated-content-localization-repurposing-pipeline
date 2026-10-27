# Matt Pocock's Agent-Driven Development Workflow

This document outlines the structured, step-by-step process for using AI coding agents effectively, moving from initial concept to merged code while keeping humans in charge of strategic decisions.

---

## 1. Interview & Decision Tree Mapping (`grill me` / `grill with docs`)
*   **Purpose:** Uncover hidden edge cases, clarify requirements, and align on business logic before writing any code.
*   **Description:** 
    *   Before code generation begins, the agent interviews the user. It maps the feature as a "tree of decisions in the fog."
    *   It identifies the "frontier"—the next layer of decisions whose prerequisite choices have already been made—and asks the user all frontier questions in a single numbered round, complete with recommended answers.
    *   If factual technical information is needed, the agent spawns helper agents to read the codebase rather than asking the user.
    *   **Domain Jargon (`grill with docs`):** The agent maintains a glossary within the repository to explicitly define terms (e.g., distinguishing *pause* vs. *skip*) and list terms to avoid (e.g., *hold*, *freeze*).

## 2. Plain English Clarification (`wait what`)
*   **Purpose:** Resolve confusing or overly complex jargon from the agent.
*   **Description:** If the agent produces dense or convoluted explanations, typing `wait what` instructs the agent to re-pitch its last message in clear, plain English using the terms established in the repo's glossary.

## 3. Throwaway Prototyping
*   **Purpose:** Resolve design and user experience questions that cannot be settled purely by text discussion.
*   **Description:** For "ungrillable" UI/UX choices, the agent hands off the task to a fresh session to build a few lightweight, throwaway screens with contrasting designs. The developer clicks through them, selects a preference, and feeds that decision back into the main grilling session.

## 4. Spec Writing & Seam Agreement (`to spec`)
*   **Purpose:** Formalize all decisions into an actionable specification and define system integration points.
*   **Description:** 
    *   Once the fog clears, the agent writes up the entire feature: the problem, the fix, and a detailed list of user stories.
    *   The user and agent agree on the **"seams"**—the specific boundaries or integration points (ideally just one, such as a billing module) where automated tests will validate the feature.
    *   The completed spec is posted as an issue in the issue tracker labeled `ready for agent`.

## 5. Spec Slicing & Ticket Creation (`to tickets`)
*   **Purpose:** Avoid model performance degradation ("smart zone" token limits) by dividing large tasks into context-friendly chunks.
*   **Description:** 
    *   Because agents lose reasoning capacity as context grows (typically past ~150,000 tokens), the spec is sliced into isolated, single-session tickets.
    *   Each ticket covers an end-to-end slice (from database to UI) that can stand on its own.
    *   **Rule of Thumb:** Estimate total tokens, divide by 150,000, and split into that number of tickets with clear dependency mappings (what blocks what).

## 6. Test-Driven Implementation (`implement` / `implement spec`)
*   **Purpose:** Execute code generation cleanly with minimal context drift using test-driven development (TDD).
*   **Description:** 
    *   **Single Ticket (`implement`):** The developer starts each ticket in a fresh chat session to ensure a "clean head."
    *   **Multi-Agent Execution (`implement spec`):** Spawns one agent per ready ticket simultaneously in isolated copies of the repository, all targeted to land on one branch.
    *   **TDD Approach:** Agents write a failing test at the agreed seam first, followed by only the exact amount of code required to pass the test.

## 7. Multi-Agent Code Review
*   **Purpose:** Catch bugs, spec deviations, and code smells without relying on the authoring agent's confirmation bias.
*   **Description:** 
    *   Code review is offloaded to two completely fresh agents that did not write the code:
        1.  **Spec Reviewer:** Compares the diff directly against the user stories to check for missing features, unintended scope, or incorrect logic.
        2.  **Code Quality Reviewer:** Checks the diff against repo coding standards and classic code smells (e.g., Martin Fowler's *Refactoring*).

## 8. Pull Request Generation (`PR` / `show me`)
*   **Purpose:** Document the pull request concisely while explicitly communicating risk.
*   **Description:** 
    *   Generates a concise PR description featuring the smallest image/diff summary that explains the change and proof of before-and-after behavior.
    *   Includes a **Merge Danger** section assessing the type of change (one-way vs. two-way door) and defining its blast radius (e.g., billing system, deployment ordering).

## 9. Retrospective & Environment Tuning (`retro`)
*   **Purpose:** Permanently prevent repeated agent mistakes by improving instructions and automated checks.
*   **Description:** 
    *   Before closing the chat, running `retro` prompts the agent to analyze its own transcript and identify friction points.
    *   The agent suggests improvements to its surroundings: repo structure, prompt instructions, or automated checks.
    *   Deterministic issues (e.g., wrong API calls) are turned into lint rules or automated test checks, leaving the written guidelines strictly for qualitative judgment calls.
    *   The human selects which suggested updates to keep.