# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for the BigQuery bug-database agent (bq-agent)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.agent import app, root_agent
from app.tools import find_similar_bugs


def _mock_embed_response(values: list[float] | None = None) -> SimpleNamespace:
    vec = values if values is not None else [0.01] * 768
    return SimpleNamespace(embeddings=[SimpleNamespace(values=vec)])


def test_find_similar_bugs_formats_results(monkeypatch) -> None:
    """Verify find_similar_bugs embeds the query and formats matching rows."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")

    fake_row = SimpleNamespace(
        bug_id="BUG-013",
        title="Redis connection pool exhaustion under burst traffic",
        description="Checkout service throws PoolExhaustedError when flash sale starts.",
        resolution="Increase max_connections to 200 and enable exponential backoff.",
        distance=0.1423,
    )

    mock_genai_client = MagicMock()
    mock_genai_client.models.embed_content.return_value = _mock_embed_response()

    mock_bq_client = MagicMock()
    mock_bq_client.query.return_value.result.return_value = [fake_row]

    with (
        patch("app.tools.genai.Client", return_value=mock_genai_client) as genai_cls,
        patch("app.tools.bigquery.Client", return_value=mock_bq_client),
    ):
        result = find_similar_bugs("Redis connection pool exhausted")

    genai_cls.assert_called_once_with(
        vertexai=True,
        project="test-project",
        location="us-central1",
    )
    mock_genai_client.models.embed_content.assert_called_once_with(
        model="text-embedding-004",
        contents="Redis connection pool exhausted",
    )
    assert "BUG-013" in result
    assert "Redis connection pool exhaustion under burst traffic" in result
    assert "Increase max_connections to 200" in result
    assert "0.1423" in result


def test_find_similar_bugs_handles_empty_results(monkeypatch) -> None:
    """Verify find_similar_bugs returns a clear message when no rows match."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")

    mock_genai_client = MagicMock()
    mock_genai_client.models.embed_content.return_value = _mock_embed_response()

    mock_bq_client = MagicMock()
    mock_bq_client.query.return_value.result.return_value = []

    with (
        patch("app.tools.genai.Client", return_value=mock_genai_client),
        patch("app.tools.bigquery.Client", return_value=mock_bq_client),
    ):
        result = find_similar_bugs("obscure error with no matches")

    assert "No relevant historical bugs found" in result


def test_find_similar_bugs_handles_errors_gracefully(monkeypatch) -> None:
    """Verify find_similar_bugs catches exceptions and returns a readable message."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")

    with patch("app.tools.genai.Client", side_effect=RuntimeError("API unavailable")):
        result = find_similar_bugs("NullPointerException")

    assert "Error querying historical bug database" in result
    assert "API unavailable" in result


def test_find_similar_bugs_empty_query() -> None:
    """Verify empty query returns a helpful prompt without calling external APIs."""
    result = find_similar_bugs("   ")
    assert "No search query provided" in result


def test_root_agent_configuration() -> None:
    """Verify root_agent and app exports match ADK & A2A requirements."""
    assert root_agent.name == "bq_agent"
    assert find_similar_bugs in root_agent.tools
    assert app.name == "app"
    assert app.root_agent is root_agent
