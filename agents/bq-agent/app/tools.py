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

"""BigQuery vector-search tool for searching historical production incidents."""

from __future__ import annotations

import logging
import os

from google import genai
from google.cloud import bigquery

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_LOCATION = "us-central1"
DATASET_ID = os.getenv("BQ_DATASET", "code_assist_bugs")
TABLE_ID = os.getenv("BQ_TABLE", "known_bugs")
TOP_K = 3


def find_similar_bugs(query: str) -> str:
    """Search the historical production bug database for similar incidents.

    Embeds the error message, symptom, or stack trace with ``text-embedding-004``
    and runs a BigQuery ``VECTOR_SEARCH`` query (cosine distance, top 3 matches)
    against ``code_assist_bugs.known_bugs``.

    Args:
        query: Error message, stack trace, or symptom description to search for.

    Returns:
        A formatted summary of the closest matching historical bugs including
        ``bug_id``, ``title``, ``description``, ``resolution``, and cosine
        ``distance``, or an informative message if no matches are found or an
        error occurs.
    """
    if not query or not query.strip():
        return "No search query provided. Please provide an error message or symptom."

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    try:
        genai_client = genai.Client(
            vertexai=True,
            project=project_id,
            location=EMBEDDING_LOCATION,
        )
        embed_response = genai_client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=query,
        )
        if not embed_response.embeddings or not embed_response.embeddings[0].values:
            return "Failed to generate an embedding vector for the query."
        query_vector = list(embed_response.embeddings[0].values)

        bq_client = bigquery.Client(project=project_id)
        resolved_project = project_id or bq_client.project
        table_ref = f"`{resolved_project}.{DATASET_ID}.{TABLE_ID}`"

        sql = f"""
            SELECT
                base.bug_id AS bug_id,
                base.title AS title,
                base.description AS description,
                base.resolution AS resolution,
                distance
            FROM VECTOR_SEARCH(
                TABLE {table_ref},
                'description_embedding',
                (SELECT @query_embedding AS embedding),
                top_k => {TOP_K},
                distance_type => 'COSINE'
            )
            ORDER BY distance ASC
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter(
                    "query_embedding", "FLOAT64", query_vector
                ),
            ]
        )

        rows = list(bq_client.query(sql, job_config=job_config).result())
        if not rows:
            return f"No relevant historical bugs found matching: '{query}'."

        formatted_matches: list[str] = []
        for idx, row in enumerate(rows, start=1):
            distance_val = (
                f"{float(row.distance):.4f}"
                if getattr(row, "distance", None) is not None
                else "N/A"
            )
            formatted_matches.append(
                f"Match {idx}: [{row.bug_id}] {row.title} (cosine distance: {distance_val})\n"
                f"  Description: {row.description}\n"
                f"  Resolution: {row.resolution}"
            )
        return "\n\n".join(formatted_matches)
    except Exception as exc:
        logger.exception("Error searching BigQuery bug database")
        return f"Error querying historical bug database: {exc}"
