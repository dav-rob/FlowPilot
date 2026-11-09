"""Generator determinism, parameter validation, quota/difficulty invariants, referential/evidence integrity and split isolation tests."""
from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from flowpilot_data.generate import check_out_root, generate
from flowpilot_data.planning import validate_params
from flowpilot_data.util import read_json, read_jsonl, tree_hash
from flowpilot_data.validate import validate

REPO_ROOT = Path(__file__).resolve().parent.parent


class GeneratorAndValidationTests(unittest.TestCase):
    def test_parameter_and_output_path_validation(self):
        for bad_seed in (-1, 2**63, True, False, "42", 3.14, None):
            with self.assertRaises(ValueError, msg=f"seed={bad_seed!r}"):
                validate_params(bad_seed, 250)
        for bad_size in (0, 41, 20001, True, False, "250", 100.5):
            with self.assertRaises(ValueError, msg=f"size={bad_size!r}"):
                validate_params(42, bad_size)

        with self.assertRaises(ValueError):
            check_out_root("../outside")
        with self.assertRaises(ValueError):
            check_out_root("/")
        with self.assertRaises(ValueError):
            check_out_root("~")

    def test_safe_install_refuses_unmarked_overwrite_and_preserves_unrelated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            (root / "data" / "partitions").mkdir(parents=True)
            with self.assertRaises(FileExistsError):
                generate(root, seed=7, size=42)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "workspace"
            root.mkdir(parents=True)
            keep_top = root / "custom_notes.txt"
            keep_top.write_text("do not delete", encoding="utf-8")
            (root / "data").mkdir()
            keep_sub = root / "data" / "local_override.json"
            keep_sub.write_text('{"keep": true}', encoding="utf-8")

            generate(root, seed=7, size=42)
            generate(root, seed=8, size=42)

            self.assertEqual(keep_top.read_text(encoding="utf-8"), "do not delete")
            self.assertEqual(keep_sub.read_text(encoding="utf-8"), '{"keep": true}')

    def test_deterministic_regeneration_and_seed_variation(self):
        with tempfile.TemporaryDirectory() as tmp:
            d1 = Path(tmp) / "run1"
            d2 = Path(tmp) / "run2"
            d3 = Path(tmp) / "run_other_seed"
            generate(d1, seed=101, size=50)
            generate(d2, seed=101, size=50)
            generate(d3, seed=202, size=50)

            self.assertEqual(tree_hash(d1 / "data"), tree_hash(d2 / "data"))
            self.assertEqual(tree_hash(d1 / "evaluation"), tree_hash(d2 / "evaluation"))
            self.assertNotEqual(tree_hash(d1 / "data"), tree_hash(d3 / "data"))

            ids_101 = {c["case_id"] for c in read_jsonl(d1 / "data" / "partitions" / "train" / "cases.jsonl")}
            ids_202 = {c["case_id"] for c in read_jsonl(d3 / "data" / "partitions" / "train" / "cases.jsonl")}
            self.assertTrue(ids_101.isdisjoint(ids_202))

    def test_varied_seeds_and_sizes_pass_full_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            for seed, size in ((7, 42), (19, 65), (99, 80)):
                out = Path(tmp) / f"s_{seed}_{size}"
                manifest = generate(out, seed=seed, size=size)
                self.assertEqual(manifest["total_cases"], size)
                rep = validate(out, replay_all=True)
                self.assertTrue(rep["ok"], f"seed={seed} size={size} errors={rep['errors']}")
                self.assertEqual(rep["cases"], size)
                self.assertGreater(rep["paths_replayed"], size)

    def test_default_seed42_size250_quotas_isolation_and_integrity(self):
        rep = validate(REPO_ROOT, replay_all=True)
        self.assertTrue(rep["ok"], rep["errors"])
        self.assertEqual(rep["cases"], 250)
        self.assertLessEqual(rep["max_cross_partition_similarity"], 0.6)

        manifest = read_json(REPO_ROOT / "evaluation" / "manifests" / "dataset_manifest.json")
        self.assertEqual(manifest["seed"], 42)
        self.assertEqual(manifest["size"], 250)
        self.assertEqual(
            manifest["by_group"],
            {
                "supplier_fraud": 40,
                "regulatory_compliance": 40,
                "gdpr_data": 40,
                "it_asset": 40,
                "contract_risk": 40,
                "cross_domain": 25,
                "distractor": 25,
            },
        )
        self.assertEqual(
            manifest["by_difficulty"],
            {"straightforward": 125, "moderate": 75, "difficult": 50},
        )

        truth_by_part = {
            p: read_jsonl(REPO_ROOT / "evaluation" / "ground_truth" / f"{p}.jsonl")
            for p in ("train", "validation", "test")
        }
        self.assertEqual({p: len(rows) for p, rows in truth_by_part.items()}, {"train": 150, "validation": 50, "test": 50})

        # Verify whole-family holdout across partitions
        fams = {p: {t["family_id"] for t in rows} for p, rows in truth_by_part.items()}
        self.assertTrue(fams["train"].isdisjoint(fams["validation"]))
        self.assertTrue(fams["train"].isdisjoint(fams["test"]))
        self.assertTrue(fams["validation"].isdisjoint(fams["test"]))

        # Verify multiple document formats exist across the dataset
        exts = Counter()
        for p in ("train", "validation", "test"):
            pub_cases = read_jsonl(REPO_ROOT / "data" / "partitions" / p / "cases.jsonl")
            for c in pub_cases:
                self.assertEqual( set(c.keys()), {"case_id", "partition", "received_at", "document", "attachments"})
                name = c["document"]["path"]
                exts[name.split(".", 1)[1]] += 1
        for expected_ext in ("eml", "txt", "md", "event.json", "events.jsonl"):
            self.assertGreater(exts[expected_ext], 0, f"missing format {expected_ext}")

    def test_validator_detects_leaked_token_and_dangling_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "corrupt_check"
            generate(out, seed=11, size=42)
            # Inject a leaked ground-truth token into an inbox document and a dangling ID into an enterprise table
            cases = read_jsonl(out / "data" / "partitions" / "train" / "cases.jsonl")
            doc_file = out / "data" / "partitions" / "train" / cases[0]["document"]["path"]
            doc_file.write_text(doc_file.read_text(encoding="utf-8") + "\nexpected_outcome: approve_and_process\n", encoding="utf-8")

            sup_file = out / "data" / "partitions" / "train" / "enterprise" / "suppliers.jsonl"
            sups = read_jsonl(sup_file)
            sups[0]["account_manager_id"] = "EMP-DEADBEEF"
            sup_file.write_text("".join(json.dumps(r) + "\n" for r in sups), encoding="utf-8")

            rep = validate(out, replay_all=False)
            self.assertFalse(rep["ok"])
            self.assertTrue(any("dangling reference" in e and "EMP-DEADBEEF" in e for e in rep["errors"]), rep["errors"])
            self.assertTrue(any("leak:" in e for e in rep["errors"]), rep["errors"])


if __name__ == "__main__":
    unittest.main()
