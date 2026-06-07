import pytest

from directory.models import Link
from directory.resolve import Directory
from directory.store.api import DirectoryStore, InMemoryDirectoryStore
from directory.store.internal.sqlalchemy_store import SqlAlchemyDirectoryStore
from tests.conftest import sql_engine


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


@pytest.fixture(params=["memory", "sql"])
def directory(request: pytest.FixtureRequest) -> Directory:
    store: DirectoryStore = (
        InMemoryDirectoryStore()
        if request.param == "memory"
        else SqlAlchemyDirectoryStore(engine=sql_engine())
    )
    return Directory(store=store, clock=_Clock())


async def test_ensure_person_collapses_on_shared_email(directory: Directory) -> None:
    first = await directory.ensure_person(display_name="Ada Lovelace", email="ada@example.com")
    again = await directory.ensure_person(display_name="A. Lovelace", email="ADA@example.com")

    assert again.id == first.id


async def test_resolve_by_email_and_name(directory: Directory) -> None:
    person = await directory.ensure_person(display_name="Ada Lovelace", email="ada@example.com")

    assert (await directory.resolve(query="ada@example.com")) == person
    assert (await directory.resolve(query="lovelace")) == person
    assert (await directory.resolve(query="ghost")) is None


async def test_me_resolves_to_self_regardless_of_name(directory: Directory) -> None:
    me = await directory.set_self(display_name="Ada Lovelace", email="seb@example.com")

    assert (await directory.resolve(query="me")) == me
    assert (await directory.resolve(query="myself")) == me


async def test_relate_with_me_links_to_self(directory: Directory) -> None:
    me = await directory.set_self(display_name="Ada Lovelace", email="seb@example.com")
    await directory.ensure_person(display_name="Grace", email="grace@example.com")
    await directory.relate(subject="me", relation="reports_to", target="grace@example.com")

    edges = await directory.store.edges_from(entity_id=me.id, type="reports_to")
    assert len(edges) == 1
    dossier = await directory.whois(query="my boss")
    assert dossier is not None and dossier.entity.display_name == "Grace"


async def test_whois_my_boss_walks_reports_to_from_self(directory: Directory) -> None:
    await directory.set_self(display_name="Me", email="me@example.com")
    boss = await directory.ensure_person(display_name="Grace Hopper", email="grace@example.com")
    await directory.relate(subject="me@example.com", relation="reports_to", target="grace@example.com")

    dossier = await directory.whois(query="my boss")

    assert dossier is not None
    assert dossier.entity == boss


async def test_whois_my_reports_walks_incoming_edges(directory: Directory) -> None:
    me = await directory.set_self(display_name="Me", email="me@example.com")
    await directory.ensure_person(display_name="Junior", email="jr@example.com")
    await directory.relate(subject="jr@example.com", relation="reports_to", target="me@example.com")

    report = await directory.resolve(query="my reports")

    assert report is not None and report.display_name == "Junior"
    assert me.is_self


async def test_contacts_group_anchors_by_system(directory: Directory) -> None:
    person = await directory.ensure_person(display_name="Ada", email="ada@example.com")
    await directory.link(subject="ada@example.com", system="slack", ref_type="user", value="U1")
    await directory.link(
        subject="ada@example.com", system="jira", ref_type="user", value="acct-9"
    )

    contacts = await directory.contacts(entity_id=person.id)

    assert set(contacts) == {"email", "slack", "jira"}
    assert contacts["slack"][0].value == "U1"


async def test_remember_project_holds_many_anchors(directory: Directory) -> None:
    project = await directory.remember_project(
        name="Checkout Revamp",
        links=[
            Link(system="jira", ref_type="project_key", value="VX"),
            Link(system="jira", ref_type="project_key", value="PAY"),
            Link(system="slack", ref_type="channel", value="#checkout"),
            Link(system="slack", ref_type="channel", value="#payments-war-room"),
            Link(system="gitlab", ref_type="repo", value="org/checkout-web"),
            Link(system="gitlab", ref_type="repo", value="org/checkout-api"),
        ],
    )

    contacts = await directory.contacts(entity_id=project.id)

    assert len(contacts["jira"]) == 2
    assert len(contacts["slack"]) == 2
    assert len(contacts["gitlab"]) == 2


async def test_record_reference_links_people_to_artifact(directory: Directory) -> None:
    await directory.ensure_person(display_name="Ada", email="ada@example.com")

    artifact = await directory.record_reference(
        kind="slack_thread",
        system="slack",
        ref_type="thread",
        value="C1/1700000000.0001",
        title="incident postmortem",
        people=["ada@example.com", "Brand New Person"],
        role="authored",
    )

    dossier = await directory.dossier(entity_id=artifact.id)
    assert dossier is not None
    authors = [r.other.display_name for r in dossier.relations if r.direction == "in"]
    assert {"Ada", "Brand New Person"} == set(authors)


async def test_name_match_outranks_a_notes_mention(directory: Directory) -> None:
    project = await directory.remember_project(name="Acme")
    mentioner = await directory.ensure_person(display_name="Mira", email="m@example.com")
    await directory.store.update_entity(entity_id=mentioner.id, notes="Acme Working Group")

    resolution = await directory.resolve_full(query="Acme")

    assert resolution.entity is not None and resolution.entity.id == project.id
    assert all(alt.id != mentioner.id for alt in resolution.alternatives)


async def test_relate_is_idempotent(directory: Directory) -> None:
    await directory.set_self(display_name="Ada", email="seb@example.com")
    await directory.ensure_person(display_name="Grace", email="grace@example.com")

    await directory.relate(subject="me", relation="reports_to", target="grace@example.com")
    await directory.relate(subject="me", relation="reports_to", target="grace@example.com")

    me = await directory.store.self_entity()
    assert me is not None
    edges = await directory.store.edges_from(entity_id=me.id, type="reports_to")
    assert len(edges) == 1


async def test_remember_person_is_idempotent_on_anchors(directory: Directory) -> None:
    coords = [
        Link(system="slack", ref_type="user", value="U1"),
        Link(system="jira", ref_type="user", value="J1"),
    ]
    await directory.remember_person(name="Ada", email="ada@example.com", links=coords)
    await directory.remember_person(name="Ada Lovelace", email="ada@example.com", links=coords)

    person = await directory.resolve(query="ada@example.com")
    assert person is not None
    assert len(await directory.store.anchors_for(entity_id=person.id)) == 3


async def test_link_is_idempotent(directory: Directory) -> None:
    await directory.ensure_person(display_name="Ada", email="ada@example.com")
    await directory.link(subject="ada@example.com", system="slack", ref_type="user", value="U9")
    await directory.link(subject="ada@example.com", system="slack", ref_type="user", value="U9")

    person = await directory.resolve(query="ada@example.com")
    assert person is not None
    assert len(await directory.store.anchors_for(entity_id=person.id, system="slack")) == 1


async def test_remember_group_creates_and_dedupes_by_name(directory: Directory) -> None:
    first = await directory.remember_group(kind="team", name="Helpdesk")
    again = await directory.remember_group(kind="team", name="Helpdesk")
    other = await directory.remember_group(kind="org", name="Globex")

    assert first.kind == "team"
    assert again.id == first.id
    assert other.kind == "org" and other.id != first.id


async def test_remember_group_supports_member_of_edges(directory: Directory) -> None:
    await directory.remember_group(kind="team", name="QA")
    await directory.ensure_person(display_name="Pierre", email="pierre@example.com")
    await directory.relate(subject="pierre@example.com", relation="member_of", target="QA")

    dossier = await directory.whois(query="Pierre")

    assert dossier is not None
    assert any(r.edge.type == "member_of" and r.other.display_name == "QA" for r in dossier.relations)


async def test_relate_normalizes_relation_type(directory: Directory) -> None:
    await directory.set_self(display_name="Me", email="me@example.com")
    await directory.ensure_person(display_name="Grace", email="grace@example.com")
    await directory.relate(subject="me", relation="Reports-To", target="grace@example.com")

    dossier = await directory.whois(query="my boss")

    assert dossier is not None and dossier.entity.display_name == "Grace"


async def test_record_reference_is_idempotent_on_coordinate(directory: Directory) -> None:
    first = await directory.record_reference(
        kind="slack_thread",
        system="slack",
        ref_type="thread",
        value="C1/1700000000.0001",
        title="incident",
        occurred_at="2026-06-05T10:00:00Z",
        people=["ada@example.com"],
        role="authored",
    )
    second = await directory.record_reference(
        kind="slack_thread",
        system="slack",
        ref_type="thread",
        value="C1/1700000000.0001",
        title="incident",
        people=["ada@example.com"],
        role="authored",
    )

    assert first.id == second.id
    dossier = await directory.dossier(entity_id=first.id)
    assert dossier is not None
    assert len([r for r in dossier.relations if r.direction == "in"]) == 1
    assert any(o.key == "occurred_at" for o in dossier.observations)


async def test_tag_and_find_by_tag(directory: Directory) -> None:
    await directory.ensure_person(display_name="Grace", email="grace@example.com")
    await directory.ensure_person(display_name="Ada", email="ada@example.com")
    await directory.tag(subject="grace@example.com", label="Leadership")
    await directory.tag(subject="ada@example.com", label="leadership")

    tagged = await directory.tagged(label="leadership")

    assert {e.display_name for e in tagged} == {"Grace", "Ada"}


async def test_vocabulary_merges_suggested_and_in_use(directory: Directory) -> None:
    await directory.remember_project(
        name="Checkout", links=[Link(system="jira", ref_type="project_key", value="VX")]
    )

    vocabulary = await directory.vocabulary()

    assert "reports_to" in vocabulary["suggested"]["relation"]
    assert "jira" in vocabulary["in_use"]["system"]


async def test_alex_from_the_widget_project_picks_the_recent_one(directory: Directory) -> None:
    old_widget = await directory.remember_project(name="Widget Connector 2024")
    new_widget = await directory.remember_project(name="Widget Connector Project")
    old_alex = await directory.ensure_person(display_name="Alex Old", email="alex.old@example.com")
    new_alex = await directory.ensure_person(display_name="Alex New", email="alex.new@example.com")
    await directory.store.add_edge(from_id=old_alex.id, to_id=old_widget.id, type="works_on")
    await directory.store.add_edge(from_id=new_alex.id, to_id=new_widget.id, type="works_on")

    # The current Widget project is the one we keep touching.
    await directory.whois(query="Widget Connector Project")
    await directory.whois(query="Widget Connector Project")

    resolved = await directory.resolve(query="Alex from the widget project")

    assert resolved is not None and resolved.id == new_alex.id


async def test_ambiguous_name_prefers_most_recently_seen(directory: Directory) -> None:
    await directory.ensure_person(display_name="Chris Stale", email="chris.stale@example.com")
    fresh = await directory.ensure_person(display_name="Chris Fresh", email="chris.fresh@example.com")
    await directory.whois(query="chris.fresh@example.com")

    resolved = await directory.resolve(query="Chris")

    assert resolved is not None and resolved.id == fresh.id


async def test_lookups_accumulate_stats(directory: Directory) -> None:
    await directory.ensure_person(display_name="Ada", email="ada@example.com")
    await directory.whois(query="ada@example.com")
    dossier = await directory.whois(query="ada@example.com")

    assert dossier is not None
    assert dossier.stats.count == 2
    assert dossier.stats.last_at is not None


_DAY = 86400.0


class _FixedClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _fixed_directory(now: float) -> Directory:
    return Directory(store=InMemoryDirectoryStore(), clock=_FixedClock(now))


async def test_connection_outranks_activity_in_context() -> None:
    directory = _fixed_directory(1_000_000.0)
    widget = await directory.remember_project(name="Widget Connector")
    on_widget = await directory.ensure_person(display_name="Alex K", email="mk@example.com")
    loud_outsider = await directory.ensure_person(display_name="Alex Z", email="mz@example.com")
    await directory.store.add_edge(from_id=on_widget.id, to_id=widget.id, type="works_on")
    for at in range(50):
        await directory.store.record_interaction(
            entity_id=loud_outsider.id, kind="lookup", at=999_000.0 + at
        )

    resolution = await directory.resolve_full(query="Alex from the widget")

    # The loud outsider is touched far more, but is on no Widget project — connection wins, and
    # since only one candidate is connected the match is confident (no alternatives).
    assert resolution.entity is not None and resolution.entity.id == on_widget.id
    assert resolution.alternatives == []


async def test_two_connected_candidates_are_both_returned_for_the_consumer() -> None:
    now = 2_000_000.0
    directory = _fixed_directory(now)
    active = await directory.remember_project(name="Widget Active")
    barely = await directory.remember_project(name="Widget Barely")
    on_active = await directory.ensure_person(display_name="Alex A", email="a@example.com")
    on_barely = await directory.ensure_person(display_name="Alex B", email="b@example.com")
    await directory.store.add_edge(from_id=on_active.id, to_id=active.id, type="works_on")
    await directory.store.add_edge(from_id=on_barely.id, to_id=barely.id, type="works_on")
    # Active worked a lot 3 days ago; barely touched once 1 day ago. Similar enough that the
    # tool must NOT silently decide — it returns both and lets the consumer choose.
    for i in range(8):
        await directory.store.record_interaction(
            entity_id=active.id, kind="reference", at=now - 3 * _DAY - i * 100
        )
    await directory.store.record_interaction(entity_id=barely.id, kind="lookup", at=now - _DAY)

    resolution = await directory.resolve_full(query="Alex from the widget")

    assert resolution.entity is not None
    returned = {resolution.entity.id, *(a.id for a in resolution.alternatives)}
    assert returned == {on_active.id, on_barely.id}
    # Activity only orders the best-guess first; it does not drop the other.
    assert resolution.entity.id == on_active.id


async def test_whois_surfaces_alternatives_when_two_are_comparable() -> None:
    directory = _fixed_directory(1_000_000.0)
    sam_one = await directory.ensure_person(display_name="Sam Carter", email="sc@example.com")
    await directory.ensure_person(display_name="Sam Diaz", email="sd@example.com")

    dossier = await directory.whois(query="Sam")

    assert dossier is not None
    alt_ids = {e.id for e in dossier.alternatives}
    assert dossier.entity.id not in alt_ids
    assert len(alt_ids) >= 1
    assert sam_one.id in alt_ids or dossier.entity.id == sam_one.id


async def test_confident_match_has_no_alternatives() -> None:
    directory = _fixed_directory(1_000_000.0)
    await directory.ensure_person(display_name="Unique Person", email="u@example.com")

    dossier = await directory.whois(query="Unique")

    assert dossier is not None and dossier.alternatives == []


async def test_remember_person_attaches_links_for_any_system(directory: Directory) -> None:
    person = await directory.remember_person(
        name="Octo Cat",
        email="octo@example.com",
        links=[Link(system="github", ref_type="user", value="octocat")],
    )

    contacts = await directory.contacts(entity_id=person.id)
    assert contacts["github"][0].value == "octocat"


async def test_remember_project_attaches_links_for_any_system(directory: Directory) -> None:
    project = await directory.remember_project(
        name="Widget",
        links=[Link(system="notion", ref_type="page", value="abc123")],
    )

    contacts = await directory.contacts(entity_id=project.id)
    assert contacts["notion"][0].value == "abc123"


async def test_links_normalize_unknown_system_aliases(directory: Directory) -> None:
    person = await directory.remember_person(
        name="Octo",
        email="o@example.com",
        links=[Link(system="gh", ref_type="account", value="octocat")],
    )

    contacts = await directory.contacts(entity_id=person.id)
    assert contacts["github"][0].ref_type == "user"


async def test_merge_folds_duplicate_into_kept(directory: Directory) -> None:
    keep = await directory.ensure_person(display_name="Ada Lovelace", email="ada@example.com")
    dup = await directory.ensure_person(display_name="A. Lovelace", email="ada.l@gmail.com")
    await directory.link(subject="ada.l@gmail.com", system="slack", ref_type="user", value="U9")

    merged = await directory.merge(keep="ada@example.com", drop="ada.l@gmail.com")

    assert merged is True
    assert await directory.store.get_entity(entity_id=dup.id) is None
    contacts = await directory.contacts(entity_id=keep.id)
    assert contacts["slack"][0].value == "U9"
