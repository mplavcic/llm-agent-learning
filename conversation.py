from agent import Agent


class Conversation:
    """A persistent session: the messages list IS the memory.

    The agent loop never changed between Parts 4 and 5. What changed is
    where the messages list lives — on this object, which outlives a single
    turn, instead of a local variable thrown away after each call.
    """

    def __init__(self, agent: Agent | None = None, user_id: str | None = None):
        self.agent = agent if agent is not None else Agent()
        self.user_id = user_id
        self.messages: list[dict] = []
        self.turn_count = 0

    def send(self, user_message: str) -> str:
        if self.turn_count == 0 and self.user_id:
            user_message = f"[user_id: {self.user_id}]\n\n{user_message}"
        self.messages.append({"role": "user", "content": user_message})
        # The loop appends tool_use / tool_result blocks to self.messages
        # in place. We keep them all: they are reasoning history, not trash.
        final_text = self.agent.run(self.messages)
        self.messages.append({"role": "assistant", "content": final_text})
        self.turn_count += 1
        return final_text
