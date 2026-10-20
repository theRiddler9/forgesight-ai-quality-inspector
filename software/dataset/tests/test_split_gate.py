import pytest

from software.dataset.audit import audit_dataset, split_manifest
from software.dataset.manifest import DatasetManifest
from software.dataset.tests.test_dataset import sample_manifest


def test_split_records_policy_and_refuses_regeneration():
    manifest = DatasetManifest.model_validate(sample_manifest())
    split = split_manifest(manifest, "physical_part_id", seed=77)
    assert split.split_policy.seed == 77
    assert split.split_policy.group_by == "physical_part_id"
    assert len(split.split_policy.input_sha256) == 64
    with pytest.raises(ValueError, match="already assigned"):
        split_manifest(split, "physical_part_id", seed=78)


def test_session_and_part_connections_are_kept_in_one_split():
    data = sample_manifest()
    data["entries"][2]["capture_session"] = data["entries"][0]["capture_session"]
    manifest = DatasetManifest.model_validate(data)
    split = split_manifest(manifest, "physical_part_id", seed=2)
    assert split.entries[0].split == split.entries[2].split


def test_split_audit_fails_cross_split_duplicate_and_unreviewed_test():
    data = sample_manifest()
    data["entries"][0]["split"] = "train"
    data["entries"][1]["split"] = "test"
    data["entries"][1]["sha256"] = data["entries"][0]["sha256"]
    data["entries"][1]["review_status"] = "unreviewed"
    report = audit_dataset(DatasetManifest.model_validate(data), "physical_part_id")
    assert not report["split_audit"]["passed"]
    assert report["split_audit"]["cross_split_duplicates"]
    assert report["split_audit"]["unreviewed_evaluation_images"] == ["img-1"]
