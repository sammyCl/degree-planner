"""Agent loop: plan, check, revise (plans/AGENT-PLAN.md, task "Agent loop").

Takes an AgentRequest (request_models.py), lets the model call the tools in tools.py until
check_plan says the plan meets the requirements or the step limit is reached, and returns an
AgentResponse: status "ok" with a validated plan, or "cannot_work" with the problems.
The format both ways is docs/agent-request-format.md.
"""

from __future__ import annotations

import sqlite3

from degree_planner_backend.agent.request_models import AgentRequest, AgentResponse


def run_agent(connection: sqlite3.Connection, request: AgentRequest) -> AgentResponse:
    """Plan for the student in request and return the checked result."""
    raise NotImplementedError("Agent loop not built yet")
