from typing import Callable

import llm
from config import MAX_TOKENS, MODEL, SUPPORT_SYSTEM_PROMPT
from tools import TOOL_SCHEMAS, execute_tool

MAX_ITERATIONS = 10


class Agent:
    """A stateless agent: the loop runs over a messages list it is handed.

    State lives elsewhere (see Conversation). The loop mutates the list in
    place so the caller keeps the full history — tool_use and tool_result
    blocks included.
    """

    def __init__(
        self,
        system: str = SUPPORT_SYSTEM_PROMPT,
        *,
        tools: list[dict] = TOOL_SCHEMAS,
        model: str = MODEL,
        max_tokens: int = MAX_TOKENS,
        temperature: float | None = 0,
        execute: Callable[[str, dict], tuple[str, bool]] | None = None,
    ):
        self.system = system
        self.tools = tools
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        # The executor is a seam: pass a scoped or dispatching callable to
        # route tool_use blocks somewhere other than the global tool table.
        self.execute = execute if execute is not None else execute_tool

    def chat(self, user_message: str) -> str:
        """One-shot convenience: fresh list, single turn, no memory."""
        messages = [{"role": "user", "content": user_message}]
        return self.run(messages)

    def run(self, messages: list[dict]) -> str:
        """Run the agent loop over `messages`, appending as it goes."""
        for _ in range(MAX_ITERATIONS):
            response = llm.ask(
                messages,
                system=self.system,
                tools=self.tools,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                model=self.model,
            )
            if response.stop_reason == "end_turn":
                return llm.text(response)
            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                results = []
                for block in llm.tool_uses(response):
                    content, is_error = self.execute(block.name, block.input)
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content,
                            "is_error": is_error,
                        }
                    )
                messages.append({"role": "user", "content": results})
                continue
            raise RuntimeError(
                f"Model stopped unexpectedly: stop_reason={response.stop_reason!r}"
            )
        raise RuntimeError(f"Loop did not finish within {MAX_ITERATIONS} iterations")