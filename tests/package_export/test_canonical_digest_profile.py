#!/usr/bin/env python3
"""Contract/schema tests for SCRUM-397 WP2 canonical digest profile + registry.

Scope: WP2 ONLY. Validates that the committed normative artifacts conform to
their JSON-Schema contracts and encode the exact WP2 normative contract:
  - gwc-jcs-v1 profile (RFC-8785/JCS-compatible, strict input domain,
    negative_zero_policy=reject, non-finite reject, non-string-key reject,
    duplicate raw JSON key reject before semantic collapse, Unicode
    normalization=none, SHA-256, domain separation + preimage framing,
    bounded resource limits, deterministic error taxonomy).
  - digest-profile-registry lifecycle EXACTLY NEW_WRITE_ALLOWED|VERIFY_ONLY|REJECTED,
    fail-closed (gwc-jcs-v1 NOT activated for new writes).
  - digest-envelope binding contract.

Deliberately EXCLUDED (hard exclusions): cross-runtime reference verifier /
golden corpus (WP3); shared runtime digest API / legacy verifier (WP4);
consumer migration (WP5). This file validates schema/data conformance only.
"""

import json
import sys
import unittest
from pathlib import Path

import jsonschema
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GOV = REPO_ROOT / "governance"
SCHEMAS = REPO_ROOT / "schemas"

# Canonical lifecycle states (normative closed set).
LIFECYCLE_STATES = frozenset({"NEW_WRITE_ALLOWED", "VERIFY_ONLY", "REJECTED"})


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class ProfileSchemaTest(unittest.TestCase):
    """gwc-jcs-v1 profile conformance to canonical-digest-profile.schema.json."""

    @classmethod
    def setUpClass(cls):
        cls.schema = _load_json(SCHEMAS / "canonical-digest-profile.schema.json")
        cls.validator = jsonschema.Draft202012Validator(cls.schema)
        cls.profile = _load_yaml(GOV / "digest-profiles" / "gwc-jcs-v1.yaml")

    def test_schema_is_draft2020_12(self):
        self.assertEqual(
            cls := self.schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )

    def test_profile_conforms_to_schema(self):
        errors = sorted(self.validator.iter_errors(self.profile), key=str)
        self.assertEqual([], [str(e) for e in errors])

    def test_profile_id(self):
        self.assertEqual(self.profile["profile_id"], "gwc-jcs-v1")

    def test_status_is_definition_maturity_not_activation(self):
        # status describes definition maturity only; registry is the sole
        # activation authority (gwc-jcs-v1 lifecycle=REJECTED there).
        self.assertEqual(self.profile["status"], "defined")

    def test_specification_is_rfc8785_jcs(self):
        self.assertEqual(self.profile["specification"], "RFC_8785_JCS_COMPATIBLE")

    def test_strict_input_domain_policies(self):
        d = self.profile["strict_input_domain"]
        self.assertEqual(d["negative_zero_policy"], "reject")
        self.assertEqual(d["non_finite_policy"], "reject")
        self.assertEqual(d["non_string_key_policy"], "reject")
        self.assertEqual(d["duplicate_raw_key_policy"], "reject_before_semantic_collapse")
        self.assertEqual(d["unicode_normalization"], "none")

    def test_canonical_byte_contract_is_not_naive_json_dumps(self):
        c = self.profile["canonical_byte_contract"]
        self.assertEqual(c["standard"], "RFC_8785")
        self.assertEqual(c["key_ordering"], "lexicographic_utf16_code_unit")
        self.assertEqual(c["number_serialization"], "jcs_shortest_round_trip")
        self.assertEqual(c["string_escaping"], "jcs_minimal")
        self.assertEqual(c["utf8_encoding"], "strict_utf8")
        self.assertEqual(c["unicode_normalization"], "none")

    def test_hash_binding(self):
        h = self.profile["hash_binding"]
        self.assertEqual(h["algorithm"], "SHA-256")
        self.assertEqual(h["hex_digest_lowercase"], True)
        self.assertEqual(h["domain_separation"], "required")
        self.assertEqual(h["preimage_framing"], "required")

    def test_domain_separation_framing(self):
        ds = self.profile["domain_separation"]
        self.assertEqual(ds["scheme"], "gwc-domain-sep-v1")
        # Explicit length-prefixed framing: u32be(domain_tag len) || tag ||
        # u64be(preimage len) || preimage. No implicit-length field.
        self.assertIn("u32be", ds["framing"])
        self.assertIn("utf8_len(domain_tag)", ds["framing"])
        self.assertIn("u64be", ds["framing"])
        self.assertIn("byte_len(preimage)", ds["framing"])
        # The framing_rule prose must describe explicit length-prefix framing
        # and never allow user-supplied domain tags.
        self.assertIn("length-prefixed", ds["framing_rule"])
        self.assertIn("no implicit-length field", ds["framing_rule"])
        self.assertIn("never user-supplied", ds["framing_rule"])

    def test_resource_limits_bounded(self):
        rl = self.profile["resource_limits"]
        for key in ("max_preimage_bytes", "max_object_depth", "max_object_keys",
                    "max_array_items", "max_string_bytes"):
            self.assertGreaterEqual(rl[key], 1)
        self.assertEqual(rl["limit_policy"], "reject_with_deterministic_error")

    def test_error_taxonomy_deterministic(self):
        et = self.profile["error_taxonomy"]
        for code in ("DIGEST_NEGATIVE_ZERO_REJECTED", "DIGEST_NON_FINITE_REJECTED",
                     "DIGEST_NON_STRING_KEY_REJECTED", "DIGEST_DUPLICATE_RAW_KEY_REJECTED",
                     "DIGEST_RESOURCE_LIMIT_EXCEEDED", "DIGEST_DOMAIN_TAG_MISMATCH",
                     "DIGEST_ENVELOPE_BINDING_MISMATCH"):
            self.assertIn(code, et)
        self.assertEqual(et["error_delivery"], "deterministic_and_replayable")

    def test_envelope_binding_fields(self):
        eb = self.profile["digest_envelope_binding"]
        for field in ("profile_id", "hash_algorithm", "domain", "schema_ref",
                      "preimage_framing_scheme", "hexdigest"):
            self.assertIn(field, eb["binds"])
        self.assertEqual(eb["schema"], "schemas/digest-envelope.schema.json")

    def test_canonicalization_never_grants_authority(self):
        g = self.profile["governance"]
        self.assertTrue(g["canonicalization_never_grants_authority"])
        self.assertTrue(g["registry_activation_fail_closed"])
        self.assertEqual(g["gwc_jcs_v1_new_write_activation"], "BLOCKED_PENDING_WP3_WP4")
        self.assertTrue(g["historical_evidence_immutable"])
        self.assertTrue(g["raw_byte_hashes_unchanged"])


class RegistrySchemaTest(unittest.TestCase):
    """digest-profile-registry.yaml conformance + fail-closed semantics."""

    @classmethod
    def setUpClass(cls):
        cls.schema = _load_json(SCHEMAS / "digest-profile-registry.schema.json")
        cls.validator = jsonschema.Draft202012Validator(cls.schema)
        cls.registry = _load_yaml(GOV / "digest-profile-registry.yaml")

    def test_registry_conforms_to_schema(self):
        errors = sorted(self.validator.iter_errors(self.registry), key=str)
        self.assertEqual([], [str(e) for e in errors])

    def test_lifecycle_states_exact_closed_set(self):
        for entry in self.registry["entries"].values():
            self.assertIn(entry["lifecycle_state"], LIFECYCLE_STATES)

    def test_gwc_jcs_v1_fail_closed_not_new_write(self):
        entry = self.registry["entries"]["gwc-jcs-v1"]
        self.assertEqual(entry["lifecycle_state"], "REJECTED")
        self.assertFalse(entry["new_write_allowed"])
        self.assertEqual(entry["reason"], "NOT_ACTIVATED_PENDING_WP3_WP4")
        self.assertEqual(entry["activation_policy"], "FAIL_CLOSED")

    def test_legacy_metadata_verify_only_no_verifier(self):
        entry = self.registry["entries"]["legacy-python-json-v1"]
        self.assertEqual(entry["lifecycle_state"], "VERIFY_ONLY")
        self.assertFalse(entry["new_write_allowed"])
        self.assertTrue(entry["verify_only_allowed"])

    def test_policy_fail_closed(self):
        p = self.registry["policy"]
        self.assertEqual(p["new_write_gate"], "registry_lifecycle_state_must_equal_NEW_WRITE_ALLOWED")
        self.assertEqual(p["unknown_profile_policy"], "REJECTED")
        self.assertTrue(p["fail_closed"])


class EnvelopeSchemaTest(unittest.TestCase):
    """digest-envelope.schema.json binding contract."""

    @classmethod
    def setUpClass(cls):
        cls.schema = _load_json(SCHEMAS / "digest-envelope.schema.json")
        cls.validator = jsonschema.Draft202012Validator(cls.schema)

    def test_valid_envelope_passes(self):
        env = {
            "schema_version": "1.0",
            "artifact_type": "digest-envelope",
            "profile_id": "gwc-jcs-v1",
            "hash_algorithm": "SHA-256",
            "domain": "gwc.governance.evidence.canonical.v1",
            "schema_ref": "schemas/canonical-digest-profile.schema.json",
            "preimage_framing_scheme": "gwc-domain-sep-v1",
            "hexdigest": "a" * 64,
        }
        self.assertTrue(self.validator.is_valid(env))

    def test_envelope_rejects_missing_binding(self):
        env = {
            "schema_version": "1.0",
            "artifact_type": "digest-envelope",
            "profile_id": "gwc-jcs-v1",
            "hash_algorithm": "SHA-256",
            "domain": "gwc.governance.evidence.canonical.v1",
            "schema_ref": "schemas/canonical-digest-profile.schema.json",
            "preimage_framing_scheme": "gwc-domain-sep-v1",
            # hexdigest missing -> invalid
        }
        self.assertFalse(self.validator.is_valid(env))

    def test_envelope_rejects_bad_digest_shape(self):
        env = {
            "schema_version": "1.0",
            "artifact_type": "digest-envelope",
            "profile_id": "gwc-jcs-v1",
            "hash_algorithm": "SHA-256",
            "domain": "gwc.governance.evidence.canonical.v1",
            "schema_ref": "schemas/canonical-digest-profile.schema.json",
            "preimage_framing_scheme": "gwc-domain-sep-v1",
            "hexdigest": "not-a-hex-digest",
        }
        self.assertFalse(self.validator.is_valid(env))

    def test_envelope_rejects_unknown_framing(self):
        env = {
            "schema_version": "1.0",
            "artifact_type": "digest-envelope",
            "profile_id": "gwc-jcs-v1",
            "hash_algorithm": "SHA-256",
            "domain": "gwc.governance.evidence.canonical.v1",
            "schema_ref": "schemas/canonical-digest-profile.schema.json",
            "preimage_framing_scheme": "some-other-framing",
            "hexdigest": "a" * 64,
        }
        self.assertFalse(self.validator.is_valid(env))


class SchemaWellFormedTest(unittest.TestCase):
    """All three schemas are well-formed Draft 2020-12 schemas."""

    def test_schemas_well_formed(self):
        for name in ("canonical-digest-profile.schema.json",
                     "digest-profile-registry.schema.json",
                     "digest-envelope.schema.json"):
            schema = _load_json(SCHEMAS / name)
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            jsonschema.Draft202012Validator.check_schema(schema)


class RegistryLifecycleNegativeTest(unittest.TestCase):
    """Correction: registry schema must REJECT inconsistent lifecycle combinations."""

    @classmethod
    def setUpClass(cls):
        cls.schema = _load_json(SCHEMAS / "digest-profile-registry.schema.json")
        cls.validator = jsonschema.Draft202012Validator(cls.schema)

    def _entry(self, lifecycle_state, new_write_allowed, verify_only_allowed):
        return {
            "schema_version": "1.0",
            "artifact_type": "digest-profile-registry",
            "registry_id": "gwc-digest-profile-registry",
            "task": "SCRUM-397",
            "work_package": "WP2",
            "entries": {
                "test-profile": {
                    "profile_id": "test-profile",
                    "lifecycle_state": lifecycle_state,
                    "new_write_allowed": new_write_allowed,
                    "verify_only_allowed": verify_only_allowed,
                    "reason": "negative test",
                    "domain": "gwc.test.domain",
                    "schema_ref": None,
                    "envelope_schema_ref": "schemas/digest-envelope.schema.json",
                    "hash_algorithm": "SHA-256",
                }
            },
            "policy": {
                "new_write_gate": "registry_lifecycle_state_must_equal_NEW_WRITE_ALLOWED",
                "verify_gate": "registry_lifecycle_state_in_NEW_WRITE_ALLOWED_OR_VERIFY_ONLY",
                "unknown_profile_policy": "REJECTED",
                "domain_binding_required": True,
                "fail_closed": True,
            },
        }

    def test_rejected_with_new_write_true_rejected_by_schema(self):
        self.assertFalse(self.validator.is_valid(
            self._entry("REJECTED", True, False)))

    def test_new_write_allowed_with_new_write_false_rejected_by_schema(self):
        self.assertFalse(self.validator.is_valid(
            self._entry("NEW_WRITE_ALLOWED", False, True)))

    def test_verify_only_with_new_write_true_rejected_by_schema(self):
        self.assertFalse(self.validator.is_valid(
            self._entry("VERIFY_ONLY", True, True)))

    def test_rejected_with_verify_only_true_rejected_by_schema(self):
        self.assertFalse(self.validator.is_valid(
            self._entry("REJECTED", False, True)))

    def test_valid_rejected_entry_passes(self):
        self.assertTrue(self.validator.is_valid(
            self._entry("REJECTED", False, False)))

    def test_valid_verify_only_entry_passes(self):
        self.assertTrue(self.validator.is_valid(
            self._entry("VERIFY_ONLY", False, True)))

    def test_valid_new_write_allowed_entry_passes(self):
        self.assertTrue(self.validator.is_valid(
            self._entry("NEW_WRITE_ALLOWED", True, True)))


class EnvelopeBindingExactSetTest(unittest.TestCase):
    """Correction: profile envelope-binding list must be EXACTLY the six
    normative fields, unique, no extras."""

    @classmethod
    def setUpClass(cls):
        cls.schema = _load_json(SCHEMAS / "canonical-digest-profile.schema.json")
        cls.validator = jsonschema.Draft202012Validator(cls.schema)
        cls.profile = _load_yaml(GOV / "digest-profiles" / "gwc-jcs-v1.yaml")

    def test_binding_list_exactly_six_unique(self):
        binds = self.profile["digest_envelope_binding"]["binds"]
        self.assertEqual(len(binds), 6)
        self.assertEqual(len(set(binds)), 6)
        self.assertEqual(set(binds), {
            "profile_id", "hash_algorithm", "domain", "schema_ref",
            "preimage_framing_scheme", "hexdigest",
        })

    def test_incomplete_binding_list_rejected(self):
        bad = dict(self.profile)
        bad["digest_envelope_binding"] = {
            "binds": ["profile_id", "hash_algorithm", "domain_tag"],
            "schema": "schemas/digest-envelope.schema.json",
            "integrity_rule": "x",
        }
        self.assertFalse(self.validator.is_valid(bad))

    def test_extra_binding_field_rejected(self):
        bad = dict(self.profile)
        bad["digest_envelope_binding"] = {
            "binds": ["profile_id", "hash_algorithm", "domain_tag", "schema_ref",
                      "preimage_framing_scheme", "hexdigest", "extra_field"],
            "schema": "schemas/digest-envelope.schema.json",
            "integrity_rule": "x",
        }
        self.assertFalse(self.validator.is_valid(bad))

    def test_duplicate_binding_field_rejected(self):
        bad = dict(self.profile)
        bad["digest_envelope_binding"] = {
            "binds": ["profile_id", "profile_id", "hash_algorithm", "domain_tag",
                      "schema_ref", "preimage_framing_scheme"],
            "schema": "schemas/digest-envelope.schema.json",
            "integrity_rule": "x",
        }
        self.assertFalse(self.validator.is_valid(bad))


class FinalTighteningNegativeTest(unittest.TestCase):
    """FINAL_SCHEMA_TIGHTENING: status=active and ambiguous framing MUST NOT validate."""

    @classmethod
    def setUpClass(cls):
        cls.schema = _load_json(SCHEMAS / "canonical-digest-profile.schema.json")
        cls.validator = jsonschema.Draft202012Validator(cls.schema)
        cls.profile = _load_yaml(GOV / "digest-profiles" / "gwc-jcs-v1.yaml")

    def test_status_active_rejected_by_schema(self):
        # 'active' is an activation term; profile status must describe definition
        # maturity only. Registry is the sole write/verify activation authority.
        bad = dict(self.profile)
        bad["status"] = "active"
        self.assertFalse(self.validator.is_valid(bad))

    def test_status_defined_still_valid(self):
        self.assertTrue(self.validator.is_valid(self.profile))

    def test_old_implicit_domain_length_framing_rejected_by_schema(self):
        # The old ambiguous framing with implicit domain-tag length must fail.
        bad = dict(self.profile)
        bad["domain_separation"] = dict(self.profile["domain_separation"])
        bad["domain_separation"]["framing"] = (
            "sha256(domain_tag || 0x00 || u64be(preimage_len) || preimage)"
        )
        self.assertFalse(self.validator.is_valid(bad))

    def test_explicit_length_prefixed_framing_valid(self):
        self.assertEqual(
            self.profile["domain_separation"]["framing"],
            "sha256( u32be(utf8_len(domain_tag)) || domain_tag_utf8 || u64be(byte_len(preimage)) || preimage )",
        )
        self.assertTrue(self.validator.is_valid(self.profile))


class CrossArtifactBindingConsistencyTest(unittest.TestCase):
    """CROSS_ARTIFACT_BINDING_MISMATCH guard: profile.digest_envelope_binding.binds
    must match the digest-envelope schema's required set exactly, so field names
    cannot drift between the profile artifact and the envelope schema."""

    NORMATIVE_BINDS = {
        "profile_id", "hash_algorithm", "domain", "schema_ref",
        "preimage_framing_scheme", "hexdigest",
    }

    @classmethod
    def setUpClass(cls):
        cls.profile = _load_yaml(GOV / "digest-profiles" / "gwc-jcs-v1.yaml")
        cls.envelope_schema = _load_json(SCHEMAS / "digest-envelope.schema.json")

    def test_profile_binds_subset_of_envelope_required(self):
        binds = set(self.profile["digest_envelope_binding"]["binds"])
        required = set(self.envelope_schema["required"])
        missing = binds - required
        self.assertEqual(missing, set(),
                         f"profile binds not present in envelope required: {missing}")

    def test_envelope_required_contains_normative_binds(self):
        required = set(self.envelope_schema["required"])
        self.assertTrue(self.NORMATIVE_BINDS <= required,
                        f"envelope schema missing normative bindings: {self.NORMATIVE_BINDS - required}")

    def test_normative_set_exact_and_unique(self):
        binds = set(self.profile["digest_envelope_binding"]["binds"])
        self.assertEqual(binds, self.NORMATIVE_BINDS)

    def test_domain_tag_should_not_be_a_binding(self):
        # The actual envelope field is 'domain', not 'domain_tag'.
        binds = set(self.profile["digest_envelope_binding"]["binds"])
        self.assertNotIn("domain_tag", binds)
        self.assertNotIn("domain_tag", set(self.envelope_schema["required"]))


if __name__ == "__main__":
    unittest.main()
