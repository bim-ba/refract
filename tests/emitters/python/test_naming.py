from refract.emitters.python.naming import PythonNaming

n = PythonNaming()


def test_pascal():
    assert n.pascal("me") == "Me"
    assert n.pascal("localized_name") == "LocalizedName"


def test_module_function_guards_shadowed_names():
    assert n.module_function("list") == "list_"  # shadows builtin at module scope
    assert n.module_function("import") == "import_"  # keyword
    assert n.module_function("get") == "get"  # unchanged


def test_safe_param_guards_shadowed_names():
    assert n.safe_param("id") == "id_"  # shadows builtin -> ruff A002 without the guard
    assert n.safe_param("type") == "type_"  # shadows builtin
    assert n.safe_param("class") == "class_"  # keyword -> bare `class` is a SyntaxError
    assert n.safe_param("priority_id") == "priority_id"  # unchanged (no-op on the corpus)


def test_class_name_merges_the_three_helpers():
    assert n.class_name("me", "Client") == "MeClient"  # was resource_client_class
    assert n.class_name("tracker", "Resource") == "TrackerResource"  # was domain_resource_base
    assert n.class_name("tracker", "Client") == "TrackerClient"  # was domain_client_class


def test_cli_option_snake_joins_parts():
    assert n.cli_option("key") == "key"  # single part -> verbatim
    assert n.cli_option("name", "ru") == "name_ru"  # typer auto-derives the --name-ru flag
