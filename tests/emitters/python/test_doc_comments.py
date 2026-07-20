from refract.emitters.python.doc_comments import PythonDocComments

d = PythonDocComments()


def test_absent_text_is_empty():
    assert d.render(None, "    ") == ()
    assert d.render("", "    ") == ()


def test_single_line():
    assert d.render("Hello.", "    ") == ('    """Hello."""',)


def test_multiline_reindents_and_closes_on_own_line():
    out = d.render("First.\n\n    Indented.", "    ")
    assert out == ('    """First.', "", "        Indented.", '    """')
