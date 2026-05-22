# Common Agent → Coordinator Redesign

**Date**: 2026-05-22
**Status**: Design approved, pending implementation
**Scope**: `src/agents/common/` — replace the rigid `planner → codeact → END` workflow with a tool-calling coordinator that orchestrates the deep-research and codeact sub-agents.

---

## 1. Motivation

The current `factory.py` wires a fixed `START → planner → codeact → END` graph. This shape was useful for sandbox testing but blocks the next goal: integrating the deep-research (DR) sub-agent and letting the system handle requests that need both research and execution. Concretely:

- The planner runs once and never re-plans.
- Codeact is the only downstream — there is no place to plug DR in.
- `PlannerOutput.target_skill` hard-routes to a single skill; mixed-skill tasks can't be expressed.

We want a Coordinator that can mix DR and codeact in one request (e.g. "research the latest AI inference chip benchmarks, then plot a comparison"). The Coordinator should plan when planning helps, dispatch the right sub-agent for each sub-problem, and synthesize a final answer.

## 2. Architecture

```
                ┌──────────────────────────────────────────┐
                │           create_agent (outer)           │
                │   System prompt:                         │
                │    - identity & dispatch principles      │
                │    - planning discipline                 │
                │    - tool usage rules (incl. BAD/GOOD)   │
                │    - skill catalog (refreshed each turn) │
                │                                          │
                │   ReAct loop (LLM ↔ tools):              │
                │     update_plan   ──► state.plan         │
                │     deep_research ──► DR subgraph        │
                │     run_codeact   ──► codeact subgraph   │
                └──────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   update_plan        deep_research            run_codeact
   (state mutation)   (compiled DR graph)      (compiled codeact graph)
```

### Key decisions

- **No upfront planner node.** Planning becomes a tool the agent calls when needed. Pure Claude-Code style.
- **No rigid edges at the outer layer.** `create_agent` runs a ReAct loop; iteration count is bounded by `recursion_limit` only.
- **Sub-agent-as-tool.** DR and codeact remain fully-compiled subgraphs. The outer layer sees them as plain `@tool` callables. Sub-agents' internal edges and nodes are untouched.
- **`target_skill` routing is removed.** Skill selection is handled by the outer LLM reading the skill catalog (in system prompt) and phrasing `run_codeact(task=...)` accordingly. Codeact's internal `tool_command` node still dispatches into `SKILL_DICT`.
- **Outer model and DR model are independent.** DR keeps its hardcoded `ChatDeepSeek` (it is prompt-tuned for that model and DR is a high-volume web-summarization task suited to a cheaper model).

## 3. State schema

```python
import operator
from typing import Annotated, Literal
from typing_extensions import TypedDict
from langgraph.graph import MessagesState

class Todo(TypedDict):
    id: str                                      # short agent-assigned id, e.g. "t1"
    content: str                                 # imperative phrasing, e.g. "Search for X"
    status: Literal["pending", "in_progress", "completed"]

class CommonAgentState(MessagesState):
    plan: list[Todo]                                              # overwritten by update_plan
    workspace: str                                                # caller-provided
    dr_findings: Annotated[list[dict], operator.add]              # appended by deep_research
    codeact_artifacts: Annotated[list[dict], operator.add]        # appended by run_codeact
```

### Field ownership

| Field | Writer | Trigger |
|---|---|---|
| `messages` | `create_agent` internals + every tool | every turn |
| `plan` | `update_plan` tool (via `Command(update={"plan": ...})`) | when agent decides to plan |
| `workspace` | Caller, in `initial_state` | once per invocation |
| `dr_findings` | `deep_research` tool | each DR call |
| `codeact_artifacts` | `run_codeact` tool | each codeact call |

### Why the artifact fields exist

`messages` will eventually be subject to context compression (Anthropic-harness style). Sub-agent outputs are the most load-bearing structured data we have, so we keep them in dedicated state fields. Compression middleware (out of scope for this spec) can later replace bulky tool messages with references like "see `state.dr_findings[i]`" while preserving the underlying data.

## 4. Tool surface

Four tools total. Skill discovery is handled via system-prompt catalog, not as a tool.

### 4.1 `update_plan(todos: list[Todo]) → Command`

Full-replacement todo write (Anthropic `TodoWrite` style). The agent passes the entire new list each time.

```python
@tool
def update_plan(
    todos: list[Todo],
    state: Annotated[CommonAgentState, InjectedState],
) -> Command:
    """Create or replace the agent's todo list. Use PROACTIVELY for any
    task with 3+ distinct steps. Exactly one item should be in_progress
    at a time. Mark items completed IMMEDIATELY after finishing them."""
    return Command(update={
        "plan": todos,
        "messages": [ToolMessage(content=_format_plan(todos), ...)],
    })
```

### 4.2 `deep_research(query: str) → Command`

Wraps the compiled DR subgraph. The `query` argument is **the agent's research goal**, not the user's raw input.

```python
@tool
def deep_research(
    query: str,
    state: Annotated[CommonAgentState, InjectedState],
) -> Command:
    """Conduct deep web research on a focused topic. Returns a markdown
    report with sources. Use when the question needs external/current
    info, multiple sub-questions, or source citations.

    CRITICAL: `query` is YOUR research goal, not the user's raw input.
    Phrase it as: subject + time range + info type."""
    dr = _get_dr()
    result = dr.invoke({"messages": [HumanMessage(query)]})
    finding = {
        "query": query,
        "report": result["answer"],
        "sources": _extract_sources(result),
    }
    return Command(update={
        "dr_findings": [finding],
        "messages": [ToolMessage(content=result["answer"], ...)],
    })
```

### 4.3 `run_codeact(task: str) → Command`

Wraps the compiled codeact subgraph. `task` must be **self-contained** — codeact has no access to the outer plan or findings unless the agent quotes them in `task`.

```python
@tool
def run_codeact(
    task: str,
    state: Annotated[CommonAgentState, InjectedState],
) -> Command:
    """Execute a Python/data/analysis task in a sandbox with access to
    project skills. The `task` must be self-contained — codeact won't
    see your plan or DR findings unless you include them in `task`.

    If the task fits a project skill, mention it explicitly."""
    workspace = state.get("workspace") or _default_workspace()
    codeact = _get_codeact()
    result = codeact.invoke(
        {"messages": [HumanMessage(f"{task}\n\nWorkspace: {workspace}")], ...},
        config={"recursion_limit": 40},
    )
    summary = result["messages"][-1].content
    artifact = {"task": task, "summary": summary, "workspace": workspace}
    return Command(update={
        "codeact_artifacts": [artifact],
        "messages": [ToolMessage(content=summary, ...)],
    })
```

### 4.4 Sub-agent lifecycle

Both sub-agents are compiled lazily at module level and reused for the lifetime of the process. Compiling a `StateGraph` is non-trivial and re-compiling per tool call would dominate runtime.

Caveat: the codeact singleton captures the model from the first `create_common_agent` call. If multiple `create_common_agent(...)` calls in the same process pass different models, all share the first codeact instance. This matches current single-process / single-model usage; revisit if multi-model scenarios appear.

```python
_codeact_singleton = None
_dr_singleton = None

def _get_codeact(model):
    global _codeact_singleton
    if _codeact_singleton is None:
        _codeact_singleton = create_codeact(model=model, eval_fn=local_python_sandbox)
    return _codeact_singleton

def _get_dr():
    global _dr_singleton
    if _dr_singleton is None:
        _dr_singleton = research_agent().create_agent()
    return _dr_singleton
```

### 4.5 Error handling

Sub-agent exceptions surface naturally through the default `ToolNode` behavior — the exception becomes a `ToolMessage` and the outer agent reacts. No bespoke try/except.

DR's existing internal fault tolerance (failed Tavily queries logged as warnings, partial results still returned) is preserved.

## 5. System prompt

The outer system prompt is a **static string** rendered once when `create_common_agent` is called and passed to `create_agent(system_prompt=...)`. The current langchain version's `create_agent` does not accept a callable prompt, so per-turn refresh of the skill catalog is not available in v1.

```python
def _render_system_prompt() -> str:
    return SYSTEM_PROMPT_TEMPLATE.format(
        skill_catalog=_render_skill_catalog(),   # list_skills() called once at build time
    )
```

Implications:
- Adding a new skill at runtime requires rebuilding the agent (calling `create_common_agent` again).
- For typical usage where skills are defined statically in the codebase, this is acceptable. Dynamic refresh is deferred — see §10.

### Prompt structure (five sections)

1. **Identity** — coordinator role, explicit "DO NOT execute Python yourself / DO NOT search the web yourself" prohibition to prevent hallucinated tool bypass.
2. **Planning discipline** — `update_plan` usage rules, one in_progress at a time, mark completed immediately.
3. **Sub-agent dispatch** — when to use `deep_research` vs `run_codeact`; explicit BAD/GOOD example for DR query formulation; reminder that `run_codeact(task=...)` must be self-contained.
4. **Skill catalog** — `{skill_catalog}` placeholder, rendered fresh each turn from `list_skills()`.
5. **Workflow patterns** — three concrete examples: hybrid (DR → codeact), code-only, research-only. Presented as illustrations, not enforced sequences.

Full prompt text is implemented in `src/agents/common/prompts.py`.

## 6. Factory and entry points

### 6.1 Signature

```python
def create_common_agent(
    model: BaseChatModel | None = None,
    *,
    recursion_limit: int = 60,
) -> CompiledStateGraph:
    selected_model = model or create_default_model()
    codeact = _get_codeact(selected_model)
    dr = _get_dr()
    tools = _build_tools(codeact=codeact, dr=dr)
    return create_agent(
        model=selected_model,
        tools=tools,
        system_prompt=_render_system_prompt(),
        state_schema=CommonAgentState,
    )
```

The `workspace_dir` parameter is **removed** — workspace is the caller's responsibility (see 6.2).

### 6.2 Workspace handling

Pure caller-supplied:

```python
graph.invoke({
    "messages": [HumanMessage(user_input)],
    "workspace": "./output/my-session",        # caller provides
})
```

`run_codeact` has a one-line last-resort default (`state.get("workspace") or _default_workspace()`) so a missing workspace does not crash, but the contract is: callers should supply it.

### 6.3 Recursion limits (layered)

| Layer | Limit | Set where |
|---|---|---|
| Outer coordinator | 60 (configurable via `recursion_limit` arg) | `create_agent` |
| Codeact subgraph | 40 | inside `run_codeact` tool's `codeact.invoke(config=...)` |
| DR subgraph | `MAX_ROUNDS = 2` | constant in `research_agent` class |

The three layers are independent — sub-agent config does not consume the outer budget.

## 7. Module layout

```
src/agents/common/
├── factory.py        # rewrite — create_common_agent
├── state.py          # NEW — Todo, CommonAgentState
├── tools.py          # NEW — update_plan, deep_research, run_codeact
├── prompts.py        # NEW — SYSTEM_PROMPT_TEMPLATE + builder
├── sandbox.py        # unchanged
└── planner.py        # DELETED
```

Files outside `src/agents/common/` are not modified:

- `src/agents/sub_graph/web_search.py` — imported, not changed.
- `src/agents/code/agent.py` — imported, not changed.
- `src/agents/code/skills_tools.py` — `list_skills()` consumed by `prompts.py`; `SKILL_DICT` consumed by codeact internals.

## 8. Implementation order

Each step is independently testable.

1. Create `state.py` (`Todo`, `CommonAgentState` with reducers).
2. Create `prompts.py` (full template + `build_system_prompt` callable).
3. Create `tools.py` (three tools, each returning `Command`).
4. Rewrite `factory.py` (assemble with `create_agent`).
5. Delete `planner.py`; update `__init__.py` exports.
6. Smoke test via `test.py`: confirm graph compiles, a single trivial request runs end-to-end.
7. Hybrid end-to-end test: a request that should plausibly trigger DR → codeact in sequence. Verify dispatch by inspecting messages and `dr_findings` / `codeact_artifacts`.

## 9. Pre-implementation verification

These are **not assumed**; the implementation plan's first task is to confirm them empirically.

| Check | How |
|---|---|
| `langchain.agents.create_agent` (v1 API) is available in the project's langchain version | `grep langchain requirements.txt`; import `from langchain.agents import create_agent` in a scratch script |
| Tools returning `Command(update={...})` merge into outer state correctly | minimal tool returning a Command; invoke; inspect resulting state |
| `InjectedState` injection works for our state schema | tool reads `state["workspace"]`; print/log to verify |

If any check fails, fall back to a hand-written supervisor `StateGraph` with the same external contract (state schema, tool surface, system prompt). This fallback is the only alternative path; the rest of the spec is unaffected.

## 10. Out of scope (YAGNI)

- Context compression middleware (state fields are reserved; middleware itself is later work).
- DR report length cap (address inside DR's `report` node when needed).
- Multi-thread checkpointing.
- Streaming-friendly tool message reshaping (existing `service/chat.py` stream handling continues unchanged).
- Standalone `replan` tool (`update_plan` full-replacement already covers re-planning).
- **Per-turn dynamic skill catalog refresh** — current `create_agent` API takes only a string `system_prompt`. Skill changes require rebuilding the agent. Future option: revisit when langchain exposes callable prompts or implement via a `pre_model_hook` middleware that rewrites the system message.

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Agent skips `update_plan` despite system prompt | Observe in hybrid test. If frequent, strengthen BAD/GOOD examples in prompt; last resort, revert to a hybrid where a one-shot upfront planner seeds the initial todo list. |
| Agent passes raw user input as DR query | Tool description's BAD/GOOD example is first line of defense. If still observed, add a small LLM rephrasing step inside the tool. |
| `create_agent` ReAct loop trips recursion limit on edge cases | Already bounded by `recursion_limit=60`. Observe loops in testing; tune downward if needed. |
| Existing callers depend on `state["plan"]` being `PlannerOutput` | `grep -r 'state\["plan"\]' src/` and `grep -r 'plan\.target_skill' src/`; migrate any consumers to `list[Todo]`. Current grep suggests no external consumers, but verify. |

## 12. Backwards compatibility for callers

Existing invocation shape:

```python
graph.invoke({"messages": [HumanMessage(user_input)]})
```

continues to work. The new optional `workspace` field is the only addition. `plan`, `dr_findings`, `codeact_artifacts` default to empty via LangGraph reducers.

`cli_common_agent.py`, `test.py`, and `service/chat.py` are expected to require no changes for the basic flow. Any code reading `state["plan"]` as `PlannerOutput` will need to migrate; this is checked in §11.
