"""
CompanionAgent — handles casual conversation, jokes, and emotional support.

This agent uses Gemini to generate conversational responses but
NEVER triggers system actions. It is purely conversational.

Capabilities:
- tell_joke: Tells a joke
- casual_chat: Handles general conversation
- compliment: Gives a genuine compliment
- motivate: Provides motivation / encouragement
"""

import os
from core.agents.base_agent import BaseAgent, AgentResult
from core.voice_response import speak


class CompanionAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "companion"

    @property
    def description(self) -> str:
        return (
            "Handles casual conversation, jokes, emotional support, "
            "and small talk. Uses Gemini for natural responses. "
            "Does NOT trigger any system actions."
        )

    def __init__(self):
        super().__init__()
        self.register_action("tell_joke",   self._tell_joke)
        self.register_action("casual_chat", self._casual_chat)
        self.register_action("compliment",  self._compliment)
        self.register_action("motivate",    self._motivate)

    def _ask_gemini_companion(self, prompt: str) -> str:
        """
        Ask Gemini a conversational question.
        Returns response text, or a fallback if Gemini fails.
        """
        try:
            from google import genai
            from dotenv import load_dotenv
            load_dotenv()

            api_key = os.getenv("API_KEY")
            if not api_key:
                return self._fallback_response(prompt)

            client = genai.Client(api_key=api_key)

            system = (
                "You are Jarvis, a witty and friendly AI companion. "
                "You're having a casual chat with your best friend. "
                "Keep responses short (1-3 sentences), funny, warm, and genuine. "
                "Never sound robotic or use corporate language. "
                "Be yourself — sarcastic sometimes, supportive always."
            )

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"{system}\n\nUser: {prompt}\nJarvis:"
            )
            return response.text.strip()

        except Exception as e:
            print(f"⚠️  CompanionAgent Gemini error: {e}")
            return self._fallback_response(prompt)

    def _fallback_response(self, prompt: str) -> str:
        """Offline fallback responses when Gemini is unavailable."""
        prompt_lower = prompt.lower()

        if any(w in prompt_lower for w in ["joke", "funny", "laugh"]):
            import random
            jokes = [
                "Why do programmers prefer dark mode? Because light attracts bugs.",
                "I told my computer a joke. It crashed. Guess it couldn't handle the punchline.",
                "Why did the developer go broke? Because he used up all his cache.",
                "There are 10 types of people — those who understand binary, and those who don't.",
                "A SQL query walks into a bar, sees two tables, and asks... Can I JOIN you?",
            ]
            return random.choice(jokes)

        if any(w in prompt_lower for w in ["sad", "down", "upset", "tired"]):
            return "Hey — it's okay to have tough days. You've got this. Take a breath."

        if any(w in prompt_lower for w in ["bored", "boring"]):
            return "Bored? Want me to roast your code instead? Just kidding... mostly."

        return "I'm here if you need anything. What's on your mind?"

    # ─── Actions ─────────────────────────────────────────────

    def _tell_joke(self, params: dict) -> AgentResult:
        """Tells a joke."""
        response = self._ask_gemini_companion(
            params.get("query", "Tell me a funny programming joke")
        )
        speak(response)
        return AgentResult(
            success=True, action="tell_joke",
            result=response, data={"response": response}
        )

    def _casual_chat(self, params: dict) -> AgentResult:
        """Handles general conversation."""
        query = params.get("query", params.get("command", "hey, what's up"))
        response = self._ask_gemini_companion(query)
        speak(response)
        return AgentResult(
            success=True, action="casual_chat",
            result=response, data={"response": response}
        )

    def _compliment(self, params: dict) -> AgentResult:
        """Gives a genuine compliment."""
        response = self._ask_gemini_companion(
            "Give the user a genuine, specific compliment about their work ethic"
        )
        speak(response)
        return AgentResult(
            success=True, action="compliment",
            result=response, data={"response": response}
        )

    def _motivate(self, params: dict) -> AgentResult:
        """Provides motivation and encouragement."""
        response = self._ask_gemini_companion(
            params.get("query", "Give me a short motivational boost")
        )
        speak(response)
        return AgentResult(
            success=True, action="motivate",
            result=response, data={"response": response}
        )


# ─── Quick test ──────────────────────────────────────────────
if __name__ == "__main__":
    agent = CompanionAgent()
    print("Testing CompanionAgent...")
    print(agent.execute("tell_joke", {}))
    print(agent.execute("casual_chat", {"query": "how are you doing today?"}))
