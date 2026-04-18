"""
ManagerAgent — The Orchestrator.

This is the central brain that:
1. Analyzes complex user requests
2. Decides if it's a single-step or multi-step task
3. Builds a TaskGraph for multi-step tasks
4. Dispatches to specialized agents
5. Synthesizes the final spoken response

Architecture:
    User Command → ManagerAgent.plan()
        → Single step? → route to agent directly
        → Multi-step?  → build TaskGraph → execute via GraphExecutor
        → Chat/question? → route to Gemini directly
"""

import json
import os
import time
from typing import Optional
from google import genai
from dotenv import load_dotenv

from core.agents.base_agent import AgentResult
from core.graph.task_graph import TaskGraph, GraphExecutor, NodeStatus
from core.network.connectivity import require_online
from core.voice_response import speak, speak_instant
from core.memory import get_context_for_gemini, save_exchange, update_context, get_last_file, get_last_context
from mood.mood_engine import get_mood_for_prompt
from core.logger import log_interaction

load_dotenv()

# ─── Settings ────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("API_KEY")
MODEL          = "gemini-3.1-flash-lite-preview"
MAX_PLAN_STEPS = 8
MAX_REPLANS    = 1             # Max self-healing retries per command
# ─────────────────────────────────────────────────────────────

client = genai.Client(api_key=GEMINI_API_KEY)


class ManagerAgent:
    """
    The Orchestrator agent. Does NOT execute actions itself —
    it plans and delegates to specialized agents.
    """

    def __init__(self, agents: dict, actions: dict):
        """
        Args:
            agents:  dict of agent_name → BaseAgent instance
            actions: the original ACTIONS dict from main.py (for legacy compat)
        """
        self._agents  = agents    # {"filesystem": FileSystemAgent, "system": SystemControlAgent, ...}
        self._actions = actions   # Original ACTIONS dict
        self._graph_executor = GraphExecutor(
            agent_registry=self._build_agent_dispatch(),
            max_parallel=3,
            on_node_start=self._on_node_start,
            on_node_done=self._on_node_done,
        )

    def _build_agent_dispatch(self) -> dict:
        """
        Creates the agent_registry dict for GraphExecutor.
        Maps agent_name → callable(action, params) → result.
        """
        dispatch = {}
        for agent_name, agent in self._agents.items():
            def make_handler(a):
                def handler(action, params):
                    result = a.execute(action, params)
                    if result.success:
                        return result.result
                    raise RuntimeError(result.error)
                return handler
            dispatch[agent_name] = make_handler(agent)
        return dispatch

    def _on_node_start(self, node):
        """Called when a task graph node starts executing."""
        print(f"   🔄 [{node.agent}] Starting: {node.description}")

    def _on_node_done(self, node):
        """Called when a task graph node completes."""
        pass  # Logging handled by GraphExecutor

    def _get_agent_descriptions(self) -> str:
        """Builds a combined description of all available agents + tools."""
        descriptions = []
        for name, agent in self._agents.items():
            descriptions.append(agent.tools_description)
        return "\n\n".join(descriptions)

    # ─── Plan Prompt ─────────────────────────────────────────
    def _build_plan_prompt(self, command: str) -> str:
        """Builds the Gemini prompt for task planning."""
        user_context = get_context_for_gemini()
        mood_context = get_mood_for_prompt()
        agent_desc   = self._get_agent_descriptions()

        # ── Inject working memory (last file + last action) ──
        last_file    = get_last_file()
        last_ctx     = get_last_context()
        working_mem  = ""
        if last_file:
            working_mem += f'Last file touched: "{last_file["filename"]}" (action: {last_file.get("action", "unknown")})\n'
        if last_ctx.get("action"):
            working_mem += f'Last action taken: {last_ctx["action"]} on "{last_ctx.get("target", "")}"\n'
        if working_mem:
            working_mem = f"\nCurrent working context (use this to resolve 'that file', 'it', 'the file you just created'):\n{working_mem}"

        return f"""You are Jarvis's planning brain. Analyze the user's command and create an execution plan.

{user_context}
{mood_context}
{working_mem}
Available agents and their tools:
{agent_desc}

User's command: "{command}"

Respond with ONLY a JSON object. No markdown. No explanation.

If the command needs MULTIPLE steps, return a task graph:
{{
    "type": "graph",
    "thought": "Brief explanation of your reasoning and what you extracted from the command",
    "name": "short_task_name",
    "steps": [
        {{"id": "step_0", "agent": "agent_name", "action": "action_name", "params": {{}}, "depends_on": [], "description": "What this step does"}},
        {{"id": "step_1", "agent": "agent_name", "action": "action_name", "params": {{}}, "depends_on": ["step_0"], "description": "What this step does"}}
    ],
    "response": "Short spoken confirmation (max 8 words)"
}}

If the command is a SINGLE action, route directly:
{{
    "type": "single",
    "thought": "Brief explanation of your reasoning and what you extracted from the command",
    "agent": "agent_name",
    "action": "action_name",
    "params": {{}},
    "response": "Short spoken confirmation (max 8 words)"
}}

If the command is a question or chat (no system action needed):
{{
    "type": "chat",
    "thought": "Why I think this is chat, not an action",
    "response": "Natural conversational response (2-3 sentences max)"
}}

CRITICAL RULES FOR PARAMS:
- You MUST fill in ALL "REQUIRED" params listed in the tool description above.
- Extract names, filenames, targets from the user's natural speech. DO NOT leave params empty.
- For file operations: if user says "text file" or "txt", append ".txt" to the filename.
  Example: "create a file named superman and it should be a text file" → params: {{"name": "superman.txt"}}
- For file operations: if user says "pdf", append ".pdf". If no extension mentioned, default to ".txt".
- Ignore filler words like "kind of", "I mean", "actually", "I want you to".
- Focus on extracting the REAL intent — the noun (filename, app name) and the action verb.

OTHER RULES:
- Use the correct agent for each action
- If a step depends on another step's output, add it to depends_on
- Keep spoken responses SHORT (max 8 words). Sound human, not robotic.
- For questions, answer directly and conversationally
- NEVER make up actions that don't exist in the agent descriptions
- Use contractions (don't, can't, won't). Talk like a friend.
"""

    # ─── Execute ─────────────────────────────────────────────
    def run(self, command: str) -> str:
        """
        Main entry point. Analyzes the command and executes.

        Returns:
            Result string for logging.
        """
        start_time = time.time()
        print(f"\n🤖 ManagerAgent: Planning for '{command}'")

        # Check connectivity for Gemini
        if not require_online(speak):
            return "Offline — cannot plan"

        # Get the plan from Gemini
        plan = self._get_plan(command)
        if not plan:
            speak("Had trouble understanding that. Try again?")
            return "Planning failed"

        print(f"📋 Plan type: {plan.get('type', 'unknown')}")

        # ── Debug: Log AI reasoning (training mode) ──────────
        thought = plan.get("thought", "")
        if thought:
            print(f"🧠 AI Reasoning: {thought}")
        if plan.get("params"):
            print(f"📦 Extracted params: {plan.get('params')}")

        # ── Chat response (no action) ────────────────────────
        if plan["type"] == "chat":
            response = plan.get("response", "I'm not sure about that.")
            speak(response)
            save_exchange(command, response)
            self._log(command, "chat_response", start_time, response=response)
            return f"Chat: {response[:50]}"

        # ── Single action ────────────────────────────────────
        if plan["type"] == "single":
            return self._execute_single(command, plan, start_time)

        # ── Task graph (multi-step) ──────────────────────────
        if plan["type"] == "graph":
            return self._execute_graph(command, plan, start_time)

        speak("I understood but I'm not sure how to handle that.")
        return "Unknown plan type"

    def _get_plan(self, command: str) -> Optional[dict]:
        """Calls Gemini to generate an execution plan."""
        prompt = self._build_plan_prompt(command)

        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                )
                text  = response.text.strip()
                clean = text.replace("```json", "").replace("```", "").strip()
                plan  = json.loads(clean)
                return plan

            except json.JSONDecodeError:
                # Gemini returned non-JSON — treat as chat
                return {"type": "chat", "response": text}

            except Exception as e:
                if "429" in str(e):
                    print(f"❌ Rate limited. Failing fast to prevent freeze.")
                    return None
                else:
                    print(f"❌ Planning error: {e}")
                    return None
        return None

    def _execute_single(self, command: str, plan: dict, start_time: float, replan_count: int = 0) -> str:
        """Executes a single-step plan by routing to the correct agent."""
        agent_name = plan.get("agent", "")
        action     = plan.get("action", "")
        params     = plan.get("params", {})
        response   = plan.get("response", "On it.")

        if agent_name not in self._agents:
            speak("I know what you want but I don't have the right agent for it.")
            return f"Unknown agent: {agent_name}"

        # Speak the instant response
        speak_instant(response)

        # Execute
        agent = self._agents[agent_name]
        result = agent.execute(action, params)

        if result.success:
            print(f"Single action result: {result.result}")
            update_context(
                action=action,
                target=params.get("target", params.get("name", "")),
                result=result.result,
                command=command,
            )
            save_exchange(command, response)
            self._log(command, action, start_time, response=response)
            return result.result
        else:
            print(f"Single action failed: {result.error}")

            # Self-healing: try alternative action
            if replan_count < MAX_REPLANS:
                alt_plan = self._replan_on_failure(
                    command, action, result.error
                )
                if alt_plan and alt_plan.get("type") != "give_up":
                    print(f"[REPLAN] {action} -> {alt_plan.get('action', '?')}")
                    speak_instant("Let me try a different approach.")
                    return self._execute_single(
                        command, alt_plan, start_time,
                        replan_count=replan_count + 1
                    )

            speak(f"That didn't work. {result.error}")
            self._log(command, f"{action}_failed", start_time, response=result.error)
            return f"Failed: {result.error}"

    def _replan_on_failure(self, command: str, failed_action: str, error: str) -> Optional[dict]:
        """
        Self-healing: ask Gemini for an alternative action when the first fails.

        Example: open_app("claw") failed -> web_search("OpenClaw app")
        """
        agent_desc = self._get_agent_descriptions()

        prompt = f"""You are Jarvis's recovery brain. The action '{failed_action}' failed.

Error: "{error}"
Original user command: "{command}"

Available agents and tools:
{agent_desc}

Suggest ONE alternative action that could fulfill the user's intent.
Return ONLY JSON, no markdown:
{{"type":"single","agent":"agent_name","action":"action_name","params":{{}},"response":"Short spoken message (max 8 words)"}}

If no alternative makes sense, return:
{{"type":"give_up"}}

RULES:
- Do NOT retry the same action that failed
- Think creatively: if app not found, try web search; if file not found, try creating it
- Keep the response SHORT and human"""

        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )
            text  = response.text.strip()
            clean = text.replace("```json", "").replace("```", "").strip()
            plan  = json.loads(clean)
            return plan
        except Exception as e:
            print(f"Re-plan failed: {e}")
            return None

    def _execute_graph(self, command: str, plan: dict, start_time: float) -> str:
        """Builds and executes a TaskGraph from the plan."""
        graph_name = plan.get("name", "multi_step_task")
        steps      = plan.get("steps", [])
        response   = plan.get("response", "Working on it.")

        if not steps:
            speak("I built a plan but it was empty. Try again?")
            return "Empty graph"

        # Speak instant ack
        speak_instant(response)

        # Build the graph
        graph = TaskGraph(name=graph_name)
        id_map = {}  # step_id → graph_node_id

        for step in steps:
            step_id = step.get("id", f"step_{len(id_map)}")
            deps = [id_map[d] for d in step.get("depends_on", []) if d in id_map]

            node_id = graph.add_node(
                agent=step["agent"],
                action=step["action"],
                params=step.get("params", {}),
                depends_on=deps,
                description=step.get("description", f"{step['agent']}.{step['action']}"),
            )
            id_map[step_id] = node_id

        print(f"📊 Built graph: {graph.summary()}")

        # Execute the graph
        result_graph = self._graph_executor.execute(graph)

        # Synthesize result
        trace = result_graph.get_execution_trace()
        total_ms = (time.time() - start_time) * 1000

        if result_graph.has_failures:
            failed = [t for t in trace if t["status"] == "failed"]
            speak(f"Had trouble with one of the steps. {failed[0].get('error', '')}")
            self._log(command, "graph_partial_fail", start_time, response=str(trace))
            return f"Graph partially failed: {trace}"
        else:
            # Get the last step's result for speaking
            last_result = trace[-1].get("result", "Done") if trace else "Done"
            print(f"✅ Graph complete in {total_ms:.0f}ms")

            update_context(
                action=graph_name,
                target="",
                result=last_result,
                command=command,
            )
            save_exchange(command, response)
            self._log(command, f"graph_{graph_name}", start_time, response=last_result)
            return f"Graph complete: {last_result}"

    def _log(self, command: str, action: str, start_time: float, response: str = ""):
        """Logs the interaction."""
        latency_ms = (time.time() - start_time) * 1000
        log_interaction(
            you_said=command,
            action_taken=action,
            was_understood=True,
            intent_source="manager_agent",
            latency_ms=latency_ms,
            gemini_response=response,
            sent_to_gemini=True,
        )

    def get_agent(self, name: str):
        """Returns a specific agent by name."""
        return self._agents.get(name)

    def list_agents(self) -> list:
        """Returns list of all registered agent names."""
        return list(self._agents.keys())

    def shutdown(self):
        """Cleanly shuts down the executor."""
        self._graph_executor.shutdown()
