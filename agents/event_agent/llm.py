import httpx
from pydantic import BaseModel


class ModelUnavailable(ValueError):
    pass


def structured(client: httpx.Client, *, key, model, base_url, schema: type[BaseModel], content):
    if not key:
        raise ModelUnavailable("An agent model API key is missing")
    try:
        response = client.post(
            f"{base_url.rstrip('/')}/responses",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model, "store": False, "max_output_tokens": 12000,
                "text": {"format": {
                    "type": "json_schema", "name": schema.__name__, "strict": True, "schema": schema.model_json_schema(),
                }},
                "input": [{"role": "user", "content": content}],
            },
        )
        response.raise_for_status()
        payload = response.json()
        parts = [
            part["text"] for item in payload.get("output", []) for part in item.get("content", [])
            if part.get("type") == "output_text"
        ]
        if payload.get("status") != "completed" or not parts:
            raise ValueError("The model response was incomplete")
        return schema.model_validate_json("".join(parts))
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        if status == 429:
            raise ModelUnavailable("The AI provider rate-limited the request (HTTP 429)") from error
        raise ModelUnavailable(f"The AI provider rejected the request (HTTP {status})") from error
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise ModelUnavailable("The agent model did not return a valid response") from error
