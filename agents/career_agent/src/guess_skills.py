import json
from turtle import title
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"

def guess_skills(title):
    """Ask the local LLM to guess likely skills for a job title."""
    prompt = (f"List the 8 most likely technical skills for the job title '{title}'. "
              'Answer only with JSON like {"skills": ["Python", "SQL"]}.')
    resp = requests.post(OLLAMA_URL, json={
        "model": "qwen2.5:7b",
        "prompt": prompt,
        "format": "json",
        "stream": False,
    })
    answer = json.loads(resp.json()["response"])
    # The model may wrap the list in an object, so unwrap it
    if isinstance(answer, dict):
        answer = next(iter(answer.values()), [])
    return answer

if __name__ == "__main__":
    print(guess_skills("Software Engineer"))