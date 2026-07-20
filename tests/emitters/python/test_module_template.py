from refract.emitters.python.templating import make_template_environment


def test_module_skeleton_lays_out_doc_imports_body():
    env = make_template_environment()
    child = env.from_string(
        '{% extends "_module.jinja" %}{% block body %}CLASS_BODY\n{% endblock %}'
    )
    out = child.render(
        page={
            "doc_block": ('"""Doc."""',),
            "header_lines": (),
            "import_lines": ("from .models import Me",),
        }
    )
    assert '"""Doc."""' in out
    assert "from .models import Me" in out
    assert "CLASS_BODY" in out
    assert out.index('"""Doc."""') < out.index("from .models import Me") < out.index("CLASS_BODY")
