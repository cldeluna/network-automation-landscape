"""Open a GitHub pull request from a set of file changes.

The server never writes to disk (Render's filesystem is ephemeral and the data
is read once at startup). Instead a submission becomes a PR against ``main``,
which runs the existing ``validate.yml`` CI and, once a maintainer merges it,
triggers ``deploy.yml`` to rebuild the site. The maintainer's merge IS the
moderation step.

When ``GH_TOKEN`` is not configured the whole flow still works for preview:
``GitHubConfig.configured`` is False and the router shows the proposed YAML diff
instead of opening a PR (mirrors the ``use_case_system`` "configured: false"
pattern elsewhere in the app).
"""

import base64
import os
from dataclasses import dataclass

import httpx

API_ROOT = "https://api.github.com"
# Submissions go to THIS fork, never to the upstream parent. cldeluna/... is a
# fork of steinzi/...; because we POST to cldeluna and set both base and head to
# branches inside cldeluna, the PR is intra-fork and cannot land on upstream.
DEFAULT_REPO = "cldeluna/network-automation-landscape"
DEFAULT_BASE = "main"
# Hard guard: refuse to ever open a PR against the upstream parent, even if
# GH_REPO is misconfigured. Override only with an explicit env opt-in.
UPSTREAM_REPO = "steinzi/network-automation-landscape"


@dataclass
class GitHubConfig:
    token: str | None
    repo: str
    base_branch: str

    @classmethod
    def from_env(cls) -> "GitHubConfig":
        return cls(
            token=os.environ.get("GH_TOKEN"),
            repo=os.environ.get("GH_REPO", DEFAULT_REPO),
            base_branch=os.environ.get("GH_BASE_BRANCH", DEFAULT_BASE),
        )

    @property
    def configured(self) -> bool:
        return bool(self.token)


class GitHubError(RuntimeError):
    pass


def _headers(cfg: GitHubConfig) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {cfg.token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _request(client: httpx.Client, cfg: GitHubConfig, method: str, path: str, **kw):
    resp = client.request(method, f"{API_ROOT}{path}", headers=_headers(cfg), **kw)
    if resp.status_code >= 300:
        raise GitHubError(
            f"GitHub {method} {path} -> {resp.status_code}: {resp.text[:300]}"
        )
    return resp.json()


def open_pr(
    cfg: GitHubConfig,
    *,
    branch: str,
    title: str,
    body: str,
    text_files: dict[str, str],
    binary_files: dict[str, bytes] | None = None,
) -> dict:
    """Create ``branch`` off the base, commit the given files, and open a PR.

    Returns the GitHub PR object (includes ``html_url`` and ``number``).
    """
    if not cfg.configured:
        raise GitHubError("GH_TOKEN is not configured; cannot open a PR.")
    if cfg.repo == UPSTREAM_REPO and not os.environ.get("ALLOW_UPSTREAM_PR"):
        raise GitHubError(
            f"Refusing to open a PR against the upstream repo {cfg.repo!r}. "
            "Submissions belong in the fork. Set ALLOW_UPSTREAM_PR=1 to override."
        )

    binary_files = binary_files or {}
    with httpx.Client(timeout=30) as client:
        repo = cfg.repo
        # 1. base ref -> base commit -> base tree
        ref = _request(
            client, cfg, "GET", f"/repos/{repo}/git/ref/heads/{cfg.base_branch}"
        )
        base_sha = ref["object"]["sha"]
        base_commit = _request(
            client, cfg, "GET", f"/repos/{repo}/git/commits/{base_sha}"
        )
        base_tree = base_commit["tree"]["sha"]

        # 2. blobs
        tree_entries = []
        for path, content in text_files.items():
            blob = _request(
                client,
                cfg,
                "POST",
                f"/repos/{repo}/git/blobs",
                json={"content": content, "encoding": "utf-8"},
            )
            tree_entries.append(
                {"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]}
            )
        for path, raw in binary_files.items():
            blob = _request(
                client,
                cfg,
                "POST",
                f"/repos/{repo}/git/blobs",
                json={
                    "content": base64.b64encode(raw).decode("ascii"),
                    "encoding": "base64",
                },
            )
            tree_entries.append(
                {"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]}
            )

        # 3. tree -> commit -> branch ref -> PR
        tree = _request(
            client,
            cfg,
            "POST",
            f"/repos/{repo}/git/trees",
            json={"base_tree": base_tree, "tree": tree_entries},
        )
        commit = _request(
            client,
            cfg,
            "POST",
            f"/repos/{repo}/git/commits",
            json={"message": title, "tree": tree["sha"], "parents": [base_sha]},
        )
        _request(
            client,
            cfg,
            "POST",
            f"/repos/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": commit["sha"]},
        )
        return _request(
            client,
            cfg,
            "POST",
            f"/repos/{repo}/pulls",
            json={
                "title": title,
                "head": branch,
                "base": cfg.base_branch,
                "body": body,
            },
        )
