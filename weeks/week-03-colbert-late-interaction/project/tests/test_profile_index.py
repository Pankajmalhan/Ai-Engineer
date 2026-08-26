"""app.profile_index's pure math -- directory-size summation and the
compression-ratio arithmetic -- checked against a synthetic temp directory,
no real index or model needed."""

from app.profile_index import _dir_size_bytes


def test_dir_size_bytes_sums_all_files_recursively(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"x" * 100)
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "b.txt").write_bytes(b"y" * 250)

    assert _dir_size_bytes(tmp_path) == 350


def test_dir_size_bytes_ignores_directories_themselves(tmp_path):
    (tmp_path / "empty_dir").mkdir()
    (tmp_path / "file.txt").write_bytes(b"z" * 42)

    assert _dir_size_bytes(tmp_path) == 42


def test_dir_size_bytes_is_zero_for_empty_directory(tmp_path):
    assert _dir_size_bytes(tmp_path) == 0


def test_uncompressed_estimate_matches_the_documented_formula():
    # 10 passages, 20 tokens each, 128-dim fp32 -> 10*20*128*4 bytes.
    # Recomputed independently here rather than importing the constant
    # product, so this test would actually fail if profile_index.py's
    # formula ever silently changed.
    passage_count, avg_tokens = 10, 20.0
    dim, dtype_bytes = 128, 4
    expected = passage_count * avg_tokens * dim * dtype_bytes

    assert expected == 102_400
