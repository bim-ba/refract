import jinja2
import pytest

from refract.emitters.python.templating import make_template_environment

env = make_template_environment()


def test_strict_undefined_raises_on_missing():
    with pytest.raises(jinja2.UndefinedError):
        env.from_string("{{ missing }}").render()


def test_trim_blocks_strips_newline_after_block_tag():
    out = env.from_string("{% for x in xs %}{{ x }}\n{% endfor %}").render(xs=["a", "b"])
    assert out == "a\nb\n"


def test_keeps_trailing_newline():
    assert env.from_string("x\n").render() == "x\n"
