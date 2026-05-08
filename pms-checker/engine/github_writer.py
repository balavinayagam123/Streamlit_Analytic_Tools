"""
github_writer.py
Writes updated JSON reference data back to the GitHub repo via the API.
Token and repo are read from Streamlit secrets.
"""
import base64
import json
import requests


def _headers(token: str) -> dict:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}


def get_file_sha(repo: str, filepath: str, token: str) -> str | None:
    url = f"https://api.github.com/repos/{repo}/contents/{filepath}"
    r = requests.get(url, headers=_headers(token), timeout=10)
    if r.status_code == 200:
        return r.json().get("sha")
    return None


def push_json(repo: str, filepath: str, data, token: str, message: str = "Update reference data") -> bool:
    """
    Push updated JSON to GitHub. Returns True on success.
    filepath should be e.g. 'data/transform_map.json'
    """
    url = f"https://api.github.com/repos/{repo}/contents/{filepath}"
    sha = get_file_sha(repo, filepath, token)

    content = base64.b64encode(
        json.dumps(data, indent=2).encode("utf-8")
    ).decode("utf-8")

    payload = {"message": message, "content": content}
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=_headers(token), json=payload, timeout=15)
    return r.status_code in (200, 201)
