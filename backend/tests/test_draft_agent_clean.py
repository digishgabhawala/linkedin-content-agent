from app.agents.draft_agent import _clean_draft_output, _strip_wrapping_quotes


def test_strip_wrapping_quotes_removes_matching_double_quotes():
    assert _strip_wrapping_quotes('"hello world"') == "hello world"


def test_strip_wrapping_quotes_removes_matching_curly_quotes():
    assert _strip_wrapping_quotes("“hello world”") == "hello world"


def test_strip_wrapping_quotes_leaves_unquoted_text_alone():
    assert _strip_wrapping_quotes("hello world") == "hello world"


def test_strip_wrapping_quotes_leaves_mismatched_quotes_alone():
    assert _strip_wrapping_quotes('"hello world') == '"hello world'


def test_clean_draft_output_strips_trailing_self_reported_char_count():
    # Found live: the model appended "---\n(1,120 characters)" to a draft
    # that was actually ~870 chars -- claiming compliance instead of
    # achieving it. This must be stripped, not trusted.
    text = "This is my actual post text.\n\n---\n(1,120 characters)"
    assert _clean_draft_output(text) == "This is my actual post text."


def test_clean_draft_output_strips_trailing_count_without_separator():
    text = "This is my actual post text.\n\n(870 characters)"
    assert _clean_draft_output(text) == "This is my actual post text."


def test_clean_draft_output_strips_approx_count_without_comma():
    text = "Real content here.\n~870 characters"
    assert _clean_draft_output(text) == "Real content here."


def test_clean_draft_output_leaves_normal_text_alone():
    text = "A completely normal post with no trailing metadata at all."
    assert _clean_draft_output(text) == text


def test_clean_draft_output_combines_quote_stripping_and_meta_stripping():
    text = '"Wrapped in quotes.\n\n(500 characters)"'
    assert _clean_draft_output(text) == "Wrapped in quotes."
