from repo.services.planner.providers.comfyui_video import _slug

def test_slug_basic():
    assert _slug("Hello World") == "hello-world"

def test_slug_special_characters():
    assert _slug("Hello! World?") == "hello-world"

def test_slug_multiple_spaces():
    assert _slug("Hello   World") == "hello-world"

def test_slug_long_text():
    long_text = "a" * 100
    assert _slug(long_text) == "a" * 48
    assert len(_slug(long_text)) == 48

def test_slug_empty_result():
    assert _slug("!!!") == "comfyui-job"
    assert _slug("") == "comfyui-job"

def test_slug_numbers():
    assert _slug("Job 123") == "job-123"

def test_slug_mixed_case():
    assert _slug("MixED Case") == "mixed-case"

def test_slug_leading_trailing_hyphens():
    assert _slug("-Hello-") == "hello"
    assert _slug("---Hello---") == "hello"

def test_slug_max_length_exactly_48():
    text = "a" * 48
    assert _slug(text) == text
    assert len(_slug(text)) == 48

def test_slug_max_length_plus_one():
    text = "a" * 49
    assert _slug(text) == "a" * 48
    assert len(_slug(text)) == 48
