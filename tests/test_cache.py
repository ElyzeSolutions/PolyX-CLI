"""Test caching."""

from polyx.config import Config
from polyx.storage.cache import FileCache


def test_file_cache(tmp_path):
    config = Config.load()
    config.data_dir = tmp_path
    cache = FileCache(config)

    data = {"hello": "world"}
    key = "test_key"

    # Set and get
    cache.set(key, data, ttl=10)
    assert cache.get(key) == data

    # Expired
    cache.set(key, data, ttl=-1)
    assert cache.get(key) is None

    # Clear
    cache.set(key, data, ttl=10)
    cache.clear()
    assert cache.get(key) is None


def test_cache_stats(tmp_path):
    config = Config.load()
    config.data_dir = tmp_path
    cache = FileCache(config)
    cache.set("key1", {"a": 1}, ttl=10)
    cache.set("key2", {"b": 2}, ttl=10)

    stats = cache.stats()
    assert stats["total_files"] == 2
    assert stats["total_size_kb"] > 0
