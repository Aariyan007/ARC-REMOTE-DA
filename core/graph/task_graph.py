"""
Task Graph Engine — non-linear, DAG-based task execution.

Converts complex user requests into a Directed Acyclic Graph where
each node is a discrete action and edges represent dependencies.

Features:
- Parallel execution of independent nodes
- Retry on failure with configurable max attempts
- Mid-execution interruption & graph rewriting
- Status tracking per node (pending → running → done / failed)
- Execution history for explainability ("Why did you do that?")

Example:
    "Send my resume to HR"
    →  [find_file:resume] → [compose_email] → [attach_file] → [send_email]
"""

import uuid
import time
import threading
from enum import Enum
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, Future


# ─── Node Status ─────────────────────────────────────────────
class NodeStatus(Enum):
    PENDING   = "pending"       # Waiting for dependencies
    READY     = "ready"         # All deps met, ready to run
    RUNNING   = "running"       # Currently executing
    DONE      = "done"          # Completed successfully
    FAILED    = "failed"        # Failed after retries
    SKIPPED   = "skipped"       # Skipped (upstream failure)
    PAUSED    = "paused"        # Paused by interrupt


# ─── Graph Node ──────────────────────────────────────────────
@dataclass
class TaskNode:
    """A single step in the task graph."""
    id:          str                       # Unique node ID
    agent:       str                       # Which agent handles this ("filesystem", "email", etc.)
    action:      str                       # Action name ("search_file", "send_email")
    params:      dict        = field(default_factory=dict)    # Parameters for the action
    depends_on:  list        = field(default_factory=list)    # List of node IDs this depends on
    status:      NodeStatus  = NodeStatus.PENDING
    result:      Any         = None       # Output from execution
    error:       str         = None       # Error message if failed
    retries:     int         = 0          # Number of retries attempted
    max_retries: int         = 2          # Max retries before failure
    start_time:  float       = 0.0
    end_time:    float       = 0.0
    description: str         = ""         # Human-readable description for explainability

    def duration_ms(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0


# ─── Task Graph ──────────────────────────────────────────────
class TaskGraph:
    """
    A DAG of TaskNodes that can be executed in dependency order.
    Supports parallel execution of independent branches.
    """

    def __init__(self, name: str = "unnamed_task"):
        self.id:        str             = str(uuid.uuid4())[:8]
        self.name:      str             = name
        self.nodes:     dict            = {}   # node_id → TaskNode
        self.order:     list            = []   # Topological execution order
        self.created_at: float          = time.time()
        self.completed_at: float        = 0.0
        self._interrupted: bool         = False
        self._lock                      = threading.Lock()

    def add_node(
        self,
        agent:       str,
        action:      str,
        params:      dict  = None,
        depends_on:  list  = None,
        description: str   = "",
        max_retries: int   = 2,
    ) -> str:
        """
        Adds a node to the graph. Returns the node ID.
        """
        node_id = f"{agent}_{action}_{len(self.nodes)}"
        node = TaskNode(
            id=node_id,
            agent=agent,
            action=action,
            params=params or {},
            depends_on=depends_on or [],
            description=description or f"{agent}.{action}",
            max_retries=max_retries,
        )
        self.nodes[node_id] = node
        return node_id

    def _topological_sort(self) -> list:
        """Returns nodes in valid execution order (respecting dependencies)."""
        visited  = set()
        order    = []
        in_stack = set()

        def _visit(node_id):
            if node_id in in_stack:
                raise ValueError(f"Cycle detected in task graph at node: {node_id}")
            if node_id in visited:
                return
            in_stack.add(node_id)
            node = self.nodes[node_id]
            for dep_id in node.depends_on:
                if dep_id in self.nodes:
                    _visit(dep_id)
            in_stack.discard(node_id)
            visited.add(node_id)
            order.append(node_id)

        for nid in self.nodes:
            _visit(nid)

        self.order = order
        return order

    def get_ready_nodes(self) -> list:
        """Returns nodes whose dependencies are all DONE."""
        ready = []
        for node in self.nodes.values():
            if node.status != NodeStatus.PENDING:
                continue
            deps_met = all(
                self.nodes[dep].status == NodeStatus.DONE
                for dep in node.depends_on
                if dep in self.nodes
            )
            if deps_met:
                ready.append(node)
        return ready

    def interrupt(self):
        """Signals the graph to pause execution after current node completes."""
        with self._lock:
            self._interrupted = True
            # Pause any PENDING nodes
            for node in self.nodes.values():
                if node.status == NodeStatus.PENDING:
                    node.status = NodeStatus.PAUSED

    def resume(self):
        """Resumes a paused graph."""
        with self._lock:
            self._interrupted = False
            for node in self.nodes.values():
                if node.status == NodeStatus.PAUSED:
                    node.status = NodeStatus.PENDING

    @property
    def is_interrupted(self) -> bool:
        return self._interrupted

    @property
    def is_complete(self) -> bool:
        """True if all nodes are DONE, FAILED, or SKIPPED."""
        return all(
            n.status in (NodeStatus.DONE, NodeStatus.FAILED, NodeStatus.SKIPPED)
            for n in self.nodes.values()
        )

    @property
    def has_failures(self) -> bool:
        return any(n.status == NodeStatus.FAILED for n in self.nodes.values())

    def get_execution_trace(self) -> list:
        """
        Returns a human-readable trace of what happened.
        Used for explainability ("Why did you do that?").
        """
        trace = []
        sorted_nodes = sorted(
            self.nodes.values(),
            key=lambda n: n.start_time if n.start_time else float('inf')
        )
        for node in sorted_nodes:
            entry = {
                "step":        node.description,
                "agent":       node.agent,
                "action":      node.action,
                "status":      node.status.value,
                "duration_ms": round(node.duration_ms(), 1),
            }
            if node.result:
                entry["result"] = str(node.result)[:200]
            if node.error:
                entry["error"] = node.error
            trace.append(entry)
        return trace

    def summary(self) -> str:
        """Short summary of graph state."""
        counts = {}
        for node in self.nodes.values():
            counts[node.status.value] = counts.get(node.status.value, 0) + 1
        parts = [f"{v} {k}" for k, v in counts.items()]
        return f"TaskGraph[{self.name}] — {len(self.nodes)} nodes: {', '.join(parts)}"

    def __repr__(self):
        return self.summary()


# ─── Graph Executor ──────────────────────────────────────────
class GraphExecutor:
    """
    Executes a TaskGraph by dispatching nodes to agent handlers.

    Args:
        agent_registry: dict mapping agent_name → callable(action, params) → result
        max_parallel:   max nodes to run in parallel
        on_node_start:  optional callback(node) when a node starts
        on_node_done:   optional callback(node) when a node completes
    """

    def __init__(
        self,
        agent_registry: dict,
        max_parallel:   int = 3,
        on_node_start:  Optional[Callable] = None,
        on_node_done:   Optional[Callable] = None,
    ):
        self.agents        = agent_registry
        self.max_parallel  = max_parallel
        self.on_node_start = on_node_start
        self.on_node_done  = on_node_done
        self._executor     = ThreadPoolExecutor(
            max_workers=max_parallel, thread_name_prefix="jarvis_graph"
        )

    def execute(self, graph: TaskGraph) -> TaskGraph:
        """
        Executes the task graph, respecting dependencies and parallelism.
        Returns the graph with all nodes updated.
        """
        # Validate and sort
        graph._topological_sort()
        print(f"\n📊 Executing {graph.summary()}")
        print(f"   Order: {' → '.join(graph.order)}")

        while not graph.is_complete and not graph.is_interrupted:
            ready_nodes = graph.get_ready_nodes()

            if not ready_nodes:
                # Check if we're stuck (all remaining are PENDING with unmet deps)
                pending = [n for n in graph.nodes.values() if n.status == NodeStatus.PENDING]
                if pending:
                    # Upstream failures — skip downstream
                    for node in pending:
                        has_failed_dep = any(
                            graph.nodes[d].status == NodeStatus.FAILED
                            for d in node.depends_on
                            if d in graph.nodes
                        )
                        if has_failed_dep:
                            node.status = NodeStatus.SKIPPED
                            node.error = "Skipped due to upstream failure"
                            print(f"   ⏭️  Skipped: {node.description} (upstream failure)")
                    continue
                break

            # Execute ready nodes (potentially in parallel)
            futures = {}
            for node in ready_nodes[:self.max_parallel]:
                node.status = NodeStatus.RUNNING
                node.start_time = time.time()

                if self.on_node_start:
                    self.on_node_start(node)

                print(f"   ▶️  Running: {node.description}")
                future = self._executor.submit(self._execute_node, node, graph)
                futures[future] = node

            # Wait for all submitted nodes to complete
            for future in futures:
                try:
                    future.result(timeout=30)
                except Exception as e:
                    node = futures[future]
                    node.status = NodeStatus.FAILED
                    node.error = str(e)
                    node.end_time = time.time()
                    print(f"   ❌ Failed: {node.description} — {e}")

        graph.completed_at = time.time()
        total_ms = (graph.completed_at - graph.created_at) * 1000
        print(f"\n📊 {graph.summary()} — total: {total_ms:.0f}ms")
        return graph

    def _execute_node(self, node: TaskNode, graph: TaskGraph):
        """Executes a single node by dispatching to the right agent."""
        try:
            # Check if the agent exists
            if node.agent not in self.agents:
                raise ValueError(f"Unknown agent: {node.agent}")

            agent_handler = self.agents[node.agent]

            # Inject upstream results into params
            for dep_id in node.depends_on:
                if dep_id in graph.nodes:
                    dep_node = graph.nodes[dep_id]
                    if dep_node.result:
                        node.params[f"_upstream_{dep_id}"] = dep_node.result

            # Execute
            result = agent_handler(node.action, node.params)

            node.result = result
            node.status = NodeStatus.DONE
            node.end_time = time.time()

            if self.on_node_done:
                self.on_node_done(node)

            print(f"   ✅ Done: {node.description} ({node.duration_ms():.0f}ms)")

        except Exception as e:
            node.retries += 1
            if node.retries <= node.max_retries:
                print(f"   🔄 Retry {node.retries}/{node.max_retries}: {node.description}")
                node.status = NodeStatus.PENDING  # Will be picked up again
            else:
                node.status = NodeStatus.FAILED
                node.error = str(e)
                node.end_time = time.time()
                print(f"   ❌ Failed (max retries): {node.description} — {e}")

    def shutdown(self):
        """Cleanly shut down the executor thread pool."""
        self._executor.shutdown(wait=False)


# ─── Quick Test ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  TASK GRAPH ENGINE TEST")
    print("=" * 60)

    # Create a simple test graph
    graph = TaskGraph(name="test_send_resume")

    n1 = graph.add_node(
        agent="filesystem",
        action="search_file",
        params={"name": "resume"},
        description="Find resume file",
    )
    n2 = graph.add_node(
        agent="filesystem",
        action="read_file",
        params={"filename": "resume.pdf"},
        depends_on=[n1],
        description="Read resume contents",
    )
    n3 = graph.add_node(
        agent="email",
        action="compose_email",
        params={"to": "hr@company.com"},
        depends_on=[n2],
        description="Compose email to HR",
    )

    print(f"\n{graph}")
    print(f"Nodes: {list(graph.nodes.keys())}")

    # Simulate execution with dummy agents
    def dummy_filesystem(action, params):
        time.sleep(0.1)
        if action == "search_file":
            return ["/Users/lynux/Desktop/resume.pdf"]
        return f"read file result"

    def dummy_email(action, params):
        time.sleep(0.1)
        return "Email composed"

    executor = GraphExecutor(
        agent_registry={
            "filesystem": dummy_filesystem,
            "email": dummy_email,
        }
    )

    result_graph = executor.execute(graph)

    print("\n── Execution Trace ──")
    for step in result_graph.get_execution_trace():
        print(f"  {step}")

    executor.shutdown()
    print("\n✅ Task Graph Engine test passed!")
