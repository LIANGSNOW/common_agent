# CLI Common Agent Design

## Goal

Build the first common-agent milestone as a command-line demo runner. The agent should be domain-neutral, with no stock-specific behavior registered by default. It should use a lightweight planner before execution, use CodeAct as the main reasoning and execution loop, reuse the existing skills mechanism, and execute trusted local Python through a real local sandbox.

## Non-Goals

- No stock or finance domain behavior in the first milestone.
- No API server, OpenWebUI integration, or frontend work.
- No hardened sandbox yet. The first version is trusted and local-only.
- No plugin marketplace or dynamic package installation.
- No plan approval, step-by-step human review, or final acceptance middleware in the first milestone.

## Architecture

`create_common_agent` is the primary assembly function. It initializes the chat model, creates the lightweight planner, creates the CodeAct executor, wires in the local Python sandbox, and exposes reusable capabilities such as skills and web research.

Skills and sandbox are runtime capabilities, not middleware. The planner is part of the main graph flow rather than middleware because it defines what the agent should do before execution begins. Middleware remains reserved for cross-cutting graph behavior such as clarification, summarization, checkpointing, tracing, filesystem history, plan approval, execution monitoring, final acceptance evaluation, or future memory.

The first milestone should look like this:

```text
CLI runner
  -> create_common_agent(...)
      -> planner
      -> CodeAct executor
          -> skill registry
          -> local Python sandbox
          -> optional tools/subagents
              -> web_search_deep_research
```

## Components

### CLI Runner

The CLI runner provides the demo surface. It should support a simple single-process loop where the user enters a task, the agent streams or prints intermediate messages, and the final answer is shown in the terminal.

The CLI runner should stay thin. It should not know how skills are loaded, how the sandbox executes code, or how subagents are constructed.

### Common Agent Factory

`create_common_agent` owns composition. It should accept optional model, skill registry, sandbox, tools, subagents, and middleware inputs, while providing sensible defaults for the CLI demo.

The default first version returns a graph that can:

- create a lightweight task plan before execution,
- identify likely required capabilities such as skills, Python execution, or web research,
- inspect available skills,
- fetch skill details,
- generate Python code,
- execute that code in the local sandbox,
- produce a final answer.

### Lightweight Planner

The planner runs before CodeAct execution. Its job is to understand the user request, split it into a small number of execution steps, and identify which capabilities are likely needed: skill lookup, local Python execution, or web research.

For the MVP, the planner should be advisory and automatic. It should not require human approval before execution, and it should not enforce a complex plan state machine. The output should be compact enough to pass into CodeAct as execution context.

Later upgrades can add plan confirmation, per-step progress tracking, plan revision, and final acceptance evaluation as middleware or graph-level control nodes.

### CodeAct Runtime

The existing `src/agents/code/agent.py` should be reused as the main implementation. Any changes should keep its current responsibilities recognizable: model call, command extraction, sandbox execution, and loop routing.

The existing skill discovery functions in `src/agents/code/skills_tools.py` should be reused. They can be cleaned up only where needed to make registration explicit and domain-neutral.

### Local Python Sandbox

The sandbox should start from the existing local `exec` behavior in `src/main.py`, moved into a reusable module. It executes trusted Python code locally and preserves execution context across turns in a single agent run.

The sandbox should clearly be documented as trusted/local-only.

### Web Search Deep Research Subagent

The internet search capability should be retained and made domain-neutral. It should not be stock-specific and should not default to finance search.

The web search deep research subagent should be modeled as a subagent rather than a skill because it is a multi-step workflow: plan search queries, run searches, summarize evidence, and return a research result.

For the first milestone, this subagent may be optional or minimally wired as long as the architecture leaves a clean registration point.

## Data Flow

1. The CLI receives user input.
2. The CLI sends a `HumanMessage` to the common agent graph.
3. The planner creates a compact execution plan and likely capability list.
4. CodeAct receives the user request plus planner context.
5. CodeAct decides whether to inspect skills, execute Python, call a capability, or answer.
6. Skill commands call the skill registry functions.
7. Python code runs in the trusted local sandbox.
8. Optional web research delegates to the web search subagent.
9. The CLI prints intermediate and final messages.

## Error Handling

Sandbox execution errors should be returned as messages to the agent rather than crashing the CLI. Missing skills, malformed skill commands, and tool argument errors should produce readable feedback that the agent can recover from.

Configuration errors such as missing model credentials should fail early with a clear terminal message.

Search provider errors should be contained inside the web research capability and returned as structured failure text.

## Testing

The first milestone should include focused checks for:

- `create_common_agent` can build the graph with default settings.
- the planner produces a compact plan for a basic non-domain task.
- the local sandbox executes a simple Python snippet and returns stdout.
- the skill registry lists skills and returns details for an existing skill.
- the CLI runner can invoke the graph for a basic non-domain task.

Network-dependent web search should be manually tested or mocked in automated tests.

## Migration Notes

`deep_agents.py` should stop being a stock demo script and become either a thin CLI runner or be replaced by a clearer CLI entry module.

Existing stock-specific files can remain in the repository but should not be registered by default in the common-agent milestone.
