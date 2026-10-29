# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.tools import find_similar_bugs

load_dotenv()

MODEL = os.getenv("MODEL", "gemini-3.5-flash")

INSTRUCTION = """You are a specialist bug-database investigator in a multi-agent code-assist system.
Your job is to search the historical production incident database in BigQuery (`code_assist_bugs.known_bugs`) for past bugs that match the user's error message, symptom, or stack trace.

Follow these rules strictly:
1. Always call `find_similar_bugs` with the user's error message, stack trace, or symptom description.
2. Ground your response strictly in the rows returned by `find_similar_bugs`. Never invent bug IDs, root causes, or resolutions.
3. For every relevant match, explicitly cite its `bug_id` (e.g., `BUG-013`), `title`, root cause (`description`), `resolution`, and cosine `distance`.
4. If no relevant historical bug is found (or the returned matches are unrelated to the error), state clearly that no relevant historical bug was found in the database.
"""

root_agent = Agent(
    # Keep in sync with create_params.root_agent_name in agents-cli-manifest.yaml:
    # telemetry reports this name as gen_ai.agent.name, and agents-cli reports the
    # manifest's value. Renaming the agent only here makes the two disagree, and
    # anything selecting traces by name stops finding this agent's.
    name="bq_agent",
    description=(
        "Searches the BigQuery historical production incident database "
        "(code_assist_bugs.known_bugs) using vector similarity search and "
        "returns matching bug IDs, root causes, and resolutions."
    ),
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=INSTRUCTION,
    tools=[find_similar_bugs],
)

app = App(
    root_agent=root_agent,
    name="app",
)
