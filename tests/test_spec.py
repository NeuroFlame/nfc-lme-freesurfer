"""Smoke tests for the computation spec and its math, run without NVFlare."""

import json
import logging
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from computation.inputs import load_inputs
from computation.local_math import (
    compute_global_products,
    compute_level_residuals,
    compute_local_stats,
)
from computation.remote_math import (
    compute_global_model,
    gather_site_levels,
    merge_level_residuals,
)
from computation.results import build_outputs
from computation.spec import SPEC
from computation.types import (
    GlobalFit,
    GlobalLevels,
    LocalState,
    SiteLevelResiduals,
    SiteLevels,
    SiteProducts,
)
from computation.validation import validate_and_get_inputs
from framework.serialization import deserialize_value, serialize_value
from framework.workflow import get_task_names

TEST_DATA = Path(__file__).resolve().parents[1] / "test_data"
LOGGER = logging.getLogger("test")
LOGGER.addHandler(logging.NullHandler())
LOGGER.propagate = False


def _transport(value, expected_type=None):
    """Round-trip a value the way the framework does between participants."""
    wire = json.loads(json.dumps(serialize_value(value)))
    return deserialize_value(wire, expected_type)


class SpecTests(unittest.TestCase):
    """The computation spec builds and exposes the expected site task names."""

    def test_task_names(self):
        self.assertEqual(
            get_task_names(SPEC.workflow),
            [
                "compute_local_stats",
                "compute_global_products",
                "compute_level_residuals",
                "build_outputs",
            ],
        )

    def test_local_state_type_is_inferred(self):
        self.assertIs(SPEC.workflow.local_state_type, LocalState)


class GatherSiteLevelsTests(unittest.TestCase):
    """Sites get contiguous global Z column offsets, ordered by site name."""

    def test_offsets_follow_site_name_order(self):
        result = gather_site_levels(
            {
                "site_b": SiteLevels(
                    "token-b", nlevels=2, nobservns=10, random_factor_labels=["x", "y"]
                ),
                "site_a": SiteLevels(
                    "token-a", nlevels=3, nobservns=11, random_factor_labels=None
                ),
            }
        )
        self.assertEqual(
            result.payload.col_offset_per_token, {"token-a": 0, "token-b": 3}
        )
        self.assertEqual(result.payload.nlevels_global, 5)
        self.assertEqual(result.state["nobservns_global"], 21)
        self.assertEqual(
            result.state["random_factor_labels_per_site"],
            {"site_a": None, "site_b": ["x", "y"]},
        )


class RandomFactorEncodingTests(unittest.TestCase):
    """RandomFactor labels are encoded into dense, sorted, 1-indexed levels."""

    def _validate(self, covariates: pd.DataFrame, parameters: dict):
        with tempfile.TemporaryDirectory() as directory:
            covariates_path = Path(directory) / "covariates.csv"
            data_path = Path(directory) / "data.csv"
            covariates.to_csv(covariates_path, index=False)
            pd.DataFrame({"roi": [1.0, 2.0, 3.0, 4.0]}).to_csv(data_path, index=False)
            return validate_and_get_inputs(
                str(covariates_path), str(data_path), parameters, LOGGER
            )

    def setUp(self):
        self.parameters = {
            "Covariates": {"age": "float"},
            "Dependents": {"roi": "float"},
            "RandomFactorColumn": "institution",
        }

    def test_string_labels(self):
        covariates = pd.DataFrame(
            {
                "age": [20.0, 30.0, 40.0, 50.0],
                "institution": ["zeta", "alpha", "zeta", "mid"],
            }
        )
        is_valid, _, _, random_factor, labels = self._validate(
            covariates, self.parameters
        )
        self.assertTrue(is_valid)
        self.assertEqual(labels, ["alpha", "mid", "zeta"])
        self.assertEqual(random_factor.tolist(), [3, 1, 3, 2])

    def test_missing_column_is_a_single_level(self):
        covariates = pd.DataFrame({"age": [20.0, 30.0, 40.0, 50.0]})
        is_valid, _, _, random_factor, labels = self._validate(
            covariates, self.parameters
        )
        self.assertTrue(is_valid)
        self.assertIsNone(labels)
        self.assertEqual(random_factor.tolist(), [1, 1, 1, 1])

    def test_missing_covariate_header_is_invalid(self):
        covariates = pd.DataFrame({"not_age": [20.0, 30.0, 40.0, 50.0]})
        is_valid, *_ = self._validate(covariates, self.parameters)
        self.assertFalse(is_valid)


class ProtocolTests(unittest.TestCase):
    """The full protocol runs on the repo test data, with transport round-trips."""

    @classmethod
    def setUpClass(cls):
        with open(TEST_DATA / "server" / "parameters.json", encoding="utf-8") as f:
            cls.parameters = json.load(f)
        cls.sites = ["site1", "site2"]

        states = {}
        site_levels = {}
        for site in cls.sites:
            inputs = load_inputs(str(TEST_DATA / site), cls.parameters, LOGGER)
            step = compute_local_stats(inputs, cls.parameters)
            states[site] = _transport(step.state, LocalState)
            site_levels[site] = _transport(step.payload, SiteLevels)

        step = gather_site_levels(site_levels)
        remote_state = step.state
        global_levels = _transport(step.payload, GlobalLevels)

        site_products = {
            site: _transport(
                compute_global_products(global_levels, states[site]), SiteProducts
            )
            for site in cls.sites
        }
        step = compute_global_model(site_products, remote_state, cls.parameters)
        remote_state = step.state
        global_fit = _transport(step.payload, GlobalFit)

        site_residuals = {
            site: _transport(
                compute_level_residuals(global_fit, states[site]), SiteLevelResiduals
            )
            for site in cls.sites
        }
        cls.result = _transport(merge_level_residuals(site_residuals, remote_state))
        cls.outputs = build_outputs(cls.result, cls.parameters)

    def test_one_regression_per_dependent(self):
        self.assertEqual(
            [regression["ROI"] for regression in self.result["regressions"]],
            list(self.parameters["Dependents"]),
        )

    def test_local_stats_are_keyed_by_site(self):
        for regression in self.result["regressions"]:
            self.assertEqual(list(regression["local_stats"]), self.sites)

    def test_contrasts_are_reported(self):
        inference = self.result["regressions"][0]["global_stats"][
            "Inference Statistics"
        ]
        self.assertEqual(
            [contrast["Contrast Name"] for contrast in inference["T-Contrasts"]],
            ["Intercept", "age", "isControl"],
        )
        self.assertEqual(
            [contrast["Contrast Name"] for contrast in inference["F-Contrasts"]],
            ["OmnibusF"],
        )

    def test_random_effect_levels(self):
        levels = self.result["random_effect_levels"]
        self.assertEqual(
            levels["total"], sum(len(labels) for labels in levels["per_site"].values())
        )
        self.assertEqual(
            {
                site: list(residuals)
                for site, residuals in self.result["level_residuals"][
                    "per_site"
                ].items()
            },
            levels["per_site"],
        )

    def test_output_files(self):
        self.assertEqual(
            list(self.outputs),
            [
                "global_regression_result.json",
                "index.html",
                "global_stats.csv",
                "local_stats_site1.csv",
                "local_stats_site2.csv",
            ],
        )
        self.assertEqual(self.outputs["global_stats.csv"].index.name, "ROI")
        self.assertIn(
            "<title>Federated LME Regression Report</title>", self.outputs["index.html"]
        )


if __name__ == "__main__":
    unittest.main()
