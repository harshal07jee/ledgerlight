import hashlib
import os


def test_fixture_checksums_integrity():
    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    checksums_file = os.path.join(fixtures_dir, "CHECKSUMS.txt")

    assert os.path.exists(checksums_file), (
        "tests/fixtures/CHECKSUMS.txt is missing"
    )

    with open(checksums_file, "r", encoding="utf-8") as f:
        recorded_entries = [
            line.strip().split("  ", 1)
            for line in f
            if line.strip()
        ]

    assert len(recorded_entries) == 15, (
        f"Expected 15 fixture entries in CHECKSUMS.txt, "
        f"got {len(recorded_entries)}"
    )

    for expected_hash, rel_path in recorded_entries:
        abs_path = os.path.join(
            fixtures_dir,
            rel_path.replace("/", os.sep),
        )

        assert os.path.exists(abs_path), f"Fixture missing: {rel_path}"

        with open(abs_path, "rb") as fp:
            actual_hash = hashlib.sha256(fp.read()).hexdigest()

        assert actual_hash == expected_hash, (
            f"Fixture modified without explicit approval! File: {rel_path}\n"
            f"Expected SHA-256: {expected_hash}\n"
            f"Actual SHA-256:   {actual_hash}"
        )