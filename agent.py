import llm
from config import MAX_TOKENS, MODEL
from tools import TOOL_SCHEMAS, execute_tool

MAX_ITERATIONS = 10


class Agent:
    """A stateless agent: one chat() call runs one fresh conversation."""

    def __init__(
        self,
        system: str,
        *,
        tools: list[dict] = TOOL_SCHEMAS,
        model: str = MODEL,
        max_tokens: int = MAX_TOKENS,
        temperature: float | None = 0,
    ):
        self.system = system
        self.tools = tools
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def chat(self, user_message: str) -> str:
        messages = [{"role": "user", "content": user_message}]
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
                    content, is_error = execute_tool(block.name, block.input)
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