"""Persist chart lineage under the verified application user."""

from __future__ import annotations

import json
from typing import Any

from app_core.identifiers import ALGORITHM_VERSION, algorithm_result_id, birth_key, input_id_for

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

    def input_identity(self, internal_user_id: str, chart_input: dict) -> tuple[str, str]:
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
        input_id, birth = self.input_identity(internal_user_id, chart_input)
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
        self.repository.bind_patient(internal_user_id, patient_id, input_id)
        self.repository.save(
            internal_user_id,
            "prokerala_results",
            input_id,
            _fit({
                "record_type": "prokerala",
                "input_id": input_id,
                "patient_id": patient_id,
                "source": source,
                "status": "stored",
                "ascendant": response.get("ascendant"),
                "planets": response.get("planets"),
                "houses": response.get("houses"),
                "data_source": source,
            }),
        )

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
        for name in algorithm_names:
            if name not in response:
                continue
            doc_id = algorithm_result_id(input_id, name)
            algorithm_ids.append(doc_id)
            self.repository.save(
                internal_user_id,
                "algorithm_results",
                doc_id,
                _fit({
                    "record_type": "algorithm",
                    "algorithm": name,
                    "algorithm_version": ALGORITHM_VERSION,
                    "input_id": input_id,
                    "prokerala_result_id": input_id,
                    "patient_id": patient_id,
                    "source": "rules_engine",
                    "status": "complete",
                    "output": _shrink(response.get(name)),
                }),
            )

        combined_id = algorithm_result_id(input_id, "chart_summary")
        self.repository.save(
            internal_user_id,
            "combined_results",
            combined_id,
            _fit({
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
            }),
        )
        self.repository.save(
            internal_user_id,
            "audit_events",
            algorithm_result_id(input_id, "chart_created"),
            {
                "record_type": "audit",
                "action": "chart_generated",
                "input_id": input_id,
                "patient_id": patient_id,
                "source": "api",
            },
        )
        return {"input_id": input_id, "combined_result_id": combined_id}

    def save_combined_module(self, internal_user_id: str, patient_id: str, final_output: dict) -> str:
        binding = self.repository.get(internal_user_id, "patients", patient_id) or {}
        input_id = binding.get("input_id") or patient_id
        doc_id = algorithm_result_id(str(input_id), "module_c")
        self.repository.save(
            internal_user_id,
            "combined_results",
            doc_id,
            _fit({
                "record_type": "combined",
                "combined_result_id": doc_id,
                "input_id": input_id,
                "patient_id": patient_id,
                "algorithm_version": ALGORITHM_VERSION,
                "source": "combine_output",
                "status": "complete",
                "output": _shrink(final_output),
            }),
        )
        return doc_id

    def save_chat_turn(self, internal_user_id: str, session_id: str, patient_id: str, role: str, text: str, turn: int) -> None:
        existing = self.repository.get(internal_user_id, "chat_sessions", session_id) or {}
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
                "input_id": (self.repository.get(internal_user_id, "patients", patient_id) or {}).get("input_id"),
                "source": "chat",
                "status": "open",
                "turns": turns[-100:],
            },
        )
