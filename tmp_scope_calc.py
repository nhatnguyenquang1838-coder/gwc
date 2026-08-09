import sys
sys.path.insert(0, 'tools')
from node_architect.scope_hash_calculation import calculate_gate_scope_identity

result = calculate_gate_scope_identity(
    task_id="SCRUM-298",
    repository="nhatnguyenquang1838-coder/gwc",
    base_ref="main",
    base_sha="cff9fb1bbe55493ccc8bc7b48e48f613521a58b2",
    working_branch="feat/scrum-298-intake-request-intake",
    head_sha=None,
    risk_class="R0",
    authorized_paths=[
        "schemas/request-intake-record.schema.json",
        "tools/node_architect/request_intake.py",
        "tests/test_intake_context_request_intake_m4.py",
        "tools/node_architect/validate_node_catalog_intake_context.py",
        ".gwc/tasks/SCRUM-298/g0/context-snapshot.yaml",
        ".gwc/tasks/SCRUM-298/g1/intake/alignment.yaml",
        ".gwc/tasks/SCRUM-298/g1/intake/brainstorming.yaml",
        ".gwc/tasks/SCRUM-298/g1/intake/decision.yaml",
        ".gwc/tasks/SCRUM-298/g1/intake/preflight.yaml"
    ],
    authorized_actions=[
        "create_guarded_branch_or_worktree",
        "modify_approved_files",
        "run_sandboxed_validation",
        "stage",
        "create_commit",
        "push_working_branch",
        "read_repository",
        "inspect_task",
        "materialize_g1_artifacts",
        "run_read_only_validation"
    ],
    excluded_actions=[
        "merge_approved_pr",
        "deploy_approved_release",
        "production_data_write",
        "production_config_change",
        "credential_rotation",
        "migration",
        "open_or_update_draft_pr",
        "mark_pr_ready_for_review",
        "run_independent_review",
        "verify_post_merge_ci"
    ],
    additional_bindings=[]
)

print("SCOPE_CALCULATION_START")
print(f"outcome:{result['outcome']}")
print(f"reason_codes:{','.join(result['reason_codes'])}")
if result.get('scope_hash'):
    hex_part = result['scope_hash'].split(':')[1]
    scope_hash_16 = hex_part[6:22]
    print(f"scope_hash_16:{scope_hash_16}")
    print(f"full_scope_hash:{result['scope_hash']}")
else:
    print("scope_hash_16:NONE")
print("SCOPE_CALCULATION_END")