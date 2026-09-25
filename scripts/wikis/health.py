"""Shared partial-run reporting: keep acquired data, fail the run visibly."""

def report_issue(session, message: str) -> None:
    issues = getattr(session, "_ingestion_issues", None)
    if issues is None:
        issues = []
        session._ingestion_issues = issues
    issues.append(message)
    print(f"[WIKI-ISSUE] {message}")


def install_response_guard(session) -> None:
    """A WAF page with HTTP 200 must not advance a successful checkpoint."""
    if not hasattr(session, 'hooks') or getattr(session, '_ingestion_guard', False):
        return

    def guard(response, *args, **kwargs):
        content_type = response.headers.get('Content-Type', '').lower()
        if 'html' not in content_type and 'queue-it.net' not in response.url:
            return response
        try:
            from scripts.manga_watch import detect_challenge
        except ImportError:
            from manga_watch import detect_challenge
        challenge = detect_challenge(response.text, final_url=response.url)
        if challenge:
            import requests
            message = f'challenge={challenge}: {response.url}'
            report_issue(session, message)
            raise requests.HTTPError(message, response=response)
        return response

    session.hooks.setdefault('response', []).append(guard)
    session._ingestion_guard = True
