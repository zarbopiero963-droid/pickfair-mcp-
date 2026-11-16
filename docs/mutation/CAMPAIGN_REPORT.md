# Campagne dei mutanti critici: esito per mutante

Mandato owner PF-CLAUDE-C-MCP-BLACKBOX-INTEGRATION-20261109 §1. Ogni numero qui sotto è generato da
`campaign_report.py` a partire dal suo file JSONL, che è versionato in questa cartella: nessun numero è scritto a
mano.

## Metodo

- **Catalogo**: `scripts/critical_mutations.py` (`MUTANTS`). Ogni campagna usa il catalogo del commit sotto prova.
  La guardia `tests/guards/test_mutation_catalog.py` verifica che ogni mutante si applichi esattamente una volta.
- **Esecuzione**: `run_campaign.py <worktree del commit> <out.jsonl> 3` con 3 worker in parallelo.
  - Ogni worker ha una copia propria del worktree (le directory `COPY`).
  - Ogni worker esegue prima la baseline sul codice non mutato, poi i suoi mutanti uno alla volta, con
    `pytest -x` sui test `TEST_ARGS`.
  - Il tempo massimo per suite è 400 s, perché con 3 worker in parallelo la suite rallenta.
  - Le copie non hanno `.git`: per questo 4 test di igiene del repository risultano «skipped» per costruzione.
- **Esiti**:
  - KILLED: test falliti; il JSONL riporta il primo test fallito;
  - SURVIVED, TIMEOUT;
  - NOT_APPLICABLE: l'originale non compare esattamente una volta;
  - INFRA_ERROR: pytest non è arrivato a eseguire i test.
- **Ripresa**: se una campagna viene interrotta, `run_campaign.py` salta i mutanti già scritti nel JSONL e rifà
  le baseline.

## Riepilogo

| Commit | Mutanti | KILLED | SURVIVED | NOT_APPLICABLE | TIMEOUT | INFRA_ERROR | JSONL sha256 |
|---|---|---|---|---|---|---|---|
| `540a932` (codice finale; `9d521f0` cambia solo docs) | 241 | 241 | 0 | 0 | 0 | 0 | `19245ce1…db2e4a` |
| `90e7d45` (MCP-01p) | 226 | 226 | 0 | 0 | 0 | 0 | `b35711f8…a53847` |
| `40c34c4` (catalogo riallineato) | 216 | 215 | 0 | 0 | 1 | 0 | `fbea5bf7…14b4` |

Note:
- **`40c34c4`**: il mutante J09 era andato in TIMEOUT. Corretto con `fail_after(5)` nel test: nelle campagne
  successive J09 è KILLED in pochi secondi.
- **Mutanti aggiunti dopo `40c34c4`**:
  - B01–B14, P01–P03, R01–R10: scatola nera, MCP-01p;
  - R11–R25: forme reali di BB-1, MCP-01q.
- **Campagne interrotte**: quelle su `907423e`, `df044fc` e `3900d1c` sono state fermate a metà, perché ogni
  nuova consegna di Claude B cambiava il commit finale. Non sono riportate come esiti.
- **`540a932`, primo avvio**: la baseline di un worker è fallita su
  `tests/control_api/test_tokens.py::test_concurrent_processes_never_read_a_partial_token`, sul codice NON
  mutato. Quel worker non ha eseguito i suoi 80 mutanti; i log delle baseline sono in
  `mut_campaign_540a932_run1_baselines.txt`. Rieseguito a parte, il test passa 15 volte su 15 da solo e 12 su 12
  con la CPU satura: è un difetto di stabilità del test sotto carico, **osservato ma non spiegato**. La ripresa
  ha eseguito gli 80 mutanti mancanti con 3 baseline PASS. Il JSONL contiene un solo esito per mutante (241).

## Riproduzione

```bash
git worktree add --detach /tmp/w 540a932321b241503d423bf5617517da2d83cf0d
python3 docs/mutation/run_campaign.py /tmp/w /tmp/out.jsonl 3
python3 docs/mutation/campaign_report.py /tmp/out.jsonl 540a932 "Riproduzione"
```

### Campagna finale (commit di codice 540a932)

Commit `540a932321b241503d423bf5617517da2d83cf0d` · 241 mutanti · file `mut_campaign_540a932.jsonl` sha256 `19245ce11fdd8f3792fe201bc34b2e32c8e706b1cc967524fe0190fa89db2e4a`

| Esito | Numero |
|---|---|
| KILLED | 241 |
| SURVIVED | 0 |
| NOT_APPLICABLE | 0 |
| TIMEOUT | 0 |
| INFRA_ERROR | 0 |

<details><summary>Esito di ogni mutante (primo test fallito)</summary>

| Mutante | Esito | Primo test fallito | s |
|---|---|---|---|
| `A01` | KILLED | `tests/integration/test_auth_server.py::test_read_principal_calling_write_tool_is_forbidden_with_zero_upstream` | 7.9 |
| `A02` | KILLED | `tests/unit/test_auth.py::test_full_principal_by_tool_matrix[cancel_order-read]` | 1.5 |
| `A03` | KILLED | `tests/unit/test_auth.py::test_missing_principal_fails_closed` | 1.8 |
| `A04` | KILLED | `tests/unit/test_auth.py::test_principal_tampered_after_construction_fails_closed` | 1.9 |
| `A05` | KILLED | `tests/unit/test_auth.py::test_owner_only_operations` | 1.7 |
| `A06` | KILLED | `tests/unit/test_auth.py::test_owner_only_operations` | 1.5 |
| `A07` | KILLED | `tests/unit/test_auth.py::test_read_routes_need_read_and_commands_never_need_read` | 1.7 |
| `A08` | KILLED | `tests/integration/test_auth_server.py::test_registration_without_or_with_wrong_scope_is_refused` | 7.4 |
| `A09` | KILLED | `tests/integration/test_auth_server.py::test_registration_without_or_with_wrong_scope_is_refused` | 7.9 |
| `A10` | KILLED | `tests/integration/test_auth_server.py::test_forbidden_takes_precedence_over_input_validation` | 7.2 |
| `A11` | KILLED | `tests/unit/test_auth.py::test_principal_rejects_forged_or_malformed_scopes[bad_scopes1]` | 2.1 |
| `A12` | KILLED | `tests/unit/test_auth.py::test_parse_principal_rejects_malformed[raw13]` | 2.0 |
| `A13` | KILLED | `tests/unit/test_auth.py::test_local_stdio_principal_is_read_only` | 1.8 |
| `A14` | KILLED | `tests/unit/test_auth.py::test_principal_rejects_forged_or_malformed_scopes[bad_scopes0]` | 1.9 |
| `A15` | KILLED | `tests/unit/test_auth.py::test_owner_only_operations` | 1.8 |
| `B01` | KILLED | `tests/integration/test_blackbox_tools.py::test_unrecordable_request_is_an_unavailable_upstream_never_data` | 9.9 |
| `B02` | KILLED | `tests/control_api/test_server.py::test_invalid_configuration_refused` | 70.4 |
| `B03` | KILLED | `tests/control_api/test_blackbox_query.py::test_rejections_carry_a_fixed_code_never_the_input[foo=1-QUERY_PARAM]` | 51.9 |
| `B04` | KILLED | `tests/control_api/test_blackbox_query.py::test_rejections_carry_a_fixed_code_never_the_input[limit=1&limit=2-QUERY_PARAM_REPEATED]` | 49.0 |
| `B05` | KILLED | `tests/control_api/test_blackbox_query.py::test_rejections_carry_a_fixed_code_never_the_input[since=2026-01-01T00:00:00Z&until=2026-03-01T00:00:00Z-QUERY_RANGE]` | 51.3 |
| `B06` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_owner_question_reconstructed_from_recorded_events_only` | 48.2 |
| `B07` | KILLED | `tests/unit/test_blackbox_models.py::test_events_rejected[body0]` | 1.7 |
| `B08` | KILLED | `tests/unit/test_blackbox_models.py::test_events_rejected[body2]` | 1.9 |
| `B09` | KILLED | `tests/integration/test_blackbox_tools.py::test_http_adapter_never_sends_an_unvalidated_query[query0]` | 10.7 |
| `B10` | KILLED | `tests/integration/test_blackbox_tools.py::test_unrecordable_request_is_an_unavailable_upstream_never_data` | 9.5 |
| `B11` | KILLED | `tests/unit/test_blackbox_models.py::test_event_detail_rejected[body2]` | 1.9 |
| `B12` | KILLED | `tests/integration/test_blackbox_tools.py::test_a_core_that_ignores_the_cursor_is_not_trusted` | 9.9 |
| `B13` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_every_mcp_read_is_recorded_once_with_its_count` | 48.4 |
| `B14` | KILLED | `tests/integration/test_blackbox_tools.py::test_unrecordable_request_is_an_unavailable_upstream_never_data` | 10.3 |
| `C01` | KILLED | `tests/integration/test_diagnostics_tools.py::test_float_amount_from_core_is_stopped_by_the_server` | 14.2 |
| `C02` | KILLED | `tests/integration/test_blackbox_tools.py::test_real_control_api_round_trip_records_the_mcp_request` | 10.1 |
| `C03` | KILLED | `tests/integration/test_http_adapter.py::test_control_api_down_then_restarted_recovers_with_new_handshake` | 25.9 |
| `C04` | KILLED | `tests/control_api/test_server.py::test_wrong_host[localhost]` | 62.7 |
| `C05` | KILLED | `tests/control_api/test_tokens.py::test_during_rotation_both_tokens_accepted_then_only_new` | 71.0 |
| `C06` | KILLED | `tests/integration/test_http_adapter.py::test_rotation_is_recovered_with_one_reload` | 24.8 |
| `C07` | KILLED | `tests/control_api/test_server.py::test_almost_equal_tokens_are_rejected` | 73.2 |
| `C08` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_status_rejected_by_both_sides[9]` | 4.1 |
| `C09` | KILLED | `tests/control_api/test_schema_check.py::test_unknown_keyword_is_an_error_not_ignored` | 59.4 |
| `C10` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_reconciliation_rejected_by_both_sides[1]` | 4.2 |
| `C11` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_status_rejected_by_both_sides[13]` | 4.2 |
| `F01` | KILLED | `tests/unit/test_contract_descriptor.py::test_cross_field_rules_are_enforced_by_the_mcp[account-parse_account-override0]` | 4.0 |
| `F02` | KILLED | `tests/unit/test_contract_descriptor.py::test_cross_field_rules_are_enforced_by_the_mcp[account-parse_account-override2]` | 4.3 |
| `F03` | KILLED | `tests/unit/test_contract_descriptor.py::test_cross_field_rules_are_enforced_by_the_mcp[account-parse_account-override3]` | 4.2 |
| `F04` | KILLED | `tests/unit/test_contract_descriptor.py::test_cross_field_rules_are_enforced_by_the_mcp[exposure-parse_exposure-override4]` | 4.5 |
| `F05` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.0 |
| `F06` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.1 |
| `F07` | KILLED | `tests/integration/test_finance_tools.py::test_simulated_answers_are_marked_simulated[get_account]` | 16.4 |
| `F08` | KILLED | `tests/control_api/test_server.py::test_approved_but_unserved_reads_are_typed_not_implemented[/v1/events]` | 64.4 |
| `F09` | KILLED | `tests/control_api/test_server.py::test_unknown_paths[/v1/operations/.]` | 61.9 |
| `F10` | KILLED | `tests/integration/test_finance_tools.py::test_not_implemented_from_the_core_is_typed_and_not_retried` | 25.7 |
| `F11` | KILLED | `tests/integration/test_finance_tools.py::test_not_implemented_from_the_core_is_typed_and_not_retried` | 23.5 |
| `F12` | KILLED | `tests/control_api/test_server.py::test_invalid_configuration_refused` | 66.9 |
| `F13` | KILLED | `tests/unit/test_cli.py::test_contract_info` | 2.5 |
| `F14` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.0 |
| `G01` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.1 |
| `G02` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.0 |
| `G03` | KILLED | `tests/unit/test_contract_descriptor.py::test_13_cross_field_rules_are_enforced_by_the_mcp[status-parse_status-body0]` | 4.7 |
| `G04` | KILLED | `tests/unit/test_contract_descriptor.py::test_valid_status_accepted_by_both_sides[body0]` | 4.3 |
| `G05` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.1 |
| `G06` | KILLED | `tests/unit/test_contract_descriptor.py::test_13_cross_field_rules_are_enforced_by_the_mcp[positions-parse_positions-body2]` | 4.4 |
| `G07` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_positions_rejected_by_both_sides[4]` | 4.3 |
| `G08` | KILLED | `tests/unit/test_diagnostics_models.py::test_ready_engine_with_failing_component_is_rejected` | 5.5 |
| `G09` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.3 |
| `G10` | KILLED | `tests/integration/test_diagnostics_tools.py::test_positions_keep_decimal_strings_end_to_end` | 11.9 |
| `G11` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_13_status_rejected_by_both_sides[8]` | 4.2 |
| `H01` | KILLED | `tests/integration/test_http_adapter.py::test_protocol_violations_fail_closed[_redirect-UPSTREAM_INVALID_RESPONSE:HTTP_302]` | 27.9 |
| `H02` | KILLED | `tests/integration/test_http_adapter.py::test_protocol_violations_fail_closed[_wrong_type-UPSTREAM_INVALID_RESPONSE:CONTENT_TYPE]` | 28.1 |
| `H03` | KILLED | `tests/integration/test_http_adapter.py::test_wrong_token_is_unauthorized_and_not_retryable` | 25.7 |
| `H04` | KILLED | `tests/integration/test_http_adapter.py::test_rotation_is_recovered_with_one_reload` | 25.8 |
| `H05` | KILLED | `tests/integration/test_http_adapter.py::test_control_api_down_then_restarted_recovers_with_new_handshake` | 26.4 |
| `H06` | KILLED | `tests/integration/test_http_adapter.py::test_adapter_never_reads_more_than_the_limit` | 31.5 |
| `H07` | KILLED | `tests/integration/test_blackbox_tools.py::test_real_control_api_round_trip_records_the_mcp_request` | 9.9 |
| `H08` | KILLED | `tests/unit/test_cli.py::test_http_adapter_token_file_unsafe_is_refused_without_leaking` | 2.1 |
| `H09` | KILLED | `tests/unit/test_token_file.py::test_wrong_owner_rejected` | 8.1 |
| `H10` | KILLED | `tests/unit/test_token_file.py::test_symlink_rejected` | 7.6 |
| `H11` | KILLED | `tests/unit/test_token_file.py::test_writable_directory_rejected[511]` | 7.0 |
| `H12` | KILLED | `tests/unit/test_token_file.py::test_altered_content_rejected[short]` | 7.8 |
| `H13` | KILLED | `tests/unit/test_cli.py::test_http_adapter_misconfiguration_never_falls_back[args0-HTTP_ADAPTER_REQUIRES_PORT_AND_TOKEN_FILE]` | 2.0 |
| `H14` | KILLED | `tests/integration/test_http_adapter.py::test_token_file_made_readable_by_others_fails_closed` | 24.7 |
| `H15` | KILLED | `tests/integration/test_http_adapter.py::test_protocol_violations_fail_closed[_redirect-UPSTREAM_INVALID_RESPONSE:HTTP_302]` | 28.0 |
| `J01` | KILLED | `tests/unit/test_journal.py::test_duplicate_returns_same_operation_without_upstream_call` | 6.3 |
| `J02` | KILLED | `tests/unit/test_journal.py::test_fsync_failure_no_mutation` | 7.4 |
| `J03` | KILLED | `tests/unit/test_journal.py::test_exclusive_lock_second_opener_cannot_write` | 6.4 |
| `J04` | KILLED | `tests/unit/test_journal.py::test_failure_after_send_is_ambiguous_and_never_retried[bad_ack]` | 6.7 |
| `J05` | KILLED | `tests/unit/test_journal.py::test_crash_after_send_is_ambiguous_no_replay` | 6.7 |
| `J06` | KILLED | `tests/unit/test_journal.py::test_checksum_detects_structurally_valid_tampering` | 6.5 |
| `J07` | KILLED | `tests/unit/test_journal.py::test_corrupt_journal_fails_closed_reads_allowed[truncate]` | 6.3 |
| `J08` | KILLED | `tests/unit/test_journal.py::test_replaced_file_detected` | 6.6 |
| `J09` | KILLED | `tests/unit/test_journal.py::test_failure_after_send_is_ambiguous_and_never_retried[timeout]` | 11.9 |
| `J10` | KILLED | `tests/unit/test_journal.py::test_crash_after_send_is_ambiguous_no_replay` | 6.5 |
| `J11` | KILLED | `tests/unit/test_journal.py::test_duplicate_survives_restart` | 6.4 |
| `J12` | KILLED | `tests/unit/test_journal.py::test_new_entry_has_request_operation_correlation` | 6.2 |
| `J13` | KILLED | `tests/unit/test_journal.py::test_read_retry_attempts_bounded` | 6.5 |
| `K01` | KILLED | `tests/unit/test_config_models.py::test_setting_rules[max_daily_loss-overrides1]` | 4.1 |
| `K02` | KILLED | `tests/unit/test_config_models.py::test_structure_is_closed[missing-key]` | 4.0 |
| `K03` | KILLED | `tests/unit/test_config_models.py::test_setting_rules[table_count-overrides0]` | 4.1 |
| `K04` | KILLED | `tests/unit/test_config_models.py::test_setting_rules[commission_pct-overrides4]` | 4.0 |
| `K05` | KILLED | `tests/unit/test_config_models.py::test_sensitive_names_never_accepted_in_unlisted[betfair_app_key]` | 4.1 |
| `K06` | KILLED | `tests/unit/test_config_models.py::test_unlisted_rules[unlisted1]` | 4.1 |
| `K07` | KILLED | `tests/unit/test_config_models.py::test_unavailable_settings` | 3.9 |
| `K08` | KILLED | `tests/unit/test_config_models.py::test_unlisted_rules[unlisted0]` | 4.2 |
| `L01` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides0]` | 7.6 |
| `L02` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides2]` | 7.2 |
| `L03` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides4]` | 7.6 |
| `L04` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides5]` | 7.3 |
| `L05` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides6]` | 7.1 |
| `L06` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_snapshot_state_rules[section0]` | 7.9 |
| `L07` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides7]` | 7.6 |
| `L08` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides8]` | 7.4 |
| `M01` | KILLED | `tests/unit/test_handshake.py::test_pure_check_rejects[overrides0-VERSION_UNSUPPORTED]` | 6.1 |
| `M02` | KILLED | `tests/unit/test_handshake.py::test_pure_check_rejects[overrides3-SCHEMA_HASH_UNKNOWN]` | 5.9 |
| `M03` | KILLED | `tests/unit/test_handshake.py::test_pure_check_rejects[overrides5-CAPABILITY_NOT_APPROVED]` | 6.4 |
| `M04` | KILLED | `tests/unit/test_handshake.py::test_pure_check_rejects[overrides4-CAPABILITY_MISSING:GET` | 6.0 |
| `M05` | KILLED | `tests/unit/test_handshake.py::test_failing_scenarios[Scenario.INCOMPATIBLE_MAJOR-HandshakeStatus.INCOMPATIBLE-ErrorCode.CONTRACT_INCOMPATIBLE]` | 6.3 |
| `M06` | KILLED | `tests/unit/test_handshake.py::test_reconnect_forces_new_handshake` | 6.0 |
| `M07` | KILLED | `tests/unit/test_handshake.py::test_failing_scenarios[Scenario.TIMEOUT-HandshakeStatus.UNAVAILABLE-ErrorCode.UPSTREAM_TIMEOUT]` | 11.0 |
| `M08` | KILLED | `tests/unit/test_handshake.py::test_failing_scenarios[Scenario.INCOMPATIBLE_MAJOR-HandshakeStatus.INCOMPATIBLE-ErrorCode.CONTRACT_INCOMPATIBLE]` | 6.2 |
| `M09` | KILLED | `tests/unit/test_config_models.py::test_structure_is_closed[extra-field]` | 4.0 |
| `M10` | KILLED | `tests/unit/test_config_models.py::test_setting_rules[table_count-overrides7]` | 4.3 |
| `M11` | KILLED | `tests/unit/test_models_meta.py::test_strict_base_rejects_coercion_and_non_finite_numbers` | 6.7 |
| `M12` | KILLED | `tests/unit/test_models_meta.py::test_invalid_meta_is_rejected[{"contract_version":` | 7.0 |
| `M13` | KILLED | `tests/unit/test_models_meta.py::test_invalid_meta_is_rejected[{"contract_version":"1.0.0","contract_version":"1.0.0","capabilities":["GET` | 7.2 |
| `M14` | KILLED | `tests/unit/test_models_meta.py::test_invalid_meta_is_rejected[{"contract_version":` | 6.6 |
| `M15` | KILLED | `tests/unit/test_models_meta.py::test_oversized_body_is_rejected_before_parsing` | 7.4 |
| `M16` | KILLED | `tests/unit/test_registry_guard.py::test_command_tools_are_refused_while_exposure_blocked[place_order-POST` | 6.9 |
| `M17` | KILLED | `tests/unit/test_registry_guard.py::test_command_tools_are_refused_while_exposure_blocked[place_order-POST` | 7.0 |
| `M18` | KILLED | `tests/unit/test_registry_guard.py::test_forbidden_name_is_refused_even_if_catalog_were_extended` | 7.2 |
| `M19` | KILLED | `tests/unit/test_registry_guard.py::test_name_route_mismatch_is_refused` | 7.0 |
| `M20` | KILLED | `tests/integration/test_auth_server.py::test_forbidden_takes_precedence_over_input_validation` | 7.6 |
| `M21` | KILLED | `1 error in 0.76s` | 1.3 |
| `M22` | KILLED | `tests/unit/test_config_and_audit.py::test_non_loopback_or_malformed_urls_are_rejected[http://0.0.0.0:8770-CONFIG_HOST_NOT_LOOPBACK]` | 3.9 |
| `M23` | KILLED | `tests/unit/test_config_and_audit.py::test_audit_keeps_only_allowlisted_fields` | 4.0 |
| `M24` | KILLED | `tests/integration/test_auth_server.py::test_altered_tool_names_are_unknown_and_never_reach_upstream[PLACE_ORDER]` | 7.2 |
| `M25` | KILLED | `tests/integration/test_review_findings.py::test_r2_cancelled_handshake_does_not_keep_previous_verdict` | 36.1 |
| `M26` | KILLED | `tests/unit/test_handshake.py::test_pure_check_rejects[overrides5-CAPABILITY_NOT_APPROVED]` | 6.0 |
| `M27` | KILLED | `tests/unit/test_config_and_audit.py::test_serve_logging_keeps_only_audit_on_stderr` | 4.1 |
| `M28` | KILLED | `tests/integration/test_review_findings.py::test_r9_annotations_follow_route_kind` | 36.4 |
| `M29` | KILLED | `tests/unit/test_handshake.py::test_explicit_handshake_cannot_reopen_an_incompatible_epoch` | 7.1 |
| `M30` | KILLED | `tests/unit/test_cli.py::test_tracker_records_and_delegates_the_first_sigint` | 2.2 |
| `M31` | KILLED | `tests/unit/test_cli.py::test_tracker_leaves_ignored_or_default_disposition_alone` | 2.2 |
| `M32` | KILLED | `tests/unit/test_cli.py::test_asyncio_runner_keeps_its_own_sigint_handling` | 2.0 |
| `M33` | KILLED | `tests/unit/test_cli.py::test_sigint_watchdog_exits_when_the_runner_never_returns` | 7.1 |
| `M34` | KILLED | `tests/unit/test_cli.py::test_main_disarms_the_watchdog_on_every_exit_path` | 3.6 |
| `M35` | KILLED | `tests/unit/test_cli.py::test_forced_exit_writes_the_interrupted_audit_and_exits_130` | 3.7 |
| `M36` | KILLED | `tests/unit/test_cli.py::test_sigint_handler_starts_no_thread` | 3.5 |
| `M37` | KILLED | `tests/unit/test_cli.py::test_every_interrupted_exit_goes_through_the_forced_exit_once[_interrupted_with_exception]` | 3.3 |
| `M38` | KILLED | `tests/unit/test_cli.py::test_stop_interrupted_runs_once_even_with_the_watchdog` | 4.3 |
| `M39` | KILLED | `tests/unit/test_cli.py::test_stop_holds_the_lock_until_the_exit_completes` | 3.7 |
| `M40` | KILLED | `tests/unit/test_cli.py::test_stop_holds_the_lock_until_the_exit_completes` | 3.9 |
| `M41` | KILLED | `tests/unit/test_cli.py::test_interrupt_grace_is_short` | 4.1 |
| `M42` | KILLED | `tests/unit/test_cli.py::test_stop_ignores_sigint_on_the_main_thread_before_exiting` | 3.9 |
| `M43` | KILLED | `tests/unit/test_cli.py::test_sigint_watchdog_exits_when_the_runner_never_returns` | 6.9 |
| `M44` | KILLED | `tests/unit/test_cli.py::test_second_sigint_ignores_further_signals_before_delegating` | 4.6 |
| `M45` | KILLED | `tests/unit/test_cli.py::test_after_the_loop_sigint_is_recorded_without_raising` | 4.1 |
| `M46` | KILLED | `tests/unit/test_cli.py::test_main_ignores_late_sigint_before_deciding_the_exit[ok]` | 3.8 |
| `M47` | KILLED | `tests/unit/test_cli.py::test_main_ignores_late_sigint_before_deciding_the_exit[transport]` | 4.2 |
| `M48` | KILLED | `tests/unit/test_cli.py::test_server_start_is_written_only_once_sigint_handling_is_active` | 4.1 |
| `N01` | KILLED | `tests/integration/test_market_tools.py::test_real_control_api_book_round_trip_and_id_echo` | 31.7 |
| `N02` | KILLED | `tests/unit/test_market_models.py::test_book_rejected[body3]` | 6.9 |
| `N03` | KILLED | `tests/unit/test_market_models.py::test_book_rejected[body0]` | 6.8 |
| `N04` | KILLED | `tests/unit/test_market_models.py::test_markets_rejected[body0]` | 7.0 |
| `N05` | KILLED | `tests/integration/test_market_tools.py::test_http_adapter_never_builds_a_path_from_an_unvalidated_id[../etc]` | 32.6 |
| `N06` | KILLED | `tests/control_api/test_market_routes.py::test_book_route_rejects_any_other_shape_without_calling_the_core[/v1/markets/../book]` | 54.6 |
| `O01` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.1 |
| `O02` | KILLED | `tests/unit/test_orders_models.py::test_unknown_core_status_can_only_be_reported_as_unknown[MATCHED]` | 7.2 |
| `O03` | KILLED | `tests/unit/test_orders_models.py::test_partial_split_requires_explicit_sizes` | 7.5 |
| `O04` | KILLED | `tests/unit/test_contract_descriptor.py::test_14_cross_field_rules_are_enforced_by_the_mcp[1]` | 4.2 |
| `O05` | KILLED | `tests/unit/test_orders_models.py::test_broker_view_needs_a_bet_id` | 7.1 |
| `O06` | KILLED | `tests/unit/test_orders_models.py::test_duplicate_local_ids_are_rejected` | 7.4 |
| `O07` | KILLED | `tests/unit/test_orders_models.py::test_incoherent_snapshot_is_rejected[snapshot1]` | 6.4 |
| `O08` | KILLED | `tests/unit/test_orders_models.py::test_incoherent_snapshot_is_rejected[snapshot3]` | 7.3 |
| `O09` | KILLED | `tests/integration/test_orders_tools.py::test_orders_are_listed_with_ambiguous_kept_ambiguous` | 32.0 |
| `O10` | KILLED | `tests/unit/test_orders_models.py::test_order_violations_are_rejected[override7]` | 6.3 |
| `O11` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.5 |
| `O12` | KILLED | `tests/unit/test_compat_models.py::test_unconfirmed_with_any_amount_is_rejected[AMBIGUOUS-AMBIGUOUS-size_matched]` | 4.3 |
| `P01` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_snapshot_state_rules[section1]` | 8.2 |
| `P02` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_snapshot_state_rules[section2]` | 7.8 |
| `P03` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.4 |
| `R01` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_engine_record_mapping` | 47.3 |
| `R02` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_owner_question_reconstructed_from_recorded_events_only` | 44.4 |
| `R03` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_engine_record_mapping` | 47.5 |
| `R04` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_a_truthy_non_true_answer_is_not_an_accepted_record` | 51.2 |
| `R05` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_owner_question_reconstructed_from_recorded_events_only` | 45.5 |
| `R06` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_unavailable_register_gives_no_data_but_status_still_answers` | 50.8 |
| `R07` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_unmappable_records_are_refused_never_adjusted[over4]` | 46.4 |
| `R08` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_values_are_flattened_exactly_and_unrepresentable_ones_counted` | 45.2 |
| `R09` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_engine_record_mapping` | 48.2 |
| `R10` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_unmappable_records_are_refused_never_adjusted[over5]` | 47.8 |
| `R11` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_new_bb1_filters_reach_the_reader_in_the_engine_text_form` | 46.3 |
| `R12` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_time_gaps_from_bb1_are_shown_as_unrecorded_windows` | 48.7 |
| `R13` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_owner_question_reconstructed_from_recorded_events_only` | 46.9 |
| `R14` | KILLED | `tests/control_api/test_blackbox_query.py::test_rejections_carry_a_fixed_code_never_the_input[order_id=ord_0123-QUERY_VALUE]` | 48.1 |
| `R15` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_status_never_claims_what_bb1_does_not_report` | 51.1 |
| `R16` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_get_in_a_shape_other_than_bb1_is_an_error[shape1]` | 51.0 |
| `R17` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_engine_record_mapping` | 45.4 |
| `R18` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_engine_not_recorded_never_hides_a_value[not_recorded0]` | 46.1 |
| `R19` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_a_bad_time_gap_is_an_error_never_hidden[bad0]` | 48.8 |
| `R20` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_only_a_literal_ok_and_not_degraded_register_is_available[True-True]` | 48.2 |
| `R21` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_sessions_tell_a_crash_from_the_running_session` | 51.5 |
| `R22` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_sessions_tell_a_crash_from_the_running_session` | 53.1 |
| `R23` | KILLED | `tests/contract/test_blackbox_bb1_fixture.py::test_every_real_record_maps_none_becomes_corrupt` | 48.3 |
| `R24` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_unmappable_records_are_refused_never_adjusted[over14]` | 48.1 |
| `R25` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_unmappable_records_are_refused_never_adjusted[over17]` | 51.2 |
| `S01` | KILLED | `tests/integration/test_blackbox_tools.py::test_bad_blackbox_bodies_are_rejected[StatusScenario.WRONG_SOURCE]` | 10.1 |
| `S02` | KILLED | `tests/integration/test_diagnostics_tools.py::test_invalid_positions_fail_closed[StatusScenario.STALE-UPSTREAM_INVALID_RESPONSE:STALE_SNAPSHOT]` | 12.7 |
| `S03` | KILLED | `tests/integration/test_diagnostics_tools.py::test_core_without_positions_capability_is_never_read` | 12.7 |
| `S04` | KILLED | `tests/unit/test_blackbox_models.py::test_events_rejected[body23]` | 1.9 |
| `S05` | KILLED | `tests/unit/test_status_models.py::test_ready_requires_level_ready_and_no_blockers` | 7.6 |
| `S06` | KILLED | `tests/unit/test_status_models.py::test_ready_requires_level_ready_and_no_blockers` | 7.7 |
| `S07` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.1 |
| `S08` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.3 |
| `S09` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.5 |
| `S10` | KILLED | `tests/integration/test_finance_tools.py::test_timeout_is_bounded_and_retryable[get_account]` | 19.6 |
| `S11` | KILLED | `tests/unit/test_status_models.py::test_not_run_startup_has_no_reason` | 7.6 |
| `S12` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_status_rejected_by_both_sides[11]` | 4.3 |
| `S13` | KILLED | `tests/unit/test_blackbox_models.py::test_status_rejected[body7]` | 2.0 |
| `S14` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.3 |
| `T01` | KILLED | `tests/unit/test_contract_descriptor.py::test_15_cross_field_rules_are_enforced_by_the_mcp[exposure-parse_exposure-body0]` | 4.5 |
| `T02` | KILLED | `tests/unit/test_settlement_sltp_models.py::test_incoherent_sl_tp_is_rejected[sl_tp1]` | 7.4 |
| `T03` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.3 |
| `T04` | KILLED | `tests/unit/test_contract_descriptor.py::test_15_cross_field_rules_are_enforced_by_the_mcp[reconciliation_status-parse_reconciliation_status-body1]` | 4.7 |
| `T05` | KILLED | `tests/unit/test_settlement_sltp_models.py::test_incoherent_settlement_is_rejected[override3]` | 7.3 |
| `T06` | KILLED | `tests/unit/test_settlement_sltp_models.py::test_duplicate_checkpoint_stages_are_rejected` | 7.5 |
| `T07` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_15_rejected_by_both_sides[5]` | 4.4 |
| `X01` | KILLED | `tests/control_api/test_security_hardening.py::test_weak_or_malformed_tokens_are_refused[]` | 55.6 |
| `X02` | KILLED | `tests/control_api/test_security_hardening.py::test_concurrent_rotation_with_a_failed_write_never_revives_the_old_token` | 56.1 |
| `X03` | KILLED | `tests/control_api/test_security_hardening.py::test_idle_connections_are_bounded_and_expire` | 57.4 |
| `X04` | KILLED | `tests/control_api/test_security_hardening.py::test_idle_connections_are_bounded_and_expire` | 62.2 |
| `X05` | KILLED | `tests/control_api/test_security_hardening.py::test_protocol_errors_are_fixed_json_without_echo[FOO<script>x</script>` | 58.0 |
| `X06` | KILLED | `tests/control_api/test_security_hardening.py::test_idle_connections_are_bounded_and_expire` | 57.7 |
| `Y01` | KILLED | `tests/unit/test_trailing_models.py::test_incoherent_trailing_is_rejected_by_the_mcp[tr0]` | 7.6 |
| `Y02` | KILLED | `tests/unit/test_trailing_models.py::test_incoherent_trailing_is_rejected_by_the_mcp[tr2]` | 7.7 |
| `Y03` | KILLED | `tests/unit/test_trailing_models.py::test_incoherent_trailing_is_rejected_by_the_mcp[tr4]` | 7.3 |
| `Y04` | KILLED | `tests/unit/test_trailing_models.py::test_incoherent_trailing_is_rejected_by_the_mcp[tr5]` | 8.0 |
| `Y05` | KILLED | `tests/unit/test_trailing_models.py::test_incoherent_trailing_is_rejected_by_the_mcp[tr6]` | 7.6 |
| `Y06` | KILLED | `tests/unit/test_config_models.py::test_invalid_persisted_f18` | 4.0 |
| `Y07` | KILLED | `tests/unit/test_resolve_git_sha.py::test_worktree_on_a_branch` | 7.7 |
| `Z01` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.3 |
| `Z02` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 3.9 |
| `Z03` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.4 |
| `Z04` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.0 |

</details>

### Campagna su 90e7d45 (MCP-01p)

Commit `90e7d45` · 226 mutanti · file `mut_campaign_90e7d45.jsonl` sha256 `b35711f8cdae1418ab31d5e99816e0b3610d6fbf1b0eebb57b4412b429a53847`

| Esito | Numero |
|---|---|
| KILLED | 226 |
| SURVIVED | 0 |
| NOT_APPLICABLE | 0 |
| TIMEOUT | 0 |
| INFRA_ERROR | 0 |

<details><summary>Esito di ogni mutante (primo test fallito)</summary>

| Mutante | Esito | Primo test fallito | s |
|---|---|---|---|
| `A01` | KILLED | `tests/integration/test_auth_server.py::test_read_principal_calling_write_tool_is_forbidden_with_zero_upstream` | 7.6 |
| `A02` | KILLED | `tests/unit/test_auth.py::test_full_principal_by_tool_matrix[cancel_order-read]` | 1.9 |
| `A03` | KILLED | `tests/unit/test_auth.py::test_missing_principal_fails_closed` | 1.9 |
| `A04` | KILLED | `tests/unit/test_auth.py::test_principal_tampered_after_construction_fails_closed` | 1.7 |
| `A05` | KILLED | `tests/unit/test_auth.py::test_owner_only_operations` | 1.6 |
| `A06` | KILLED | `tests/unit/test_auth.py::test_owner_only_operations` | 1.6 |
| `A07` | KILLED | `tests/unit/test_auth.py::test_read_routes_need_read_and_commands_never_need_read` | 1.6 |
| `A08` | KILLED | `tests/integration/test_auth_server.py::test_registration_without_or_with_wrong_scope_is_refused` | 7.6 |
| `A09` | KILLED | `tests/integration/test_auth_server.py::test_registration_without_or_with_wrong_scope_is_refused` | 7.8 |
| `A10` | KILLED | `tests/integration/test_auth_server.py::test_forbidden_takes_precedence_over_input_validation` | 7.8 |
| `A11` | KILLED | `tests/unit/test_auth.py::test_principal_rejects_forged_or_malformed_scopes[bad_scopes1]` | 2.6 |
| `A12` | KILLED | `tests/unit/test_auth.py::test_parse_principal_rejects_malformed[raw13]` | 1.8 |
| `A13` | KILLED | `tests/unit/test_auth.py::test_local_stdio_principal_is_read_only` | 1.8 |
| `A14` | KILLED | `tests/unit/test_auth.py::test_principal_rejects_forged_or_malformed_scopes[bad_scopes0]` | 1.9 |
| `A15` | KILLED | `tests/unit/test_auth.py::test_owner_only_operations` | 1.6 |
| `B01` | KILLED | `tests/integration/test_blackbox_tools.py::test_unrecordable_request_is_an_unavailable_upstream_never_data` | 9.7 |
| `B02` | KILLED | `tests/control_api/test_server.py::test_invalid_configuration_refused` | 69.6 |
| `B03` | KILLED | `tests/control_api/test_blackbox_query.py::test_rejections_carry_a_fixed_code_never_the_input[foo=1-QUERY_PARAM]` | 47.5 |
| `B04` | KILLED | `tests/control_api/test_blackbox_query.py::test_rejections_carry_a_fixed_code_never_the_input[limit=1&limit=2-QUERY_PARAM_REPEATED]` | 48.2 |
| `B05` | KILLED | `tests/control_api/test_blackbox_query.py::test_rejections_carry_a_fixed_code_never_the_input[since=2026-01-01T00:00:00Z&until=2026-03-01T00:00:00Z-QUERY_RANGE]` | 48.1 |
| `B06` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_owner_question_reconstructed_from_recorded_events_only` | 47.0 |
| `B07` | KILLED | `tests/unit/test_blackbox_models.py::test_events_rejected[body0]` | 1.8 |
| `B08` | KILLED | `tests/unit/test_blackbox_models.py::test_events_rejected[body2]` | 2.0 |
| `B09` | KILLED | `tests/integration/test_blackbox_tools.py::test_http_adapter_never_sends_an_unvalidated_query[query0]` | 10.2 |
| `B10` | KILLED | `tests/integration/test_blackbox_tools.py::test_unrecordable_request_is_an_unavailable_upstream_never_data` | 9.5 |
| `B11` | KILLED | `tests/unit/test_blackbox_models.py::test_event_detail_rejected[body2]` | 2.0 |
| `B12` | KILLED | `tests/integration/test_blackbox_tools.py::test_a_core_that_ignores_the_cursor_is_not_trusted` | 9.6 |
| `B13` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_every_mcp_read_is_recorded_once_with_its_count` | 47.4 |
| `B14` | KILLED | `tests/integration/test_blackbox_tools.py::test_unrecordable_request_is_an_unavailable_upstream_never_data` | 9.7 |
| `C01` | KILLED | `tests/integration/test_diagnostics_tools.py::test_float_amount_from_core_is_stopped_by_the_server` | 15.4 |
| `C02` | KILLED | `tests/integration/test_blackbox_tools.py::test_real_control_api_round_trip_records_the_mcp_request` | 9.8 |
| `C03` | KILLED | `tests/integration/test_http_adapter.py::test_control_api_down_then_restarted_recovers_with_new_handshake` | 27.0 |
| `C04` | KILLED | `tests/control_api/test_server.py::test_wrong_host[localhost]` | 58.9 |
| `C05` | KILLED | `tests/control_api/test_tokens.py::test_during_rotation_both_tokens_accepted_then_only_new` | 68.9 |
| `C06` | KILLED | `tests/integration/test_http_adapter.py::test_rotation_is_recovered_with_one_reload` | 26.3 |
| `C07` | KILLED | `tests/control_api/test_server.py::test_almost_equal_tokens_are_rejected` | 70.0 |
| `C08` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_status_rejected_by_both_sides[9]` | 4.8 |
| `C09` | KILLED | `tests/control_api/test_schema_check.py::test_unknown_keyword_is_an_error_not_ignored` | 58.3 |
| `C10` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_reconciliation_rejected_by_both_sides[1]` | 4.5 |
| `C11` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_status_rejected_by_both_sides[13]` | 4.2 |
| `F01` | KILLED | `tests/unit/test_contract_descriptor.py::test_cross_field_rules_are_enforced_by_the_mcp[account-parse_account-override0]` | 4.2 |
| `F02` | KILLED | `tests/unit/test_contract_descriptor.py::test_cross_field_rules_are_enforced_by_the_mcp[account-parse_account-override2]` | 4.3 |
| `F03` | KILLED | `tests/unit/test_contract_descriptor.py::test_cross_field_rules_are_enforced_by_the_mcp[account-parse_account-override3]` | 4.3 |
| `F04` | KILLED | `tests/unit/test_contract_descriptor.py::test_cross_field_rules_are_enforced_by_the_mcp[exposure-parse_exposure-override4]` | 4.4 |
| `F05` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.3 |
| `F06` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.3 |
| `F07` | KILLED | `tests/integration/test_finance_tools.py::test_simulated_answers_are_marked_simulated[get_account]` | 13.8 |
| `F08` | KILLED | `tests/control_api/test_server.py::test_approved_but_unserved_reads_are_typed_not_implemented[/v1/events]` | 61.9 |
| `F09` | KILLED | `tests/control_api/test_server.py::test_unknown_paths[/v1/operations/.]` | 60.2 |
| `F10` | KILLED | `tests/integration/test_finance_tools.py::test_not_implemented_from_the_core_is_typed_and_not_retried` | 22.9 |
| `F11` | KILLED | `tests/integration/test_finance_tools.py::test_not_implemented_from_the_core_is_typed_and_not_retried` | 22.7 |
| `F12` | KILLED | `tests/control_api/test_server.py::test_invalid_configuration_refused` | 64.8 |
| `F13` | KILLED | `tests/unit/test_cli.py::test_contract_info` | 1.8 |
| `F14` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.2 |
| `G01` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.2 |
| `G02` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.0 |
| `G03` | KILLED | `tests/unit/test_contract_descriptor.py::test_13_cross_field_rules_are_enforced_by_the_mcp[status-parse_status-body0]` | 4.2 |
| `G04` | KILLED | `tests/unit/test_contract_descriptor.py::test_valid_status_accepted_by_both_sides[body0]` | 4.2 |
| `G05` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.3 |
| `G06` | KILLED | `tests/unit/test_contract_descriptor.py::test_13_cross_field_rules_are_enforced_by_the_mcp[positions-parse_positions-body2]` | 4.3 |
| `G07` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_positions_rejected_by_both_sides[4]` | 4.2 |
| `G08` | KILLED | `tests/unit/test_diagnostics_models.py::test_ready_engine_with_failing_component_is_rejected` | 5.6 |
| `G09` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.0 |
| `G10` | KILLED | `tests/integration/test_diagnostics_tools.py::test_positions_keep_decimal_strings_end_to_end` | 12.0 |
| `G11` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_13_status_rejected_by_both_sides[8]` | 4.4 |
| `H01` | KILLED | `tests/integration/test_http_adapter.py::test_protocol_violations_fail_closed[_redirect-UPSTREAM_INVALID_RESPONSE:HTTP_302]` | 28.1 |
| `H02` | KILLED | `tests/integration/test_http_adapter.py::test_protocol_violations_fail_closed[_wrong_type-UPSTREAM_INVALID_RESPONSE:CONTENT_TYPE]` | 27.5 |
| `H03` | KILLED | `tests/integration/test_http_adapter.py::test_wrong_token_is_unauthorized_and_not_retryable` | 24.9 |
| `H04` | KILLED | `tests/integration/test_http_adapter.py::test_rotation_is_recovered_with_one_reload` | 26.1 |
| `H05` | KILLED | `tests/integration/test_http_adapter.py::test_control_api_down_then_restarted_recovers_with_new_handshake` | 25.3 |
| `H06` | KILLED | `tests/integration/test_http_adapter.py::test_adapter_never_reads_more_than_the_limit` | 31.1 |
| `H07` | KILLED | `tests/integration/test_blackbox_tools.py::test_real_control_api_round_trip_records_the_mcp_request` | 10.0 |
| `H08` | KILLED | `tests/unit/test_cli.py::test_http_adapter_token_file_unsafe_is_refused_without_leaking` | 2.2 |
| `H09` | KILLED | `tests/unit/test_token_file.py::test_wrong_owner_rejected` | 7.7 |
| `H10` | KILLED | `tests/unit/test_token_file.py::test_symlink_rejected` | 8.2 |
| `H11` | KILLED | `tests/unit/test_token_file.py::test_writable_directory_rejected[511]` | 8.0 |
| `H12` | KILLED | `tests/unit/test_token_file.py::test_altered_content_rejected[short]` | 8.2 |
| `H13` | KILLED | `tests/unit/test_cli.py::test_http_adapter_misconfiguration_never_falls_back[args0-HTTP_ADAPTER_REQUIRES_PORT_AND_TOKEN_FILE]` | 2.3 |
| `H14` | KILLED | `tests/integration/test_http_adapter.py::test_token_file_made_readable_by_others_fails_closed` | 26.1 |
| `H15` | KILLED | `tests/integration/test_http_adapter.py::test_protocol_violations_fail_closed[_redirect-UPSTREAM_INVALID_RESPONSE:HTTP_302]` | 27.9 |
| `J01` | KILLED | `tests/unit/test_journal.py::test_duplicate_returns_same_operation_without_upstream_call` | 6.6 |
| `J02` | KILLED | `tests/unit/test_journal.py::test_fsync_failure_no_mutation` | 6.9 |
| `J03` | KILLED | `tests/unit/test_journal.py::test_exclusive_lock_second_opener_cannot_write` | 6.8 |
| `J04` | KILLED | `tests/unit/test_journal.py::test_failure_after_send_is_ambiguous_and_never_retried[bad_ack]` | 6.7 |
| `J05` | KILLED | `tests/unit/test_journal.py::test_crash_after_send_is_ambiguous_no_replay` | 6.4 |
| `J06` | KILLED | `tests/unit/test_journal.py::test_checksum_detects_structurally_valid_tampering` | 7.1 |
| `J07` | KILLED | `tests/unit/test_journal.py::test_corrupt_journal_fails_closed_reads_allowed[truncate]` | 6.4 |
| `J08` | KILLED | `tests/unit/test_journal.py::test_replaced_file_detected` | 6.7 |
| `J09` | KILLED | `tests/unit/test_journal.py::test_failure_after_send_is_ambiguous_and_never_retried[timeout]` | 11.5 |
| `J10` | KILLED | `tests/unit/test_journal.py::test_crash_after_send_is_ambiguous_no_replay` | 6.6 |
| `J11` | KILLED | `tests/unit/test_journal.py::test_duplicate_survives_restart` | 6.4 |
| `J12` | KILLED | `tests/unit/test_journal.py::test_new_entry_has_request_operation_correlation` | 6.8 |
| `J13` | KILLED | `tests/unit/test_journal.py::test_read_retry_attempts_bounded` | 6.6 |
| `K01` | KILLED | `tests/unit/test_config_models.py::test_setting_rules[max_daily_loss-overrides1]` | 4.1 |
| `K02` | KILLED | `tests/unit/test_config_models.py::test_structure_is_closed[missing-key]` | 4.4 |
| `K03` | KILLED | `tests/unit/test_config_models.py::test_setting_rules[table_count-overrides0]` | 4.2 |
| `K04` | KILLED | `tests/unit/test_config_models.py::test_setting_rules[commission_pct-overrides4]` | 4.5 |
| `K05` | KILLED | `tests/unit/test_config_models.py::test_sensitive_names_never_accepted_in_unlisted[betfair_app_key]` | 4.6 |
| `K06` | KILLED | `tests/unit/test_config_models.py::test_unlisted_rules[unlisted1]` | 4.8 |
| `K07` | KILLED | `tests/unit/test_config_models.py::test_unavailable_settings` | 4.5 |
| `K08` | KILLED | `tests/unit/test_config_models.py::test_unlisted_rules[unlisted0]` | 4.4 |
| `L01` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides0]` | 7.6 |
| `L02` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides2]` | 7.6 |
| `L03` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides4]` | 7.7 |
| `L04` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides5]` | 7.4 |
| `L05` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides6]` | 7.2 |
| `L06` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_snapshot_state_rules[section0]` | 7.7 |
| `L07` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides7]` | 7.6 |
| `L08` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides8]` | 7.4 |
| `M01` | KILLED | `tests/unit/test_handshake.py::test_pure_check_rejects[overrides0-VERSION_UNSUPPORTED]` | 6.7 |
| `M02` | KILLED | `tests/unit/test_handshake.py::test_pure_check_rejects[overrides3-SCHEMA_HASH_UNKNOWN]` | 5.9 |
| `M03` | KILLED | `tests/unit/test_handshake.py::test_pure_check_rejects[overrides5-CAPABILITY_NOT_APPROVED]` | 6.1 |
| `M04` | KILLED | `tests/unit/test_handshake.py::test_pure_check_rejects[overrides4-CAPABILITY_MISSING:GET` | 6.4 |
| `M05` | KILLED | `tests/unit/test_handshake.py::test_failing_scenarios[Scenario.INCOMPATIBLE_MAJOR-HandshakeStatus.INCOMPATIBLE-ErrorCode.CONTRACT_INCOMPATIBLE]` | 6.3 |
| `M06` | KILLED | `tests/unit/test_handshake.py::test_reconnect_forces_new_handshake` | 6.2 |
| `M07` | KILLED | `tests/unit/test_handshake.py::test_failing_scenarios[Scenario.TIMEOUT-HandshakeStatus.UNAVAILABLE-ErrorCode.UPSTREAM_TIMEOUT]` | 11.5 |
| `M08` | KILLED | `tests/unit/test_handshake.py::test_failing_scenarios[Scenario.INCOMPATIBLE_MAJOR-HandshakeStatus.INCOMPATIBLE-ErrorCode.CONTRACT_INCOMPATIBLE]` | 5.8 |
| `M09` | KILLED | `tests/unit/test_config_models.py::test_structure_is_closed[extra-field]` | 4.3 |
| `M10` | KILLED | `tests/unit/test_config_models.py::test_setting_rules[table_count-overrides7]` | 4.3 |
| `M11` | KILLED | `tests/unit/test_models_meta.py::test_strict_base_rejects_coercion_and_non_finite_numbers` | 7.0 |
| `M12` | KILLED | `tests/unit/test_models_meta.py::test_invalid_meta_is_rejected[{"contract_version":` | 7.6 |
| `M13` | KILLED | `tests/unit/test_models_meta.py::test_invalid_meta_is_rejected[{"contract_version":"1.0.0","contract_version":"1.0.0","capabilities":["GET` | 7.0 |
| `M14` | KILLED | `tests/unit/test_models_meta.py::test_invalid_meta_is_rejected[{"contract_version":` | 7.4 |
| `M15` | KILLED | `tests/unit/test_models_meta.py::test_oversized_body_is_rejected_before_parsing` | 7.0 |
| `M16` | KILLED | `tests/unit/test_registry_guard.py::test_command_tools_are_refused_while_exposure_blocked[place_order-POST` | 7.4 |
| `M17` | KILLED | `tests/unit/test_registry_guard.py::test_command_tools_are_refused_while_exposure_blocked[place_order-POST` | 7.5 |
| `M18` | KILLED | `tests/unit/test_registry_guard.py::test_forbidden_name_is_refused_even_if_catalog_were_extended` | 7.4 |
| `M19` | KILLED | `tests/unit/test_registry_guard.py::test_name_route_mismatch_is_refused` | 7.4 |
| `M20` | KILLED | `tests/integration/test_auth_server.py::test_forbidden_takes_precedence_over_input_validation` | 8.1 |
| `M21` | KILLED | `1 error in 0.90s` | 1.5 |
| `M22` | KILLED | `tests/unit/test_config_and_audit.py::test_non_loopback_or_malformed_urls_are_rejected[http://0.0.0.0:8770-CONFIG_HOST_NOT_LOOPBACK]` | 4.1 |
| `M23` | KILLED | `tests/unit/test_config_and_audit.py::test_audit_keeps_only_allowlisted_fields` | 3.9 |
| `M24` | KILLED | `tests/integration/test_auth_server.py::test_altered_tool_names_are_unknown_and_never_reach_upstream[PLACE_ORDER]` | 8.2 |
| `M25` | KILLED | `tests/integration/test_review_findings.py::test_r2_cancelled_handshake_does_not_keep_previous_verdict` | 37.0 |
| `M26` | KILLED | `tests/unit/test_handshake.py::test_pure_check_rejects[overrides5-CAPABILITY_NOT_APPROVED]` | 6.3 |
| `M27` | KILLED | `tests/unit/test_config_and_audit.py::test_serve_logging_keeps_only_audit_on_stderr` | 4.1 |
| `M28` | KILLED | `tests/integration/test_review_findings.py::test_r9_annotations_follow_route_kind` | 35.4 |
| `M29` | KILLED | `tests/unit/test_handshake.py::test_explicit_handshake_cannot_reopen_an_incompatible_epoch` | 7.5 |
| `M30` | KILLED | `tests/unit/test_cli.py::test_tracker_records_and_delegates_the_first_sigint` | 2.4 |
| `M31` | KILLED | `tests/unit/test_cli.py::test_tracker_leaves_ignored_or_default_disposition_alone` | 2.0 |
| `M32` | KILLED | `tests/unit/test_cli.py::test_asyncio_runner_keeps_its_own_sigint_handling` | 2.6 |
| `M33` | KILLED | `tests/unit/test_cli.py::test_sigint_watchdog_exits_when_the_runner_never_returns` | 7.6 |
| `M34` | KILLED | `tests/unit/test_cli.py::test_main_disarms_the_watchdog_on_every_exit_path` | 3.4 |
| `M35` | KILLED | `tests/unit/test_cli.py::test_forced_exit_writes_the_interrupted_audit_and_exits_130` | 3.3 |
| `M36` | KILLED | `tests/unit/test_cli.py::test_sigint_handler_starts_no_thread` | 3.6 |
| `M37` | KILLED | `tests/unit/test_cli.py::test_every_interrupted_exit_goes_through_the_forced_exit_once[_interrupted_with_exception]` | 3.5 |
| `M38` | KILLED | `tests/unit/test_cli.py::test_stop_interrupted_runs_once_even_with_the_watchdog` | 3.8 |
| `M39` | KILLED | `tests/unit/test_cli.py::test_stop_holds_the_lock_until_the_exit_completes` | 4.1 |
| `M40` | KILLED | `tests/unit/test_cli.py::test_stop_holds_the_lock_until_the_exit_completes` | 3.8 |
| `M41` | KILLED | `tests/unit/test_cli.py::test_interrupt_grace_is_short` | 4.1 |
| `M42` | KILLED | `tests/unit/test_cli.py::test_stop_ignores_sigint_on_the_main_thread_before_exiting` | 4.0 |
| `M43` | KILLED | `tests/unit/test_cli.py::test_sigint_watchdog_exits_when_the_runner_never_returns` | 7.5 |
| `M44` | KILLED | `tests/unit/test_cli.py::test_second_sigint_ignores_further_signals_before_delegating` | 4.3 |
| `M45` | KILLED | `tests/unit/test_cli.py::test_after_the_loop_sigint_is_recorded_without_raising` | 4.2 |
| `M46` | KILLED | `tests/unit/test_cli.py::test_main_ignores_late_sigint_before_deciding_the_exit[ok]` | 4.1 |
| `M47` | KILLED | `tests/unit/test_cli.py::test_main_ignores_late_sigint_before_deciding_the_exit[transport]` | 4.3 |
| `M48` | KILLED | `tests/unit/test_cli.py::test_server_start_is_written_only_once_sigint_handling_is_active` | 4.1 |
| `N01` | KILLED | `tests/integration/test_market_tools.py::test_real_control_api_book_round_trip_and_id_echo` | 32.3 |
| `N02` | KILLED | `tests/unit/test_market_models.py::test_book_rejected[body3]` | 7.3 |
| `N03` | KILLED | `tests/unit/test_market_models.py::test_book_rejected[body0]` | 7.5 |
| `N04` | KILLED | `tests/unit/test_market_models.py::test_markets_rejected[body0]` | 6.6 |
| `N05` | KILLED | `tests/integration/test_market_tools.py::test_http_adapter_never_builds_a_path_from_an_unvalidated_id[../etc]` | 34.7 |
| `N06` | KILLED | `tests/control_api/test_market_routes.py::test_book_route_rejects_any_other_shape_without_calling_the_core[/v1/markets/../book]` | 52.5 |
| `O01` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.2 |
| `O02` | KILLED | `tests/unit/test_orders_models.py::test_unknown_core_status_can_only_be_reported_as_unknown[MATCHED]` | 6.8 |
| `O03` | KILLED | `tests/unit/test_orders_models.py::test_partial_split_requires_explicit_sizes` | 7.1 |
| `O04` | KILLED | `tests/unit/test_contract_descriptor.py::test_14_cross_field_rules_are_enforced_by_the_mcp[1]` | 4.2 |
| `O05` | KILLED | `tests/unit/test_orders_models.py::test_broker_view_needs_a_bet_id` | 6.8 |
| `O06` | KILLED | `tests/unit/test_orders_models.py::test_duplicate_local_ids_are_rejected` | 6.7 |
| `O07` | KILLED | `tests/unit/test_orders_models.py::test_incoherent_snapshot_is_rejected[snapshot1]` | 7.0 |
| `O08` | KILLED | `tests/unit/test_orders_models.py::test_incoherent_snapshot_is_rejected[snapshot3]` | 6.6 |
| `O09` | KILLED | `tests/integration/test_orders_tools.py::test_orders_are_listed_with_ambiguous_kept_ambiguous` | 32.4 |
| `O10` | KILLED | `tests/unit/test_orders_models.py::test_order_violations_are_rejected[override7]` | 7.1 |
| `O11` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.3 |
| `O12` | KILLED | `tests/unit/test_compat_models.py::test_unconfirmed_with_any_amount_is_rejected[AMBIGUOUS-AMBIGUOUS-size_matched]` | 4.4 |
| `P01` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_snapshot_state_rules[section1]` | 7.5 |
| `P02` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_snapshot_state_rules[section2]` | 7.4 |
| `P03` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.1 |
| `R01` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_engine_record_mapping` | 46.0 |
| `R02` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_owner_question_reconstructed_from_recorded_events_only` | 47.0 |
| `R03` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_absent_field_is_not_recorded_null_is_not_applicable` | 46.3 |
| `R04` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_a_truthy_non_true_answer_is_not_an_accepted_record` | 47.8 |
| `R05` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_filters_use_the_engine_names` | 47.7 |
| `R06` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_unavailable_register_gives_no_data_but_status_still_answers` | 47.7 |
| `R07` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_unmappable_records_are_refused_never_adjusted[over4]` | 46.2 |
| `R08` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_values_are_flattened_exactly_and_unrepresentable_ones_counted` | 46.1 |
| `R09` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_engine_record_mapping` | 46.0 |
| `R10` | KILLED | `tests/contract/test_blackbox_bb1_contract.py::test_unmappable_records_are_refused_never_adjusted[over5]` | 45.7 |
| `S01` | KILLED | `tests/integration/test_blackbox_tools.py::test_bad_blackbox_bodies_are_rejected[StatusScenario.WRONG_SOURCE]` | 10.2 |
| `S02` | KILLED | `tests/integration/test_diagnostics_tools.py::test_invalid_positions_fail_closed[StatusScenario.STALE-UPSTREAM_INVALID_RESPONSE:STALE_SNAPSHOT]` | 13.5 |
| `S03` | KILLED | `tests/integration/test_diagnostics_tools.py::test_core_without_positions_capability_is_never_read` | 13.1 |
| `S04` | KILLED | `tests/unit/test_blackbox_models.py::test_events_rejected[body23]` | 2.1 |
| `S05` | KILLED | `tests/unit/test_status_models.py::test_ready_requires_level_ready_and_no_blockers` | 7.8 |
| `S06` | KILLED | `tests/unit/test_status_models.py::test_ready_requires_level_ready_and_no_blockers` | 7.1 |
| `S07` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.2 |
| `S08` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.3 |
| `S09` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.1 |
| `S10` | KILLED | `tests/integration/test_finance_tools.py::test_timeout_is_bounded_and_retryable[get_account]` | 19.9 |
| `S11` | KILLED | `tests/unit/test_status_models.py::test_not_run_startup_has_no_reason` | 7.7 |
| `S12` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_status_rejected_by_both_sides[11]` | 4.3 |
| `S13` | KILLED | `tests/unit/test_blackbox_models.py::test_status_rejected[body6]` | 1.8 |
| `S14` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.2 |
| `T01` | KILLED | `tests/unit/test_contract_descriptor.py::test_15_cross_field_rules_are_enforced_by_the_mcp[exposure-parse_exposure-body0]` | 4.8 |
| `T02` | KILLED | `tests/unit/test_settlement_sltp_models.py::test_incoherent_sl_tp_is_rejected[sl_tp1]` | 7.4 |
| `T03` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.2 |
| `T04` | KILLED | `tests/unit/test_contract_descriptor.py::test_15_cross_field_rules_are_enforced_by_the_mcp[reconciliation_status-parse_reconciliation_status-body1]` | 4.7 |
| `T05` | KILLED | `tests/unit/test_settlement_sltp_models.py::test_incoherent_settlement_is_rejected[override3]` | 7.8 |
| `T06` | KILLED | `tests/unit/test_settlement_sltp_models.py::test_duplicate_checkpoint_stages_are_rejected` | 8.0 |
| `T07` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_15_rejected_by_both_sides[5]` | 4.7 |
| `X01` | KILLED | `tests/control_api/test_security_hardening.py::test_weak_or_malformed_tokens_are_refused[]` | 52.5 |
| `X02` | KILLED | `tests/control_api/test_security_hardening.py::test_concurrent_rotation_with_a_failed_write_never_revives_the_old_token` | 56.3 |
| `X03` | KILLED | `tests/control_api/test_security_hardening.py::test_idle_connections_are_bounded_and_expire` | 56.9 |
| `X04` | KILLED | `tests/control_api/test_security_hardening.py::test_idle_connections_are_bounded_and_expire` | 58.8 |
| `X05` | KILLED | `tests/control_api/test_security_hardening.py::test_protocol_errors_are_fixed_json_without_echo[FOO<script>x</script>` | 56.6 |
| `X06` | KILLED | `tests/control_api/test_security_hardening.py::test_client_disconnect_prints_no_traceback` | 56.8 |
| `Y01` | KILLED | `tests/unit/test_trailing_models.py::test_incoherent_trailing_is_rejected_by_the_mcp[tr0]` | 7.8 |
| `Y02` | KILLED | `tests/unit/test_trailing_models.py::test_incoherent_trailing_is_rejected_by_the_mcp[tr2]` | 8.0 |
| `Y03` | KILLED | `tests/unit/test_trailing_models.py::test_incoherent_trailing_is_rejected_by_the_mcp[tr4]` | 7.4 |
| `Y04` | KILLED | `tests/unit/test_trailing_models.py::test_incoherent_trailing_is_rejected_by_the_mcp[tr5]` | 7.9 |
| `Y05` | KILLED | `tests/unit/test_trailing_models.py::test_incoherent_trailing_is_rejected_by_the_mcp[tr6]` | 7.8 |
| `Y06` | KILLED | `tests/unit/test_config_models.py::test_invalid_persisted_f18` | 4.2 |
| `Y07` | KILLED | `tests/unit/test_resolve_git_sha.py::test_worktree_on_a_branch` | 7.5 |
| `Z01` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.3 |
| `Z02` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.1 |
| `Z03` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.2 |
| `Z04` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.7 |

</details>

### Campagna su 40c34c4 (catalogo riallineato)

Commit `40c34c4fdeebec786b244a05515675e3c5a5e238` · 216 mutanti · file `mut_campaign_40c34c4.jsonl` sha256 `fbea5bf73993e2c28123ada7fdafe09a5ac9416703f86473bb25585af36714b4`

| Esito | Numero |
|---|---|
| KILLED | 215 |
| SURVIVED | 0 |
| NOT_APPLICABLE | 0 |
| TIMEOUT | 1 |
| INFRA_ERROR | 0 |

Non KILLED:

- `J09` TIMEOUT — timeout dell'invio non applicato (400.1 s)

<details><summary>Esito di ogni mutante (primo test fallito)</summary>

| Mutante | Esito | Primo test fallito | s |
|---|---|---|---|
| `A01` | KILLED | `tests/integration/test_auth_server.py::test_read_principal_calling_write_tool_is_forbidden_with_zero_upstream` | 7.5 |
| `A02` | KILLED | `tests/unit/test_auth.py::test_full_principal_by_tool_matrix[cancel_order-read]` | 1.8 |
| `A03` | KILLED | `tests/unit/test_auth.py::test_missing_principal_fails_closed` | 1.8 |
| `A04` | KILLED | `tests/unit/test_auth.py::test_principal_tampered_after_construction_fails_closed` | 1.8 |
| `A05` | KILLED | `tests/unit/test_auth.py::test_owner_only_operations` | 1.6 |
| `A06` | KILLED | `tests/unit/test_auth.py::test_owner_only_operations` | 1.6 |
| `A07` | KILLED | `tests/unit/test_auth.py::test_read_routes_need_read_and_commands_never_need_read` | 1.5 |
| `A08` | KILLED | `tests/integration/test_auth_server.py::test_registration_without_or_with_wrong_scope_is_refused` | 7.7 |
| `A09` | KILLED | `tests/integration/test_auth_server.py::test_registration_without_or_with_wrong_scope_is_refused` | 8.7 |
| `A10` | KILLED | `tests/integration/test_auth_server.py::test_forbidden_takes_precedence_over_input_validation` | 7.8 |
| `A11` | KILLED | `tests/unit/test_auth.py::test_principal_rejects_forged_or_malformed_scopes[bad_scopes1]` | 2.2 |
| `A12` | KILLED | `tests/unit/test_auth.py::test_parse_principal_rejects_malformed[raw13]` | 1.8 |
| `A13` | KILLED | `tests/unit/test_auth.py::test_local_stdio_principal_is_read_only` | 1.7 |
| `A14` | KILLED | `tests/unit/test_auth.py::test_principal_rejects_forged_or_malformed_scopes[bad_scopes0]` | 2.0 |
| `A15` | KILLED | `tests/unit/test_auth.py::test_owner_only_operations` | 1.7 |
| `B01` | KILLED | `tests/integration/test_blackbox_tools.py::test_unrecordable_request_is_an_unavailable_upstream_never_data` | 10.9 |
| `B02` | KILLED | `tests/control_api/test_server.py::test_invalid_configuration_refused` | 66.1 |
| `B03` | KILLED | `tests/control_api/test_blackbox_query.py::test_rejections_carry_a_fixed_code_never_the_input[foo=1-QUERY_PARAM]` | 48.5 |
| `B04` | KILLED | `tests/control_api/test_blackbox_query.py::test_rejections_carry_a_fixed_code_never_the_input[limit=1&limit=2-QUERY_PARAM_REPEATED]` | 47.6 |
| `B05` | KILLED | `tests/control_api/test_blackbox_query.py::test_rejections_carry_a_fixed_code_never_the_input[since=2026-01-01T00:00:00Z&until=2026-03-01T00:00:00Z-QUERY_RANGE]` | 48.8 |
| `B06` | KILLED | `tests/control_api/test_blackbox_routes.py::test_sensitive_values_never_leave_even_if_the_engine_wrote_them` | 48.7 |
| `B07` | KILLED | `tests/unit/test_blackbox_models.py::test_events_rejected[body0]` | 1.9 |
| `B08` | KILLED | `tests/unit/test_blackbox_models.py::test_events_rejected[body2]` | 1.9 |
| `B09` | KILLED | `tests/integration/test_blackbox_tools.py::test_http_adapter_never_sends_an_unvalidated_query[query0]` | 10.4 |
| `B10` | KILLED | `tests/integration/test_blackbox_tools.py::test_unrecordable_request_is_an_unavailable_upstream_never_data` | 10.3 |
| `B11` | KILLED | `tests/unit/test_blackbox_models.py::test_event_detail_rejected[body2]` | 2.1 |
| `B12` | KILLED | `tests/integration/test_blackbox_tools.py::test_a_core_that_ignores_the_cursor_is_not_trusted` | 10.7 |
| `B13` | KILLED | `tests/control_api/test_blackbox_routes.py::test_one_record_per_request_never_one_per_event` | 51.4 |
| `B14` | KILLED | `tests/integration/test_blackbox_tools.py::test_unrecordable_request_is_an_unavailable_upstream_never_data` | 10.4 |
| `C01` | KILLED | `tests/integration/test_diagnostics_tools.py::test_float_amount_from_core_is_stopped_by_the_server` | 14.4 |
| `C02` | KILLED | `tests/integration/test_blackbox_tools.py::test_real_control_api_round_trip_records_the_mcp_request` | 9.4 |
| `C03` | KILLED | `tests/integration/test_http_adapter.py::test_control_api_down_then_restarted_recovers_with_new_handshake` | 27.2 |
| `C04` | KILLED | `tests/control_api/test_server.py::test_wrong_host[localhost]` | 56.3 |
| `C05` | KILLED | `tests/control_api/test_tokens.py::test_during_rotation_both_tokens_accepted_then_only_new` | 66.3 |
| `C06` | KILLED | `tests/integration/test_http_adapter.py::test_rotation_is_recovered_with_one_reload` | 27.3 |
| `C07` | KILLED | `tests/control_api/test_server.py::test_almost_equal_tokens_are_rejected` | 66.9 |
| `C08` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_status_rejected_by_both_sides[9]` | 4.3 |
| `C09` | KILLED | `tests/control_api/test_schema_check.py::test_unknown_keyword_is_an_error_not_ignored` | 52.1 |
| `C10` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_reconciliation_rejected_by_both_sides[1]` | 4.7 |
| `C11` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_status_rejected_by_both_sides[13]` | 4.4 |
| `F01` | KILLED | `tests/unit/test_contract_descriptor.py::test_cross_field_rules_are_enforced_by_the_mcp[account-parse_account-override0]` | 4.1 |
| `F02` | KILLED | `tests/unit/test_contract_descriptor.py::test_cross_field_rules_are_enforced_by_the_mcp[account-parse_account-override2]` | 4.1 |
| `F03` | KILLED | `tests/unit/test_contract_descriptor.py::test_cross_field_rules_are_enforced_by_the_mcp[account-parse_account-override3]` | 4.5 |
| `F04` | KILLED | `tests/unit/test_contract_descriptor.py::test_cross_field_rules_are_enforced_by_the_mcp[exposure-parse_exposure-override4]` | 4.4 |
| `F05` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.1 |
| `F06` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.2 |
| `F07` | KILLED | `tests/integration/test_finance_tools.py::test_simulated_answers_are_marked_simulated[get_account]` | 14.5 |
| `F08` | KILLED | `tests/control_api/test_server.py::test_approved_but_unserved_reads_are_typed_not_implemented[/v1/events]` | 59.7 |
| `F09` | KILLED | `tests/control_api/test_server.py::test_unknown_paths[/v1/operations/.]` | 61.5 |
| `F10` | KILLED | `tests/integration/test_finance_tools.py::test_not_implemented_from_the_core_is_typed_and_not_retried` | 23.2 |
| `F11` | KILLED | `tests/integration/test_finance_tools.py::test_not_implemented_from_the_core_is_typed_and_not_retried` | 23.0 |
| `F12` | KILLED | `tests/control_api/test_server.py::test_invalid_configuration_refused` | 66.8 |
| `F13` | KILLED | `tests/unit/test_cli.py::test_contract_info` | 2.8 |
| `F14` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.2 |
| `G01` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.2 |
| `G02` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.4 |
| `G03` | KILLED | `tests/unit/test_contract_descriptor.py::test_13_cross_field_rules_are_enforced_by_the_mcp[status-parse_status-body0]` | 4.1 |
| `G04` | KILLED | `tests/unit/test_contract_descriptor.py::test_valid_status_accepted_by_both_sides[body0]` | 4.2 |
| `G05` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.7 |
| `G06` | KILLED | `tests/unit/test_contract_descriptor.py::test_13_cross_field_rules_are_enforced_by_the_mcp[positions-parse_positions-body2]` | 4.2 |
| `G07` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_positions_rejected_by_both_sides[4]` | 4.1 |
| `G08` | KILLED | `tests/unit/test_diagnostics_models.py::test_ready_engine_with_failing_component_is_rejected` | 6.0 |
| `G09` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.1 |
| `G10` | KILLED | `tests/integration/test_diagnostics_tools.py::test_positions_keep_decimal_strings_end_to_end` | 12.0 |
| `G11` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_13_status_rejected_by_both_sides[8]` | 4.2 |
| `H01` | KILLED | `tests/integration/test_http_adapter.py::test_protocol_violations_fail_closed[_redirect-UPSTREAM_INVALID_RESPONSE:HTTP_302]` | 27.4 |
| `H02` | KILLED | `tests/integration/test_http_adapter.py::test_protocol_violations_fail_closed[_wrong_type-UPSTREAM_INVALID_RESPONSE:CONTENT_TYPE]` | 29.4 |
| `H03` | KILLED | `tests/integration/test_http_adapter.py::test_wrong_token_is_unauthorized_and_not_retryable` | 28.1 |
| `H04` | KILLED | `tests/integration/test_http_adapter.py::test_rotation_is_recovered_with_one_reload` | 25.4 |
| `H05` | KILLED | `tests/integration/test_http_adapter.py::test_control_api_down_then_restarted_recovers_with_new_handshake` | 26.3 |
| `H06` | KILLED | `tests/integration/test_http_adapter.py::test_adapter_never_reads_more_than_the_limit` | 32.2 |
| `H07` | KILLED | `tests/integration/test_blackbox_tools.py::test_real_control_api_round_trip_records_the_mcp_request` | 9.6 |
| `H08` | KILLED | `tests/unit/test_cli.py::test_http_adapter_token_file_unsafe_is_refused_without_leaking` | 3.1 |
| `H09` | KILLED | `tests/unit/test_token_file.py::test_wrong_owner_rejected` | 7.6 |
| `H10` | KILLED | `tests/unit/test_token_file.py::test_symlink_rejected` | 8.2 |
| `H11` | KILLED | `tests/unit/test_token_file.py::test_writable_directory_rejected[511]` | 7.9 |
| `H12` | KILLED | `tests/unit/test_token_file.py::test_altered_content_rejected[short]` | 8.3 |
| `H13` | KILLED | `tests/unit/test_cli.py::test_http_adapter_misconfiguration_never_falls_back[args0-HTTP_ADAPTER_REQUIRES_PORT_AND_TOKEN_FILE]` | 2.1 |
| `H14` | KILLED | `tests/integration/test_http_adapter.py::test_token_file_made_readable_by_others_fails_closed` | 26.4 |
| `H15` | KILLED | `tests/integration/test_http_adapter.py::test_protocol_violations_fail_closed[_redirect-UPSTREAM_INVALID_RESPONSE:HTTP_302]` | 28.2 |
| `J01` | KILLED | `tests/unit/test_journal.py::test_duplicate_returns_same_operation_without_upstream_call` | 6.5 |
| `J02` | KILLED | `tests/unit/test_journal.py::test_fsync_failure_no_mutation` | 6.4 |
| `J03` | KILLED | `tests/unit/test_journal.py::test_exclusive_lock_second_opener_cannot_write` | 6.3 |
| `J04` | KILLED | `tests/unit/test_journal.py::test_failure_after_send_is_ambiguous_and_never_retried[bad_ack]` | 6.9 |
| `J05` | KILLED | `tests/unit/test_journal.py::test_crash_after_send_is_ambiguous_no_replay` | 6.5 |
| `J06` | KILLED | `tests/unit/test_journal.py::test_checksum_detects_structurally_valid_tampering` | 6.8 |
| `J07` | KILLED | `tests/unit/test_journal.py::test_corrupt_journal_fails_closed_reads_allowed[truncate]` | 6.5 |
| `J08` | KILLED | `tests/unit/test_journal.py::test_replaced_file_detected` | 6.4 |
| `J09` | TIMEOUT | `—` | 400.1 |
| `J10` | KILLED | `tests/unit/test_journal.py::test_crash_after_send_is_ambiguous_no_replay` | 6.5 |
| `J11` | KILLED | `tests/unit/test_journal.py::test_duplicate_survives_restart` | 6.5 |
| `J12` | KILLED | `tests/unit/test_journal.py::test_new_entry_has_request_operation_correlation` | 6.5 |
| `J13` | KILLED | `tests/unit/test_journal.py::test_read_retry_attempts_bounded` | 7.4 |
| `K01` | KILLED | `tests/unit/test_config_models.py::test_setting_rules[max_daily_loss-overrides1]` | 4.3 |
| `K02` | KILLED | `tests/unit/test_config_models.py::test_structure_is_closed[missing-key]` | 4.0 |
| `K03` | KILLED | `tests/unit/test_config_models.py::test_setting_rules[table_count-overrides0]` | 4.4 |
| `K04` | KILLED | `tests/unit/test_config_models.py::test_setting_rules[commission_pct-overrides4]` | 4.3 |
| `K05` | KILLED | `tests/unit/test_config_models.py::test_sensitive_names_never_accepted_in_unlisted[betfair_app_key]` | 4.1 |
| `K06` | KILLED | `tests/unit/test_config_models.py::test_unlisted_rules[unlisted1]` | 4.5 |
| `K07` | KILLED | `tests/unit/test_config_models.py::test_unavailable_settings` | 4.7 |
| `K08` | KILLED | `tests/unit/test_config_models.py::test_unlisted_rules[unlisted0]` | 4.2 |
| `L01` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides0]` | 8.7 |
| `L02` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides2]` | 8.2 |
| `L03` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides4]` | 7.5 |
| `L04` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides5]` | 8.0 |
| `L05` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides6]` | 7.9 |
| `L06` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_snapshot_state_rules[section0]` | 7.6 |
| `L07` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides7]` | 7.8 |
| `L08` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_close_rules_are_enforced_by_the_mcp[overrides8]` | 8.5 |
| `M01` | KILLED | `tests/unit/test_handshake.py::test_pure_check_rejects[overrides0-VERSION_UNSUPPORTED]` | 6.0 |
| `M02` | KILLED | `tests/unit/test_handshake.py::test_pure_check_rejects[overrides3-SCHEMA_HASH_UNKNOWN]` | 6.0 |
| `M03` | KILLED | `tests/unit/test_handshake.py::test_pure_check_rejects[overrides5-CAPABILITY_NOT_APPROVED]` | 6.2 |
| `M04` | KILLED | `tests/unit/test_handshake.py::test_pure_check_rejects[overrides4-CAPABILITY_MISSING:GET` | 6.1 |
| `M05` | KILLED | `tests/unit/test_handshake.py::test_failing_scenarios[Scenario.INCOMPATIBLE_MAJOR-HandshakeStatus.INCOMPATIBLE-ErrorCode.CONTRACT_INCOMPATIBLE]` | 5.7 |
| `M06` | KILLED | `tests/unit/test_handshake.py::test_reconnect_forces_new_handshake` | 6.1 |
| `M07` | KILLED | `tests/unit/test_handshake.py::test_failing_scenarios[Scenario.TIMEOUT-HandshakeStatus.UNAVAILABLE-ErrorCode.UPSTREAM_TIMEOUT]` | 12.0 |
| `M08` | KILLED | `tests/unit/test_handshake.py::test_failing_scenarios[Scenario.INCOMPATIBLE_MAJOR-HandshakeStatus.INCOMPATIBLE-ErrorCode.CONTRACT_INCOMPATIBLE]` | 5.8 |
| `M09` | KILLED | `tests/unit/test_blackbox_models.py::test_events_rejected[body13]` | 1.8 |
| `M10` | KILLED | `tests/unit/test_config_models.py::test_setting_rules[table_count-overrides7]` | 4.3 |
| `M11` | KILLED | `tests/unit/test_models_meta.py::test_strict_base_rejects_coercion_and_non_finite_numbers` | 8.3 |
| `M12` | KILLED | `tests/unit/test_models_meta.py::test_invalid_meta_is_rejected[{"contract_version":` | 7.6 |
| `M13` | KILLED | `tests/unit/test_models_meta.py::test_invalid_meta_is_rejected[{"contract_version":"1.0.0","contract_version":"1.0.0","capabilities":["GET` | 7.4 |
| `M14` | KILLED | `tests/unit/test_models_meta.py::test_invalid_meta_is_rejected[{"contract_version":` | 7.1 |
| `M15` | KILLED | `tests/unit/test_models_meta.py::test_oversized_body_is_rejected_before_parsing` | 8.4 |
| `M16` | KILLED | `tests/unit/test_registry_guard.py::test_command_tools_are_refused_while_exposure_blocked[place_order-POST` | 7.8 |
| `M17` | KILLED | `tests/unit/test_registry_guard.py::test_command_tools_are_refused_while_exposure_blocked[place_order-POST` | 7.5 |
| `M18` | KILLED | `tests/unit/test_registry_guard.py::test_forbidden_name_is_refused_even_if_catalog_were_extended` | 7.6 |
| `M19` | KILLED | `tests/unit/test_registry_guard.py::test_name_route_mismatch_is_refused` | 7.3 |
| `M20` | KILLED | `tests/integration/test_auth_server.py::test_forbidden_takes_precedence_over_input_validation` | 7.8 |
| `M21` | KILLED | `1 error in 0.73s` | 1.2 |
| `M22` | KILLED | `tests/unit/test_config_and_audit.py::test_non_loopback_or_malformed_urls_are_rejected[http://0.0.0.0:8770-CONFIG_HOST_NOT_LOOPBACK]` | 4.0 |
| `M23` | KILLED | `tests/unit/test_config_and_audit.py::test_audit_keeps_only_allowlisted_fields` | 3.8 |
| `M24` | KILLED | `tests/integration/test_auth_server.py::test_altered_tool_names_are_unknown_and_never_reach_upstream[PLACE_ORDER]` | 8.5 |
| `M25` | KILLED | `tests/integration/test_review_findings.py::test_r2_cancelled_handshake_does_not_keep_previous_verdict` | 34.0 |
| `M26` | KILLED | `tests/unit/test_handshake.py::test_pure_check_rejects[overrides5-CAPABILITY_NOT_APPROVED]` | 5.9 |
| `M27` | KILLED | `tests/unit/test_config_and_audit.py::test_serve_logging_keeps_only_audit_on_stderr` | 4.2 |
| `M28` | KILLED | `tests/integration/test_review_findings.py::test_r9_annotations_follow_route_kind` | 35.5 |
| `M29` | KILLED | `tests/unit/test_handshake.py::test_explicit_handshake_cannot_reopen_an_incompatible_epoch` | 5.8 |
| `M30` | KILLED | `tests/unit/test_cli.py::test_tracker_records_and_delegates_the_first_sigint` | 2.0 |
| `M31` | KILLED | `tests/unit/test_cli.py::test_tracker_leaves_ignored_or_default_disposition_alone` | 2.1 |
| `M32` | KILLED | `tests/unit/test_cli.py::test_asyncio_runner_keeps_its_own_sigint_handling` | 2.0 |
| `M33` | KILLED | `tests/unit/test_cli.py::test_sigint_watchdog_exits_when_the_runner_never_returns` | 6.9 |
| `M34` | KILLED | `tests/unit/test_cli.py::test_main_disarms_the_watchdog_on_every_exit_path` | 3.3 |
| `M35` | KILLED | `tests/unit/test_cli.py::test_forced_exit_writes_the_interrupted_audit_and_exits_130` | 3.2 |
| `M36` | KILLED | `tests/unit/test_cli.py::test_sigint_handler_starts_no_thread` | 3.4 |
| `M37` | KILLED | `tests/unit/test_cli.py::test_every_interrupted_exit_goes_through_the_forced_exit_once[_interrupted_with_exception]` | 3.5 |
| `M38` | KILLED | `tests/unit/test_cli.py::test_stop_interrupted_runs_once_even_with_the_watchdog` | 3.5 |
| `M39` | KILLED | `tests/unit/test_cli.py::test_stop_holds_the_lock_until_the_exit_completes` | 3.4 |
| `M40` | KILLED | `tests/unit/test_cli.py::test_stop_holds_the_lock_until_the_exit_completes` | 3.6 |
| `M41` | KILLED | `tests/unit/test_cli.py::test_interrupt_grace_is_short` | 3.9 |
| `M42` | KILLED | `tests/unit/test_cli.py::test_stop_ignores_sigint_on_the_main_thread_before_exiting` | 3.9 |
| `M43` | KILLED | `tests/unit/test_cli.py::test_sigint_watchdog_exits_when_the_runner_never_returns` | 7.1 |
| `M44` | KILLED | `tests/unit/test_cli.py::test_second_sigint_ignores_further_signals_before_delegating` | 4.0 |
| `M45` | KILLED | `tests/unit/test_cli.py::test_after_the_loop_sigint_is_recorded_without_raising` | 4.0 |
| `M46` | KILLED | `tests/unit/test_cli.py::test_main_ignores_late_sigint_before_deciding_the_exit[ok]` | 4.1 |
| `M47` | KILLED | `tests/unit/test_cli.py::test_main_ignores_late_sigint_before_deciding_the_exit[transport]` | 3.9 |
| `M48` | KILLED | `tests/unit/test_cli.py::test_server_start_is_written_only_once_sigint_handling_is_active` | 4.2 |
| `N01` | KILLED | `tests/integration/test_market_tools.py::test_real_control_api_book_round_trip_and_id_echo` | 34.3 |
| `N02` | KILLED | `tests/unit/test_market_models.py::test_book_rejected[body3]` | 7.4 |
| `N03` | KILLED | `tests/unit/test_market_models.py::test_book_rejected[body0]` | 6.9 |
| `N04` | KILLED | `tests/unit/test_market_models.py::test_markets_rejected[body0]` | 7.0 |
| `N05` | KILLED | `tests/integration/test_market_tools.py::test_http_adapter_never_builds_a_path_from_an_unvalidated_id[../etc]` | 32.8 |
| `N06` | KILLED | `tests/control_api/test_market_routes.py::test_book_route_rejects_any_other_shape_without_calling_the_core[/v1/markets/../book]` | 50.3 |
| `O01` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.3 |
| `O02` | KILLED | `tests/unit/test_orders_models.py::test_unknown_core_status_can_only_be_reported_as_unknown[MATCHED]` | 7.4 |
| `O03` | KILLED | `tests/unit/test_orders_models.py::test_partial_split_requires_explicit_sizes` | 7.2 |
| `O04` | KILLED | `tests/unit/test_contract_descriptor.py::test_14_cross_field_rules_are_enforced_by_the_mcp[1]` | 4.4 |
| `O05` | KILLED | `tests/unit/test_orders_models.py::test_broker_view_needs_a_bet_id` | 7.2 |
| `O06` | KILLED | `tests/unit/test_orders_models.py::test_duplicate_local_ids_are_rejected` | 7.1 |
| `O07` | KILLED | `tests/unit/test_orders_models.py::test_incoherent_snapshot_is_rejected[snapshot1]` | 7.5 |
| `O08` | KILLED | `tests/unit/test_orders_models.py::test_incoherent_snapshot_is_rejected[snapshot3]` | 7.0 |
| `O09` | KILLED | `tests/integration/test_orders_tools.py::test_orders_are_listed_with_ambiguous_kept_ambiguous` | 31.6 |
| `O10` | KILLED | `tests/unit/test_orders_models.py::test_order_violations_are_rejected[override7]` | 7.3 |
| `O11` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.3 |
| `O12` | KILLED | `tests/unit/test_compat_models.py::test_unconfirmed_with_any_amount_is_rejected[AMBIGUOUS-AMBIGUOUS-size_matched]` | 4.3 |
| `P01` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_snapshot_state_rules[section1]` | 7.8 |
| `P02` | KILLED | `tests/unit/test_sl_tp_close_models.py::test_snapshot_state_rules[section2]` | 8.0 |
| `P03` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.6 |
| `S01` | KILLED | `tests/integration/test_blackbox_tools.py::test_bad_blackbox_bodies_are_rejected[StatusScenario.WRONG_SOURCE]` | 9.3 |
| `S02` | KILLED | `tests/integration/test_diagnostics_tools.py::test_invalid_positions_fail_closed[StatusScenario.STALE-UPSTREAM_INVALID_RESPONSE:STALE_SNAPSHOT]` | 14.6 |
| `S03` | KILLED | `tests/integration/test_diagnostics_tools.py::test_core_without_positions_capability_is_never_read` | 13.1 |
| `S04` | KILLED | `tests/unit/test_blackbox_models.py::test_events_rejected[body22]` | 1.9 |
| `S05` | KILLED | `tests/unit/test_status_models.py::test_ready_requires_level_ready_and_no_blockers` | 8.4 |
| `S06` | KILLED | `tests/unit/test_status_models.py::test_ready_requires_level_ready_and_no_blockers` | 7.6 |
| `S07` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.3 |
| `S08` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.6 |
| `S09` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.0 |
| `S10` | KILLED | `tests/integration/test_finance_tools.py::test_timeout_is_bounded_and_retryable[get_account]` | 19.7 |
| `S11` | KILLED | `tests/unit/test_status_models.py::test_not_run_startup_has_no_reason` | 8.5 |
| `S12` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_status_rejected_by_both_sides[11]` | 4.5 |
| `S13` | KILLED | `tests/unit/test_blackbox_models.py::test_status_rejected[body6]` | 2.0 |
| `S14` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.6 |
| `T01` | KILLED | `tests/unit/test_contract_descriptor.py::test_15_cross_field_rules_are_enforced_by_the_mcp[exposure-parse_exposure-body0]` | 4.5 |
| `T02` | KILLED | `tests/unit/test_settlement_sltp_models.py::test_incoherent_sl_tp_is_rejected[sl_tp1]` | 8.3 |
| `T03` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.3 |
| `T04` | KILLED | `tests/unit/test_contract_descriptor.py::test_15_cross_field_rules_are_enforced_by_the_mcp[reconciliation_status-parse_reconciliation_status-body1]` | 4.3 |
| `T05` | KILLED | `tests/unit/test_settlement_sltp_models.py::test_incoherent_settlement_is_rejected[override3]` | 7.6 |
| `T06` | KILLED | `tests/unit/test_settlement_sltp_models.py::test_duplicate_checkpoint_stages_are_rejected` | 7.5 |
| `T07` | KILLED | `tests/unit/test_contract_descriptor.py::test_hostile_15_rejected_by_both_sides[5]` | 4.8 |
| `X01` | KILLED | `tests/control_api/test_security_hardening.py::test_weak_or_malformed_tokens_are_refused[]` | 57.0 |
| `X02` | KILLED | `tests/control_api/test_security_hardening.py::test_concurrent_rotation_with_a_failed_write_never_revives_the_old_token` | 54.6 |
| `X03` | KILLED | `tests/control_api/test_security_hardening.py::test_idle_connections_are_bounded_and_expire` | 56.0 |
| `X04` | KILLED | `tests/control_api/test_security_hardening.py::test_idle_connections_are_bounded_and_expire` | 60.5 |
| `X05` | KILLED | `tests/control_api/test_security_hardening.py::test_protocol_errors_are_fixed_json_without_echo[FOO<script>x</script>` | 61.4 |
| `X06` | KILLED | `tests/control_api/test_security_hardening.py::test_client_disconnect_prints_no_traceback` | 55.7 |
| `Y01` | KILLED | `tests/unit/test_trailing_models.py::test_incoherent_trailing_is_rejected_by_the_mcp[tr0]` | 8.0 |
| `Y02` | KILLED | `tests/unit/test_trailing_models.py::test_incoherent_trailing_is_rejected_by_the_mcp[tr2]` | 7.4 |
| `Y03` | KILLED | `tests/unit/test_trailing_models.py::test_incoherent_trailing_is_rejected_by_the_mcp[tr4]` | 8.7 |
| `Y04` | KILLED | `tests/unit/test_trailing_models.py::test_incoherent_trailing_is_rejected_by_the_mcp[tr5]` | 8.0 |
| `Y05` | KILLED | `tests/unit/test_trailing_models.py::test_incoherent_trailing_is_rejected_by_the_mcp[tr6]` | 8.1 |
| `Y06` | KILLED | `tests/unit/test_config_models.py::test_invalid_persisted_f18` | 4.6 |
| `Y07` | KILLED | `tests/unit/test_resolve_git_sha.py::test_worktree_on_a_branch` | 7.3 |
| `Z01` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.4 |
| `Z02` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.4 |
| `Z03` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 4.5 |
| `Z04` | KILLED | `tests/unit/test_contract_descriptor.py::test_both_committed_copies_equal_the_generated_descriptor` | 5.6 |

</details>

