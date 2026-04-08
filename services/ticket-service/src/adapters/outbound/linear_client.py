import asyncio
import logging

import httpx

from src import config
from src.ports.outbound import TicketCreator

logger = logging.getLogger(__name__)

GRAPHQL_ENDPOINT = "https://api.linear.app/graphql"

CREATE_ISSUE_MUTATION = """
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue {
      id
      identifier
      url
    }
  }
}
"""

MAX_RETRIES = 2
BACKOFF_SECONDS = [1, 2]


class LinearClient(TicketCreator):
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = http_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def create_issue(
        self,
        title: str,
        body: str,
        priority: int,
        labels: list[str],
        team_id: str,
    ) -> dict:
        client = await self._get_client()
        variables = {
            "input": {
                "title": title,
                "description": body,
                "priority": priority,
                "teamId": team_id,
                "labelIds": labels,
            }
        }
        headers = {
            "Authorization": f"Bearer {config.LINEAR_API_KEY}",
            "Content-Type": "application/json",
        }

        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await client.post(
                    GRAPHQL_ENDPOINT,
                    json={"query": CREATE_ISSUE_MUTATION, "variables": variables},
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                result = data.get("data", {}).get("issueCreate", {})
                if not result.get("success"):
                    errors = data.get("errors", [])
                    raise RuntimeError(f"Linear API returned success=false: {errors}")

                issue = result["issue"]
                logger.info(
                    "Linear issue created: %s (%s)",
                    issue["identifier"],
                    issue["url"],
                )
                return issue

            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    wait = BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "Linear API attempt %d/%d failed: %s — retrying in %ds",
                        attempt + 1,
                        MAX_RETRIES + 1,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "Linear API failed after %d attempts: %s",
                        MAX_RETRIES + 1,
                        exc,
                    )

        raise last_exc  # type: ignore[misc]
