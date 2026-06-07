import pytest

from directory.store.api import DirectoryStore, InMemoryDirectoryStore
from directory.store.internal.sqlalchemy_store import SqlAlchemyDirectoryStore
from tests.conftest import sql_engine


@pytest.fixture(params=["memory", "sql"])
def store(request: pytest.FixtureRequest) -> DirectoryStore:
    if request.param == "memory":
        return InMemoryDirectoryStore()
    return SqlAlchemyDirectoryStore(engine=sql_engine())


async def test_entity_roundtrip_assigns_id(store: DirectoryStore) -> None:
    person = await store.add_entity(kind="person", display_name="Ada Lovelace")

    assert person.id != 0
    assert await store.get_entity(entity_id=person.id) == person


async def test_find_entities_is_fuzzy_and_kind_scoped(store: DirectoryStore) -> None:
    await store.add_entity(kind="person", display_name="Ada Lovelace")
    await store.add_entity(kind="project", display_name="Lovelace Migration")

    people = await store.find_entities(query="lovelace", kind="person")
    everything = await store.find_entities(query="lovelace")

    assert [e.display_name for e in people] == ["Ada Lovelace"]
    assert len(everything) == 2


async def test_update_entity_patches_named_fields(store: DirectoryStore) -> None:
    person = await store.add_entity(kind="person", display_name="Ada")

    updated = await store.update_entity(entity_id=person.id, notes="my boss", is_self=False)

    assert updated.notes == "my boss"
    assert updated.display_name == "Ada"
    assert (await store.find_entities(query="boss"))[0].id == person.id


async def test_self_entity_returns_the_marked_one(store: DirectoryStore) -> None:
    await store.add_entity(kind="person", display_name="Someone")
    me = await store.add_entity(kind="person", display_name="Me", is_self=True)

    assert await store.self_entity() == me


async def test_anchor_resolution_is_case_insensitive(store: DirectoryStore) -> None:
    person = await store.add_entity(kind="person", display_name="Ada")
    await store.add_anchor(
        entity_id=person.id, system="email", ref_type="address", value="Ada@Example.com"
    )

    resolved = await store.entity_by_anchor(system="email", value="ada@example.com")

    assert resolved == person
    assert await store.entity_by_anchor(system="email", value="nobody@example.com") is None


async def test_anchors_for_filters_by_system(store: DirectoryStore) -> None:
    person = await store.add_entity(kind="person", display_name="Ada")
    await store.add_anchor(entity_id=person.id, system="slack", ref_type="user", value="U1")
    await store.add_anchor(entity_id=person.id, system="jira", ref_type="user", value="acct-9")

    slack = await store.anchors_for(entity_id=person.id, system="slack")

    assert [a.value for a in slack] == ["U1"]
    assert len(await store.anchors_for(entity_id=person.id)) == 2


async def test_edges_traverse_both_directions_with_type_filter(store: DirectoryStore) -> None:
    boss = await store.add_entity(kind="person", display_name="Boss")
    me = await store.add_entity(kind="person", display_name="Me")
    await store.add_edge(from_id=me.id, to_id=boss.id, type="reports_to")
    await store.add_edge(from_id=me.id, to_id=boss.id, type="peer")

    reports = await store.edges_from(entity_id=me.id, type="reports_to")
    incoming = await store.edges_to(entity_id=boss.id, type="reports_to")

    assert [e.to_id for e in reports] == [boss.id]
    assert [e.from_id for e in incoming] == [me.id]


async def test_observations_roundtrip(store: DirectoryStore) -> None:
    person = await store.add_entity(kind="person", display_name="Ada")
    await store.add_observation(
        entity_id=person.id, content="prefers async updates", source="slack"
    )

    facts = await store.observations_for(entity_id=person.id)

    assert [o.content for o in facts] == ["prefers async updates"]


async def test_vocabulary_lists_distinct_in_use(store: DirectoryStore) -> None:
    person = await store.add_entity(kind="person", display_name="Ada")
    project = await store.add_entity(kind="project", display_name="Migration")
    await store.add_anchor(entity_id=person.id, system="slack", ref_type="user", value="U1")
    await store.add_edge(from_id=person.id, to_id=project.id, type="works_on")

    vocabulary = await store.vocabulary()

    assert set(vocabulary["kind"]) == {"person", "project"}
    assert vocabulary["system"] == ["slack"]
    assert vocabulary["relation"] == ["works_on"]


async def test_interaction_log_yields_count_and_last_seen(store: DirectoryStore) -> None:
    person = await store.add_entity(kind="person", display_name="Ada")
    await store.record_interaction(entity_id=person.id, kind="lookup", at=100.0)
    await store.record_interaction(entity_id=person.id, kind="reference", at=250.0)

    stats = await store.interaction_stats(entity_id=person.id)

    assert stats.count == 2
    assert stats.last_at == 250.0


async def test_interaction_stats_empty_when_never_touched(store: DirectoryStore) -> None:
    person = await store.add_entity(kind="person", display_name="Ada")

    stats = await store.interaction_stats(entity_id=person.id)

    assert stats.count == 0
    assert stats.last_at is None


async def test_merge_reassigns_anchors_edges_observations(store: DirectoryStore) -> None:
    keep = await store.add_entity(kind="person", display_name="Ada Lovelace")
    dup = await store.add_entity(kind="person", display_name="A. Lovelace")
    other = await store.add_entity(kind="project", display_name="Migration")
    await store.add_anchor(entity_id=dup.id, system="slack", ref_type="user", value="U2")
    await store.add_edge(from_id=dup.id, to_id=other.id, type="works_on")
    await store.add_observation(entity_id=dup.id, content="duplicate note")

    await store.merge_entities(keep_id=keep.id, drop_id=dup.id)

    assert await store.get_entity(entity_id=dup.id) is None
    assert (await store.anchors_for(entity_id=keep.id))[0].value == "U2"
    assert (await store.edges_from(entity_id=keep.id))[0].to_id == other.id
    assert (await store.observations_for(entity_id=keep.id))[0].content == "duplicate note"
