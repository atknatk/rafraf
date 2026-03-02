"""Pydantic schemas for GitHub manager tool."""

from pydantic import BaseModel, ConfigDict


class GitHubIssue(BaseModel):
    """GitHub issue summary model."""

    model_config = ConfigDict(frozen=True)

    number: int
    title: str
    state: str
    body: str | None = None
    labels: list[str]
    assignees: list[str]
    created_at: str
    updated_at: str
    html_url: str


class GitHubPullRequest(BaseModel):
    """GitHub pull request summary model."""

    model_config = ConfigDict(frozen=True)

    number: int
    title: str
    state: str
    body: str | None = None
    head_branch: str
    base_branch: str
    mergeable: bool | None = None
    additions: int
    deletions: int
    changed_files: int
    html_url: str
    created_at: str
    updated_at: str


class GitHubCommit(BaseModel):
    """GitHub commit model."""

    model_config = ConfigDict(frozen=True)

    sha: str
    message: str
    author: str
    date: str


class GitHubBranch(BaseModel):
    """GitHub branch model."""

    model_config = ConfigDict(frozen=True)

    name: str
    sha: str
    protected: bool


class GitHubRepoInfo(BaseModel):
    """GitHub repository info model."""

    model_config = ConfigDict(frozen=True)

    full_name: str
    description: str | None = None
    default_branch: str
    open_issues_count: int
    forks_count: int
    stargazers_count: int
    language: str | None = None
    html_url: str


class WebhookResponse(BaseModel):
    """GitHub webhook processing response."""

    status: str
    message: str
