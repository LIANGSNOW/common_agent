# Common Agent

This project is being refactored into a domain-neutral common agent. The first milestone is a CLI demo runner built around a lightweight planner, CodeAct execution, skill discovery, and trusted local Python execution.

## CLI Demo

Create a `.env` file with the LLM settings expected by `src/config/llm_config.py`:

```env
llm_model_name=your-model
llm_api_key=your-api-key
llm_base_url=your-base-url
llm_temperature=0.7
```

Run:

```bash
python -m src.cli_common_agent
```

The first sandbox implementation executes local Python with normal local privileges. Use it only in trusted local development environments.
