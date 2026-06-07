from directory import vocab


def test_aliases_fold_to_canonical() -> None:
    assert vocab.normalize_relation("reports-to") == "reports_to"
    assert vocab.normalize_relation("Reports To") == "reports_to"
    assert vocab.normalize_system("GitLab.com") == "gitlab"
    assert vocab.normalize_ref_type("repository") == "repo"
    assert vocab.normalize_kind("issue") == "ticket"


def test_distinct_canonicals_are_not_merged() -> None:
    assert vocab.normalize_relation("manages") == "manages"
    assert vocab.normalize_relation("reports_to") == "reports_to"


def test_unknown_values_are_slugged_but_kept() -> None:
    assert vocab.normalize_relation("blesses the code") == "blesses_the_code"
    assert vocab.normalize_system("SomeNewTool") == "somenewtool"


def test_normalize_key_slugs() -> None:
    assert vocab.normalize_key("Start Date") == "start_date"


def test_newly_canonical_values_are_present() -> None:
    s = vocab.suggested()
    assert {"collaborates_with", "stakeholder_of", "sponsors", "tagged"} <= set(s["relation"])
    assert "sharepoint" in s["system"]
    assert vocab.normalize_relation("works_with") == "collaborates_with"
    assert vocab.normalize_relation("stakeholder") == "stakeholder_of"


def test_suggested_lists_each_facet() -> None:
    s = vocab.suggested()
    assert {"kind", "system", "ref_type", "relation"} <= set(s)
    assert "reports_to" in s["relation"]
