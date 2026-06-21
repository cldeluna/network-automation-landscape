"""Admin layer: a self-service web form that turns tool submissions into
GitHub pull requests against ``data.yml`` (+ the sidecar), instead of asking
contributors to hand-edit a 2,300-line YAML file.

Nothing here writes to disk on the server — the write target is a PR. See
``api/admin/github_pr.py``.
"""
