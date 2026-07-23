from pathlib import Path


def test_monitor_status_workflow_deploys_the_status_it_publishes() -> None:
    workflow = Path(".github/workflows/publish-monitor-status.yml").read_text(
        encoding="utf-8"
    )

    assert "pages: write" in workflow
    assert "id-token: write" in workflow
    assert "gradwindow build-site" in workflow
    assert "actions/upload-pages-artifact@v5" in workflow
    assert "actions/deploy-pages@v5" in workflow
    assert "gh workflow run tests.yml" not in workflow
