from typing import Any

from mcp.server.fastmcp import FastMCP

from directory.mcp.api import build_mcp_server
from directory.resolve import Directory
from directory.store.api import InMemoryDirectoryStore


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


def _server() -> FastMCP:
    return build_mcp_server(directory=Directory(store=InMemoryDirectoryStore(), clock=_Clock()))


async def _call(server: FastMCP, name: str, args: dict[str, Any]) -> Any:
    _, result = await server.call_tool(name, args)
    return result


async def test_surface_is_a_small_set_of_verbs() -> None:
    names = {t.name for t in await _server().list_tools()}

    assert {
        "whois",
        "who_to_query",
        "find",
        "remember_person",
        "remember_project",
        "relate",
        "record_reference",
        "merge",
        "set_self",
        "vocab",
        "tag",
        "find_by_tag",
        "remember_team",
        "remember_org",
    } <= names


async def test_check_what_my_boss_said_end_to_end() -> None:
    server = _server()
    # A realistic self-name (not literally "Me") so "relate subject=me" can't pass by accident.
    await _call(server, "set_self", {"name": "Ada Lovelace", "email": "me@example.com"})
    await _call(
        server,
        "remember_person",
        {
            "name": "Grace Hopper",
            "email": "grace@example.com",
            "links": [{"system": "slack", "ref_type": "user", "value": "U777"}],
        },
    )
    await _call(server, "relate", {"subject": "me", "relation": "reports_to", "target": "grace@example.com"})

    boss = await _call(server, "whois", {"query": "my boss"})

    assert boss["name"] == "Grace Hopper"
    assert boss["contacts"]["slack"][0]["value"] == "U777"


async def test_who_to_query_returns_coordinates_by_system() -> None:
    server = _server()
    await _call(
        server,
        "remember_person",
        {
            "name": "Ada",
            "email": "ada@example.com",
            "links": [{"system": "jira", "ref_type": "user", "value": "acct-9"}],
        },
    )

    coords = await _call(server, "who_to_query", {"query": "ada@example.com"})

    assert coords["jira"][0]["value"] == "acct-9"
    assert coords["email"][0]["value"] == "ada@example.com"


async def test_remember_person_collapses_on_email() -> None:
    server = _server()
    first = await _call(server, "remember_person", {"name": "Ada", "email": "ada@example.com"})
    again = await _call(server, "remember_person", {"name": "A. Lovelace", "email": "ada@example.com"})

    assert first["id"] == again["id"]


async def test_record_reference_creates_artifact_and_unknown_people() -> None:
    server = _server()
    await _call(
        server,
        "record_reference",
        {
            "kind": "slack_thread",
            "system": "slack",
            "ref_type": "thread",
            "value": "C1/1700000000.0001",
            "title": "incident postmortem",
            "people": ["new.person@example.com"],
            "role": "authored",
        },
    )

    found = await _call(server, "find", {"query": "postmortem"})

    assert found["items"][0]["kind"] == "slack_thread"


async def test_vocab_tool_returns_suggested_and_in_use() -> None:
    server = _server()
    await _call(server, "remember_person", {"name": "Ada", "email": "ada@example.com"})

    vocabulary = await _call(server, "vocab", {})

    assert "reports_to" in vocabulary["suggested"]["relation"]
    assert "email" in vocabulary["in_use"]["system"]


async def test_relate_through_tool_normalizes_relation() -> None:
    server = _server()
    await _call(server, "set_self", {"name": "Me", "email": "me@example.com"})
    await _call(server, "remember_person", {"name": "Grace", "email": "grace@example.com"})
    await _call(server, "relate", {"subject": "me", "relation": "Reports To", "target": "grace@example.com"})

    boss = await _call(server, "whois", {"query": "my boss"})

    assert boss["name"] == "Grace"
    assert boss["relations"][0]["type"] == "reports_to"


async def test_tag_and_find_by_tag_tools() -> None:
    server = _server()
    await _call(server, "remember_person", {"name": "Grace", "email": "grace@example.com"})
    await _call(server, "tag", {"subject": "grace@example.com", "label": "leadership"})

    found = await _call(server, "find_by_tag", {"label": "leadership"})

    assert found["items"][0]["name"] == "Grace"


async def test_whois_surfaces_usage_stats() -> None:
    server = _server()
    await _call(server, "remember_person", {"name": "Ada", "email": "ada@example.com"})
    await _call(server, "whois", {"query": "ada@example.com"})
    again = await _call(server, "whois", {"query": "ada@example.com"})

    assert again["hits"] == 2
    assert again["last_seen"] is not None


async def test_alex_from_widget_project_disambiguates_through_tools() -> None:
    server = _server()
    await _call(server, "remember_project", {"name": "Widget Connector 2024"})
    await _call(server, "remember_project", {"name": "Widget Connector Project"})
    await _call(server, "remember_person", {"name": "Alex Old", "email": "alex.old@example.com"})
    await _call(server, "remember_person", {"name": "Alex New", "email": "alex.new@example.com"})
    await _call(server, "relate", {"subject": "alex.old@example.com", "relation": "works_on", "target": "Widget Connector 2024"})
    await _call(server, "relate", {"subject": "alex.new@example.com", "relation": "works_on", "target": "Widget Connector Project"})
    await _call(server, "whois", {"query": "Widget Connector Project"})
    await _call(server, "whois", {"query": "Widget Connector Project"})

    resolved = await _call(server, "whois", {"query": "Alex from the widget project"})

    assert resolved["name"] == "Alex New"


async def test_whois_flags_ambiguous_and_returns_both() -> None:
    server = _server()
    await _call(server, "remember_project", {"name": "Widget Connector legacy"})
    await _call(server, "remember_project", {"name": "Widget Connector current"})
    await _call(server, "remember_person", {"name": "Alex Legacy", "email": "ml@example.com"})
    await _call(server, "remember_person", {"name": "Alex Current", "email": "mc@example.com"})
    await _call(server, "relate", {"subject": "ml@example.com", "relation": "works_on", "target": "Widget Connector legacy"})
    await _call(server, "relate", {"subject": "mc@example.com", "relation": "works_on", "target": "Widget Connector current"})

    result = await _call(server, "whois", {"query": "Alex from the widget project"})

    assert result["ambiguous"] is True
    names = {result["name"], *(a["name"] for a in result["alternatives"])}
    assert names == {"Alex Legacy", "Alex Current"}


async def test_confident_match_is_not_flagged_ambiguous() -> None:
    server = _server()
    await _call(server, "remember_person", {"name": "Solo Person", "email": "solo@example.com"})

    result = await _call(server, "whois", {"query": "solo@example.com"})

    assert result["ambiguous"] is False
    assert result["alternatives"] == []


async def test_remember_team_and_member_of_through_tools() -> None:
    server = _server()
    await _call(server, "remember_team", {"name": "Helpdesk", "notes": "AI helpdesk team"})
    await _call(server, "remember_person", {"name": "Alan Turing", "email": "aa@example.com"})
    await _call(server, "relate", {"subject": "aa@example.com", "relation": "member_of", "target": "Helpdesk"})

    team = await _call(server, "whois", {"query": "Helpdesk"})

    assert team["kind"] == "team"
    assert any(r["name"] == "Alan Turing" for r in team["relations"])


async def test_remember_person_links_attach_arbitrary_systems() -> None:
    server = _server()
    await _call(
        server,
        "remember_person",
        {
            "name": "Octo Cat",
            "email": "octo@example.com",
            "links": [{"system": "github", "ref_type": "user", "value": "octocat"}],
        },
    )

    coords = await _call(server, "who_to_query", {"query": "octo@example.com"})

    assert coords["github"][0]["value"] == "octocat"


async def test_remember_org_creates_org_entity() -> None:
    server = _server()
    result = await _call(server, "remember_org", {"name": "Globex"})

    assert result["kind"] == "org"
    assert result["name"] == "Globex"


async def test_unresolvable_whois_returns_empty() -> None:
    assert await _call(_server(), "whois", {"query": "nobody"}) == {}
