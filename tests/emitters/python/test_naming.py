from refract.emitters.python.naming import PythonNaming

n = PythonNaming()


def test_identifier_guards_shadowed_def_names():
    assert n.identifier("list") == "list_"  # shadows builtin at module scope
    assert n.identifier("import") == "import_"  # keyword
    assert n.identifier("get") == "get"  # unchanged


def test_identifier_guards_shadowed_parameter_names():
    """The SAME guard serves a parameter: a def name and a parameter name are both Python
    identifiers, so one method covers both (a backend whose two cases differ overrides it once)."""
    assert n.identifier("id") == "id_"  # shadows builtin -> ruff A002 without the guard
    assert n.identifier("type") == "type_"  # shadows builtin
    assert n.identifier("class") == "class_"  # keyword -> bare `class` is a SyntaxError
    assert n.identifier("priority_id") == "priority_id"  # unchanged (no-op on the corpus)


def test_class_name_merges_the_three_helpers():
    assert n.class_name("me", "Client") == "MeClient"  # was resource_client_class
    assert n.class_name("tracker", "Resource") == "TrackerResource"  # was domain_resource_base
    assert n.class_name("tracker", "Client") == "TrackerClient"  # was domain_client_class
    assert n.class_name("localized_name", "") == "LocalizedName"  # the pascal case it wraps


def test_cli_option_joins_parent_and_child():
    assert n.cli_option("name", "ru") == "name_ru"  # typer auto-derives the --name-ru flag
