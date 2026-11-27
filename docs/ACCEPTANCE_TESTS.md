# Acceptance criteria → automated tests

All tests are in `backend/tests/test_acceptance.py`. Latest run: [test-results.txt](test-results.txt) (21 passed, on both SQLite and PostgreSQL 16).

| # | Acceptance workflow | Test(s) |
|---|---|---|
| 1 | Applicant submits through the existing WordPress site | `test_01_02_wordpress_application_received_and_stored` (signed webhook in the same format the plugin sends) |
| 2 | Application received and stored | same as 1 |
| 3 | Duplicates identified | `test_03_duplicates_identified`, `test_duplicate_gets_no_second_acknowledgment` |
| 4 | AI processes and classifies | `test_04_05_ai_classifies_and_acknowledgment_sent` |
| 5 | Acknowledgment generated and sent | same as 4 |
| 6 | Incoming email recognised | `test_06_07_08_inbound_email_recognised_associated_and_visible`, `test_inbound_duplicate_processing_prevented` |
| 7 | Conversation linked to the correct applicant | same as 6, plus `test_reply_in_thread_from_new_address_matched` |
| 8 | Conversation visible in the dashboard | same as 6 (via `/api/conversations`) |
| 9 | Admin reviews and takes over | `test_09_admin_reviews_approves_and_takes_over`, `test_sensitive_question_escalates_to_human` |
| 10 | Automation paused or stopped immediately | `test_10_global_pause_stops_all_automation`, `test_10_individual_pause_and_opt_out_enforced_immediately` |
| 11 | Applications accepted while the AI is down | `test_11_12_applications_accepted_during_ai_outage_and_processed_after` |
| 12 | Pending applications processed after recovery | same as 11 |
| 13 | Open WebUI accessible from the dashboard | `test_13_open_webui_gated_by_dashboard_login`, plus a manual gateway check (unauthenticated `/ai/` returns 302 to login; authenticated requests are proxied) |
| 14 | Open WebUI talks to local inference | `test_14_settings_expose_open_webui_and_llm`. Live check on deployment: send a prompt in Open WebUI. |

Additional checks: webhook signature and replay rejection, email validation, delivery-failure recording and retry, the guardrail that blocks "you are hired/rejected" drafts, follow-up `max_sends`, and audit logging.
