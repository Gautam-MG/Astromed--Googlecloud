"""Persist chart lineage under the verified application user."""

from __future__ import annotations

import json
from typing import Any

from app_core.identifiers import (
    ALGORITHM_VERSION,
    algorithm_result_id,
    birth_key,
    input_id_for,
)

_MAX_BYTES = 800_000
_OMIT = {"svg_raw", "chart_svg", "svg_url"}


def _shrink(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _shrink(item) for key, item in value.items() if key not in _OMIT}
    if isinstance(value, list):
        return [_shrink(item) for item in value]
    return value


def _fit(document: dict) -> dict:
    encoded = json.dumps(document, default=str).encode("utf-8")
    if len(encoded) <= _MAX_BYTES:
        return document
    return {
        "truncated": True,
        "reason": "firestore_document_limit",
        "keys": sorted(document.keys()),
        "input_id": document.get("input_id"),
        "patient_id": document.get("patient_id"),
        "algorithm": document.get("algorithm"),
    }


class ChartPersistence:
    def __init__(self, repository):
        self.repository = repository

    def input_identity(
        self, internal_user_id: str, chart_input: dict
    ) -> tuple[str, str]:
        birth = birth_key(
            chart_input["name"],
            chart_input["dob"],
            chart_input["birth_time"],
            chart_input["lat"],
            chart_input["lng"],
        )
        return input_id_for(internal_user_id, birth), birth

    def save_generation(
        self,
        internal_user_id: str,
        chart_input: dict,
        patient_id: str,
        source: str,
        response: dict,
    ) -> dict:
        import logging

        log = logging.getLogger("astromedica")

        log.info(
            "persistence_save_generation_started",
            extra={
                "operation": "save_generation",
                "internal_user_id": internal_user_id,
                "patient_id": patient_id,
                "source": source,
            },
        )

        # ---------------------------------------------------------
        # STEP 1: Build input identity
        # ---------------------------------------------------------
        log.info(
            "persistence_step_01_input_identity_started",
            extra={
                "operation": "save_generation",
                "patient_id": patient_id,
            },
        )

        try:
            input_id, birth = self.input_identity(
                internal_user_id,
                chart_input,
            )

            log.info(
                "persistence_step_02_input_identity_completed",
                extra={
                    "operation": "save_generation",
                    "patient_id": patient_id,
                    "input_id": input_id,
                },
            )
        except Exception as exc:
            log.exception(
                "persistence_algorithm_save_failed",
                extra={
                    "operation": "save_generation",
                    "patient_id": patient_id,
                    "input_id": input_id,
                    "algorithm": name,
                    "doc_id": doc_id,
                    "error_type": type(exc).__name__,
                    "error": repr(exc),
                },
            )
            raise




        # ---------------------------------------------------------
        # STEP 2: Save input document
        # ---------------------------------------------------------
        log.info(
            "persistence_step_03_input_save_started",
            extra={
                "operation": "save_generation",
                "patient_id": patient_id,
                "input_id": input_id,
                "collection": "inputs",
            },
        )

        try:
            self.repository.save(
                internal_user_id,
                "inputs",
                input_id,
                {
                    "record_type": "input",
                    "input_id": input_id,
                    "birth_key": birth,
                    "patient_id": patient_id,
                    "source": "user_form",
                    "status": "processed",
                    "profile": {
                        "name": chart_input["name"],
                        "dob": chart_input["dob"],
                        "birth_time": chart_input["birth_time"],
                        "birth_place": chart_input.get("birth_place", ""),
                        "lat": chart_input["lat"],
                        "lng": chart_input["lng"],
                        "gender": chart_input.get("gender", "Unknown"),
                    },
                },
            )

            log.info(
                "persistence_step_04_input_save_completed",
                extra={
                    "operation": "save_generation",
                    "patient_id": patient_id,
                    "input_id": input_id,
                },
            )
        except Exception as exc:
            log.exception(
                "persistence_step_04_input_save_failed",
                extra={
                    "operation": "save_generation",
                    "patient_id": patient_id,
                    "input_id": input_id,
                    "collection": "inputs",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise

        # ---------------------------------------------------------
        # STEP 3: Bind patient
        # ---------------------------------------------------------
        log.info(
            "persistence_step_05_bind_patient_started",
            extra={
                "operation": "save_generation",
                "patient_id": patient_id,
                "input_id": input_id,
            },
        )

        try:
            self.repository.bind_patient(
                internal_user_id,
                patient_id,
                input_id,
            )

            log.info(
                "persistence_step_06_bind_patient_completed",
                extra={
                    "operation": "save_generation",
                    "patient_id": patient_id,
                    "input_id": input_id,
                },
            )
        except Exception as exc:
            log.exception(
                "persistence_step_06_bind_patient_failed",
                extra={
                    "operation": "save_generation",
                    "patient_id": patient_id,
                    "input_id": input_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise

        # ---------------------------------------------------------
        # STEP 4: Save Prokerala result
        # ---------------------------------------------------------
        log.info(
            "persistence_step_07_prokerala_save_started",
            extra={
                "operation": "save_generation",
                "patient_id": patient_id,
                "input_id": input_id,
                "collection": "prokerala_results",
            },
        )

        try:
            prokerala_document = _fit(
                {
                    "record_type": "prokerala",
                    "input_id": input_id,
                    "patient_id": patient_id,
                    "source": source,
                    "status": "stored",
                    "ascendant": response.get("ascendant"),
                    "planets": response.get("planets"),
                    "houses": response.get("houses"),
                    "data_source": source,
                }
            )

            self.repository.save(
                internal_user_id,
                "prokerala_results",
                input_id,
                prokerala_document,
            )

            log.info(
                "persistence_step_08_prokerala_save_completed",
                extra={
                    "operation": "save_generation",
                    "patient_id": patient_id,
                    "input_id": input_id,
                },
            )
        except Exception as exc:
            log.exception(
                "persistence_step_08_prokerala_save_failed",
                extra={
                    "operation": "save_generation",
                    "patient_id": patient_id,
                    "input_id": input_id,
                    "collection": "prokerala_results",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise

        # ---------------------------------------------------------
        # STEP 5: Save algorithm results
        # ---------------------------------------------------------
        algorithm_names = (
            "rule1",
            "dasha",
            "complete_analysis",
            "disease_filter",
            "hitlist",
            "rashi_correlation",
            "organ_truth_correlation",
            "dasha_chat_priority",
            "zone_analysis",
            "second_ascendant",
            "imp_rashi_distance",
            "birth_current_distance",
            "health_forecast",
            "diagnosis",
        )

        algorithm_ids = []

        log.info(
            "persistence_step_09_algorithm_results_started",
            extra={
                "operation": "save_generation",
                "patient_id": patient_id,
                "input_id": input_id,
                "algorithm_count": len(algorithm_names),
            },
        )

        for name in algorithm_names:
            if name not in response:
                log.info(
                    "persistence_algorithm_skipped",
                    extra={
                        "operation": "save_generation",
                        "patient_id": patient_id,
                        "input_id": input_id,
                        "algorithm": name,
                        "reason": "missing_from_response",
                    },
                )
                continue

            doc_id = algorithm_result_id(input_id, name)
            algorithm_ids.append(doc_id)

            log.info(
                "persistence_algorithm_save_started",
                extra={
                    "operation": "save_generation",
                    "patient_id": patient_id,
                    "input_id": input_id,
                    "algorithm": name,
                    "doc_id": doc_id,
                },
            )

            try:
                algorithm_output = _shrink(response.get(name))

                algorithm_document = _fit(
                    {
                        "record_type": "algorithm",
                        "algorithm": name,
                        "algorithm_version": ALGORITHM_VERSION,
                        "input_id": input_id,
                        "prokerala_result_id": input_id,
                        "patient_id": patient_id,
                        "source": "rules_engine",
                        "status": "complete",
                        "output": algorithm_output,
                    }
                )

                self.repository.save(
                    internal_user_id,
                    "algorithm_results",
                    doc_id,
                    algorithm_document,
                )

                log.info(
                    "persistence_algorithm_save_completed",
                    extra={
                        "operation": "save_generation",
                        "patient_id": patient_id,
                        "input_id": input_id,
                        "algorithm": name,
                        "doc_id": doc_id,
                    },
                )

            except Exception as exc:
                log.exception(
                    "persistence_algorithm_save_failed",
                    extra={
                        "operation": "save_generation",
                        "patient_id": patient_id,
                        "input_id": input_id,
                        "algorithm": name,
                        "doc_id": doc_id,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                raise

        log.info(
            "persistence_step_10_algorithm_results_completed",
            extra={
                "operation": "save_generation",
                "patient_id": patient_id,
                "input_id": input_id,
                "algorithm_ids_count": len(algorithm_ids),
            },
        )

        # ---------------------------------------------------------
        # STEP 6: Save combined result
        # ---------------------------------------------------------
        combined_id = algorithm_result_id(
            input_id,
            "chart_summary",
        )

        log.info(
            "persistence_step_11_combined_save_started",
            extra={
                "operation": "save_generation",
                "patient_id": patient_id,
                "input_id": input_id,
                "combined_id": combined_id,
                "collection": "combined_results",
            },
        )

        try:
            combined_document = _fit(
                {
                    "record_type": "combined",
                    "combined_result_id": combined_id,
                    "input_id": input_id,
                    "prokerala_result_id": input_id,
                    "algorithm_result_ids": algorithm_ids,
                    "patient_id": patient_id,
                    "algorithm_version": ALGORITHM_VERSION,
                    "source": "chart_pipeline",
                    "status": "complete",
                    "most_probable": _shrink(response.get("most_probable")),
                    "top_diseases": _shrink(response.get("top_diseases")),
                }
            )

            self.repository.save(
                internal_user_id,
                "combined_results",
                combined_id,
                combined_document,
            )

            log.info(
                "persistence_step_12_combined_save_completed",
                extra={
                    "operation": "save_generation",
                    "patient_id": patient_id,
                    "input_id": input_id,
                    "combined_id": combined_id,
                },
            )

        except Exception as exc:
            log.exception(
                "persistence_step_12_combined_save_failed",
                extra={
                    "operation": "save_generation",
                    "patient_id": patient_id,
                    "input_id": input_id,
                    "combined_id": combined_id,
                    "collection": "combined_results",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise

        # ---------------------------------------------------------
        # STEP 7: Save audit event
        # ---------------------------------------------------------
        audit_id = algorithm_result_id(
            input_id,
            "chart_created",
        )

        log.info(
            "persistence_step_13_audit_save_started",
            extra={
                "operation": "save_generation",
                "patient_id": patient_id,
                "input_id": input_id,
                "audit_id": audit_id,
            },
        )

        try:
            self.repository.save(
                internal_user_id,
                "audit_events",
                audit_id,
                {
                    "record_type": "audit",
                    "action": "chart_generated",
                    "input_id": input_id,
                    "patient_id": patient_id,
                    "source": "api",
                },
            )

            log.info(
                "persistence_step_14_audit_save_completed",
                extra={
                    "operation": "save_generation",
                    "patient_id": patient_id,
                    "input_id": input_id,
                    "audit_id": audit_id,
                },
            )

        except Exception as exc:
            log.exception(
                "persistence_step_14_audit_save_failed",
                extra={
                    "operation": "save_generation",
                    "patient_id": patient_id,
                    "input_id": input_id,
                    "audit_id": audit_id,
                    "collection": "audit_events",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise

        # ---------------------------------------------------------
        # COMPLETE
        # ---------------------------------------------------------
        log.info(
            "persistence_save_generation_completed",
            extra={
                "operation": "save_generation",
                "patient_id": patient_id,
                "input_id": input_id,
                "combined_id": combined_id,
                "algorithm_ids_count": len(algorithm_ids),
            },
        )

        return {
            "input_id": input_id,
            "combined_result_id": combined_id,
        }

    def save_combined_module(
        self, internal_user_id: str, patient_id: str, final_output: dict
    ) -> str:
        binding = self.repository.get(internal_user_id, "patients", patient_id) or {}
        input_id = binding.get("input_id") or patient_id
        doc_id = algorithm_result_id(str(input_id), "module_c")
        self.repository.save(
            internal_user_id,
            "combined_results",
            doc_id,
            _fit(
                {
                    "record_type": "combined",
                    "combined_result_id": doc_id,
                    "input_id": input_id,
                    "patient_id": patient_id,
                    "algorithm_version": ALGORITHM_VERSION,
                    "source": "combine_output",
                    "status": "complete",
                    "output": _shrink(final_output),
                }
            ),
        )
        return doc_id

    def save_chat_turn(
        self,
        internal_user_id: str,
        session_id: str,
        patient_id: str,
        role: str,
        text: str,
        turn: int,
    ) -> None:
        existing = (
            self.repository.get(internal_user_id, "chat_sessions", session_id) or {}
        )
        turns = list(existing.get("turns") or [])
        turns.append({"role": role, "text": text[:4000], "turn": turn})
        self.repository.save(
            internal_user_id,
            "chat_sessions",
            session_id,
            {
                "record_type": "chat",
                "session_id": session_id,
                "patient_id": patient_id,
                "input_id": (
                    self.repository.get(internal_user_id, "patients", patient_id) or {}
                ).get("input_id"),
                "source": "chat",
                "status": "open",
                "turns": turns[-100:],
            },
        )
