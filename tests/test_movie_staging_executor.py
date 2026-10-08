import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from movie_staging_executor import exact_release, movie_id


class MovieStagingExecutorTests(unittest.TestCase):
    movie = {"id": 15, "title": "Movie", "year": 2012,
             "movieFile": {"id": 9, "size": 20 * 1073741824}}
    release = {"title": "Movie 1080p BluRay x265", "size": 6 * 1073741824,
               "seeders": 10, "infoHash": "a" * 40, "indexerId": 4,
               "quality": {"quality": {"name": "Bluray-1080p"}},
               "rejections": ["Existing file meets cutoff: Bluray-2160p"]}
    snapshot = {"identity_key": "movie:radarr:15", "title": "Movie (2012)",
                "source_file_id": "9", "source_size_bytes": 20 * 1073741824,
                "release_id": "a" * 40, "release_title": "Movie 1080p BluRay x265",
                "release_size_bytes": 6 * 1073741824, "indexer_id": "4"}

    def test_exact_release_requires_the_pinned_values(self):
        self.assertIsNotNone(exact_release(self.snapshot, self.movie, [self.release], {}))
        self.assertIsNone(exact_release(dict(self.snapshot, release_size_bytes=5 * 1073741824), self.movie, [self.release], {}))

    def test_identity_must_be_a_movie_radarr_key(self):
        self.assertEqual(movie_id(self.snapshot), 15)
        with self.assertRaises(ValueError):
            movie_id(dict(self.snapshot, identity_key="season:sonarr:15"))
