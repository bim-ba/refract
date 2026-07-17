import refract


def test_version_is_read_from_metadata():
    # importlib.metadata.version("refract") for the installed dist; never the hardcoded "0.0.0".
    assert refract.__version__ != "0.0.0"
    assert refract.__version__  # non-empty string
