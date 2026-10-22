"""Gate «independent-review»: parser del verdetto (scripts/review_gate.py)."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import REPO_ROOT

pytestmark = pytest.mark.guard

GATE = REPO_ROOT / "scripts" / "review_gate.py"
HEAD = "65be9f1a596f19921e33f11b115d75559ff667d8"
OLD = "7d5b20e54292b8c152a4d08a2b60bc17da1b668d"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("review_gate", GATE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def c(body: str, created: str = "2026-10-22T14:00:00Z", cid: int = 1) -> dict[str, Any]:
    return {
        "id": cid,
        "body": body,
        "created_at": created,
        "updated_at": created,
        "author_association": "OWNER",
    }


def review(verdict: str = "APPROVE", sha: str = HEAD, extra: str = "") -> str:
    return f"## Independent review\n\nREVIEW-VERDICT: {verdict}\nREVIEWED-SHA: {sha}\n{extra}"


def ev(comments: list[dict[str, Any]], head: str = HEAD) -> tuple[bool, str]:
    result: tuple[bool, str] = _load().evaluate(comments, head)
    return result


def test_approve_on_head_passes() -> None:
    assert ev([c(review())]) == (True, "APPROVED")


@pytest.mark.parametrize(
    "title",
    [
        "Independent review",
        "# Independent review",
        "### Independent review — MCP-01b",
        "**Independent review**",
    ],
)
def test_title_forms(title: str) -> None:
    body = f"{title}\nREVIEW-VERDICT: APPROVE\nREVIEWED-SHA: {HEAD}\n"
    assert ev([c(body)])[0] is True


def test_no_comment_fails() -> None:
    assert ev([]) == (False, "NO_REVIEW_FOR_HEAD")


def test_untitled_comment_ignored() -> None:
    body = f"LGTM\nREVIEW-VERDICT: APPROVE\nREVIEWED-SHA: {HEAD}\n"
    assert ev([c(body)]) == (False, "NO_REVIEW_FOR_HEAD")


def test_title_must_be_first_line() -> None:
    body = "note\n" + review()
    assert ev([c(body)]) == (False, "NO_REVIEW_FOR_HEAD")


def test_old_sha_fails_new_push_invalidates() -> None:
    assert ev([c(review(sha=OLD))]) == (False, "NO_REVIEW_FOR_HEAD")


def test_short_sha_rejected() -> None:
    assert ev([c(review(sha=HEAD[:7]))]) == (False, "MALFORMED_VERDICT")


def test_blocking_line_fails() -> None:
    body = review(extra="BLOCKING: race in journal recover\n")
    assert ev([c(body)]) == (False, "BLOCKING_FINDINGS:1")


def test_blocking_word_anywhere_fails_closed() -> None:
    body = review(extra="No BLOCKING: items found.\nNON-BLOCKING: nit\n")
    assert ev([c(body)]) == (False, "BLOCKING_FINDINGS:1")


def test_indented_blocking_counts() -> None:
    body = review(extra="  BLOCKING: x\n- BLOCKING: y\n")
    assert ev([c(body)]) == (False, "BLOCKING_FINDINGS:2")


@pytest.mark.parametrize("verdict", ["REQUEST_CHANGES", "COMMENT", "approve", "APPROVED", ""])
def test_non_approve_verdict_fails(verdict: str) -> None:
    assert ev([c(review(verdict=verdict))])[0] is False


def test_duplicate_verdict_lines_fail() -> None:
    body = review(extra="REVIEW-VERDICT: REQUEST_CHANGES\n")
    assert ev([c(body)]) == (False, "MALFORMED_VERDICT")


def test_duplicate_sha_lines_fail() -> None:
    body = review(extra=f"REVIEWED-SHA: {OLD}\n")
    assert ev([c(body)]) == (False, "MALFORMED_VERDICT")


def test_missing_verdict_fails() -> None:
    body = f"Independent review\nREVIEWED-SHA: {HEAD}\n"
    assert ev([c(body)]) == (False, "MALFORMED_VERDICT")


def test_latest_review_for_head_wins() -> None:
    ok = c(review(), "2026-10-22T14:00:00Z", 1)
    bad = c(review("REQUEST_CHANGES"), "2026-10-22T15:00:00Z", 2)
    assert ev([ok, bad])[0] is False
    assert ev([bad, c(review(), "2026-10-22T16:00:00Z", 3)])[0] is True


def test_order_by_time_not_list_position() -> None:
    bad = c(review("REQUEST_CHANGES"), "2026-10-22T15:00:00Z", 2)
    ok = c(review(), "2026-10-22T14:00:00Z", 1)
    assert ev([bad, ok])[0] is False


def test_edited_comment_uses_current_body() -> None:
    edited = c(review(extra="BLOCKING: found later\n"))
    edited["updated_at"] = "2026-10-22T18:00:00Z"
    assert ev([edited])[0] is False


def test_crlf_and_spaces_tolerated() -> None:
    body = f"Independent review\r\nREVIEW-VERDICT:   APPROVE  \r\nREVIEWED-SHA: {HEAD.upper()}\r\n"
    assert ev([c(body)])[0] is True


def test_head_sha_must_be_full() -> None:
    with pytest.raises(ValueError):
        ev([c(review())], head="abc")


def test_garbage_comments_ignored() -> None:
    assert ev([{"id": 1}, {"body": None}, c(review())])[0] is True


def test_cli(tmp_path: Path) -> None:
    f = tmp_path / "comments.json"
    f.write_text(json.dumps([c(review())]))
    ok = subprocess.run(
        [sys.executable, str(GATE), "--comments", str(f), "--head-sha", HEAD],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert ok.returncode == 0 and "APPROVED" in ok.stdout
    bad = subprocess.run(
        [sys.executable, str(GATE), "--comments", str(f), "--head-sha", OLD],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert bad.returncode == 1 and "NO_REVIEW_FOR_HEAD" in bad.stdout


def test_cli_accepts_paginated_arrays(tmp_path: Path) -> None:
    """`gh api --paginate --slurp` restituisce una lista di pagine."""
    f = tmp_path / "comments.json"
    f.write_text(json.dumps([[c("x", cid=1)], [c(review(), cid=2)]]))
    ok = subprocess.run(
        [sys.executable, str(GATE), "--comments", str(f), "--head-sha", HEAD],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert ok.returncode == 0


def test_workflow_wiring() -> None:
    wf = (REPO_ROOT / ".github" / "workflows" / "independent-review.yml").read_text()
    for needle in (
        "pull_request_target:",
        "issue_comment:",
        "pull_request_review:",
        "statuses: write",
        "independent-review",
        "scripts/review_gate.py",
    ):
        assert needle in wf


@pytest.mark.parametrize("assoc", ["NONE", "CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", None])
def test_untrusted_authors_ignored(assoc: str | None) -> None:
    """Repo pubblico: un commento di chi non ha accesso in scrittura non conta."""
    comment = c(review())
    comment["author_association"] = assoc
    assert ev([comment]) == (False, "NO_REVIEW_FOR_HEAD")


@pytest.mark.parametrize("assoc", ["OWNER", "MEMBER", "COLLABORATOR"])
def test_trusted_authors_counted(assoc: str) -> None:
    comment = c(review())
    comment["author_association"] = assoc
    assert ev([comment])[0] is True


# --- review 101ae4d: B1, B2, N9 -------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "BLOCKING: x",
        "Blocking: x",
        "blocking: x",
        "- **BLOCKING**: x",
        "**BLOCKING:** x",
        "* BLOCKING: x",
        "+ BLOCKING: x",
        "1. BLOCKING: x",
        "12) BLOCKING: x",
        "> BLOCKING: x",
        "### BLOCKING: x",
        "- [BLOCKING]: x",
        "`BLOCKING`: x",
        "__BLOCKING__ : x",
        "\tBLOCKING : x",
    ],
)
def test_blocking_forms_detected(line: str) -> None:
    assert ev([c(review(extra=line + "\n"))]) == (False, "BLOCKING_FINDINGS:1")


@pytest.mark.parametrize(
    "line",
    [
        "NON-BLOCKING: nit",
        "- **NON-BLOCKING**: nit",
        "1. Non-blocking: nit",
    ],
)
def test_non_blocking_forms_ignored(line: str) -> None:
    assert ev([c(review(extra=line + "\n"))])[0] is True


def test_newer_review_without_sha_invalidates_older_approve() -> None:
    ok = c(review(), "2026-10-22T14:00:00Z", 1)
    newer = c("Independent review\nREVIEW-VERDICT: APPROVE\n", "2026-10-22T15:00:00Z", 2)
    assert ev([ok, newer]) == (False, "MALFORMED_VERDICT")


def test_newer_review_with_misspelled_sha_invalidates() -> None:
    ok = c(review(), "2026-10-22T14:00:00Z", 1)
    newer = c(review(sha="not-a-sha"), "2026-10-22T15:00:00Z", 2)
    assert ev([ok, newer]) == (False, "MALFORMED_VERDICT")


def test_newer_review_for_other_sha_invalidates() -> None:
    ok = c(review(), "2026-10-22T14:00:00Z", 1)
    newer = c(review(sha=OLD), "2026-10-22T15:00:00Z", 2)
    assert ev([ok, newer]) == (False, "NO_REVIEW_FOR_HEAD")


def test_workflow_never_runs_pr_code() -> None:
    wf = (REPO_ROOT / ".github" / "workflows" / "independent-review.yml").read_text()
    code = "\n".join(line for line in wf.splitlines() if not line.lstrip().startswith("#"))
    assert "pull_request_target:" in code
    assert re.search(r"^\s{2}pull_request:", code, re.M) is None
    assert "path: pr" not in code and "pr/scripts" not in code
    assert "bootstrap" not in code.lower()
    assert "head.ref" not in code and "head.sha }}" not in code
    assert code.count("uses: actions/checkout@") == 1
    assert "ref: ${{ github.event.repository.default_branch }}" in code
    assert "persist-credentials: false" in code


# --- review 4a5b1c7: G1, G3 ------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "B1 BLOCKING: x",
        "Finding (BLOCKING): x",
        "| BLOCKING: x |",
        "* [ ] BLOCKING: x",
        "BLOCKING - x",
        "BLOCKING x",
        "BLOCKING findings:",
        "## BLOCKING",
        "<b>BLOCKING</b>: x",
        "<span>BLOCK</span>ING: x",
        "\u200bBLOCKING: x",
        "BLOC\u200bKING: x",
        "\ufeffBLOCKING: x",
        "\u00a0BLOCKING: x",
        "\uff22\uff2c\uff2f\uff23\uff2b\uff29\uff2e\uff27: x",
        "BLOCKING\uff1a x",
        "No blocking issues found.",
        "blocking",
    ],
)
def test_g1_blocking_word_anywhere(line: str) -> None:
    assert ev([c(review(extra=line + "\n"))]) == (False, "BLOCKING_FINDINGS:1")


@pytest.mark.parametrize(
    "line",
    [
        "NON-BLOCKING: nit",
        "non-blocking",
        "NON BLOCKING: nit",
        "NON_BLOCKING: nit",
        "NONBLOCKING: x",
        "NON\u2011BLOCKING: nit",
        "nonblocking work",
        "unblocking the queue",
    ],
)
def test_g1_non_blocking_variants_allowed(line: str) -> None:
    assert ev([c(review(extra=line + "\n"))])[0] is True


def test_g1_mixed_line_still_fails() -> None:
    body = review(extra="NON-BLOCKING: a, BLOCKING: b\n")
    assert ev([c(body)]) == (False, "BLOCKING_FINDINGS:1")


def test_g1_zero_width_in_verdict_normalised() -> None:
    body = f"Independent review\nREVIEW-VERDICT: APP\u200bROVE\nREVIEWED-SHA: {HEAD}\n"
    assert ev([c(body)])[0] is True


@pytest.mark.parametrize(
    "body",
    [
        f"Independent review\n**REVIEW-VERDICT:** APPROVE\nREVIEWED-SHA: {HEAD}\n",
        f"Independent review\nREVIEW-VERDICT: **APPROVE**\nREVIEWED-SHA: {HEAD}\n",
        f"Independent review\nREVIEW-VERDICT: APPROVE\n**REVIEWED-SHA:** {HEAD}\n",
        f"Independent review\n`REVIEW-VERDICT: APPROVE`\nREVIEWED-SHA: {HEAD}\n",
    ],
)
def test_g3_decorated_verdict_lines_fail_closed(body: str) -> None:
    assert ev([c(body)])[0] is False
