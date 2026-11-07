from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg

from ..events import EventBus
from ..ids import new_id
from ..models import (
    ClaimNature,
    ConfidenceLevel,
    DecisionAction,
    DecisionTargetType,
    HumanDecision,
    MatchBasis,
    MatchStatus,
    PolicyDeny,
    SupportLevel,
)
from ..store.repo import Repo, _norm_row

_SUPPORT_TO_LEGACY_STATUS = {
    "documente": "confirmed",
    "corrobore": "confirmed",
    "a_confirmer": "hypothesis",
    "contradictoire": "contradicted",
    "non_etabli": "hypothesis",
}

_SUPPORT_TO_LEGACY_TEXT = {
    "documente": "documenté",
    "corrobore": "corroboré",
    "a_confirmer": "à confirmer",
    "contradictoire": "contradictoire",
    "non_etabli": "non établi",
}


def normalize_identifier(value: str) -> str:
    """Normalisation des identifiants externes (T6.2) : casse et separateurs usuels retires."""
    return re.sub(r"[\s.\-_/]", "", str(value).strip().lower())


def _j(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return json.loads(value)
    return list(value)


class GraphService:
    """Graphe de connaissances par investigation (CON-09/CON-10, T6).

    Rapprochement conservateur : rattachement automatique UNIQUEMENT sur identifiant
    externe exact (T6.5) ; toute autre correspondance reste une proposition soumise a
    validation humaine (T6.4, C5-11). Fusions/separations non destructives et reversibles
    (C6-06/C6-07). Contradictions conservees (T6.6). Confiance multidimensionnelle
    qualitative, sans score agrege (T6.7, B5, C3-07). Le critere d'objectif suffisamment
    etaye (V1.4, T4.6) est evalue ici, cote moteur.
    """

    def __init__(self, pool: asyncpg.Pool, repo: Repo, bus: EventBus, registry: Any = None):
        self.pool = pool
        self.repo = repo
        self.bus = bus
        self.registry = registry

    def _trust_levels(self) -> dict[str, str]:
        if self.registry is None:
            return {}
        return {c["id"]: c["trust_level"] for c in self.registry.list()}

    async def _entity_exists(self, conn, investigation_id: str, entity_id: str) -> bool:
        row = await conn.fetchrow(
            "SELECT 1 FROM entities WHERE id = $1 AND investigation_id = $2", entity_id, investigation_id
        )
        return row is not None

    async def upsert_entity(
        self,
        investigation_id: str,
        *,
        kind: str,
        data: dict[str, Any],
        identifiers: Optional[dict[str, str]] = None,
        branch_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Cree l'entite ou la rattache sur identifiant externe exact (seule automatisation, T6.5)."""
        identifiers = identifiers or {}
        normalized = {str(scheme).lower(): normalize_identifier(value) for scheme, value in identifiers.items()}
        normalized = {scheme: value for scheme, value in normalized.items() if value}
        entity_id: Optional[str] = None
        matched = "created"
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", investigation_id)
                for scheme, value in normalized.items():
                    row = await conn.fetchrow(
                        "SELECT entity_id FROM entity_identifiers WHERE investigation_id = $1 AND scheme = $2 AND value_normalisee = $3",
                        investigation_id,
                        scheme,
                        value,
                    )
                    if row is not None:
                        entity_id = row["entity_id"]
                        matched = "exact_identifier"
                        break
                if entity_id is None:
                    entity_id = new_id("ent")
                    await conn.execute(
                        "INSERT INTO entities (id, investigation_id, kind, data) VALUES ($1, $2, $3, $4::jsonb)",
                        entity_id,
                        investigation_id,
                        kind,
                        _j(data),
                    )
                else:
                    await conn.execute(
                        "UPDATE entities SET data = data || $2::jsonb, updated_at = now() WHERE id = $1",
                        entity_id,
                        _j(data),
                    )
                for scheme, value in normalized.items():
                    await conn.execute(
                        "INSERT INTO entity_identifiers (id, investigation_id, entity_id, scheme, value_normalisee) "
                        "VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING",
                        new_id("eid"),
                        investigation_id,
                        entity_id,
                        scheme,
                        value,
                    )
        await self.bus.emit(
            type="entity.created" if matched == "created" else "entity.attached",
            investigation_id=investigation_id,
            branch_id=branch_id,
            payload={"entity_id": entity_id, "kind": kind, "matched": matched},
        )
        return {"entity_id": entity_id, "matched": matched}

    async def add_relation(
        self,
        investigation_id: str,
        *,
        branch_id: Optional[str],
        src_id: str,
        dst_id: str,
        type: str,
        support_level: SupportLevel = SupportLevel.A_CONFIRMER,
        direction: str = "none",
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
        proof_ids: Optional[list[str]] = None,
        derivation: str = "ia",
        match_proposal_id: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        support = support_level.value if isinstance(support_level, SupportLevel) else str(support_level)
        payload = dict(data or {})
        payload["derivation"] = derivation
        row = _norm_row(
            await self.pool.fetchrow(
                "INSERT INTO relations (id, investigation_id, branch_id, src_id, dst_id, type, status, direction, "
                "valid_from, valid_to, proof_ids, support_level, human_decision, match_proposal_id, data) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, 'unexamined', $13, $14::jsonb) RETURNING *",
                new_id("rel"),
                investigation_id,
                branch_id,
                src_id,
                dst_id,
                type,
                _SUPPORT_TO_LEGACY_STATUS.get(support, "hypothesis"),
                direction,
                valid_from,
                valid_to,
                _j(proof_ids or []),
                support,
                match_proposal_id,
                _j(payload),
            )
        )
        await self.bus.emit(
            type="relation.created",
            investigation_id=investigation_id,
            branch_id=branch_id,
            payload={"relation_id": row["id"], "type": type, "src_id": src_id, "dst_id": dst_id, "support_level": support},
        )
        return row

    async def compute_confidence(
        self,
        investigation_id: str,
        proof_ids: list[str],
        derivation: str,
        human_decision: str,
    ) -> dict[str, str]:
        """Six dimensions qualitatives T6.7/B5, explicables, jamais de score agrege (C3-07)."""
        proofs = await self.pool.fetch(
            "SELECT connector_id, proof_sha256, fetched_at FROM proof_refs WHERE investigation_id = $1 AND id = ANY($2::text[])",
            investigation_id,
            proof_ids or ["__none__"],
        )
        trusts = self._trust_levels()
        levels = [trusts.get(p["connector_id"], "experimental") for p in proofs if p["connector_id"]]
        if any(level == "official" for level in levels):
            fiabilite_source = ConfidenceLevel.HAUTE.value
        elif any(level == "approved" for level in levels):
            fiabilite_source = ConfidenceLevel.MOYENNE.value
        elif levels:
            fiabilite_source = ConfidenceLevel.FAIBLE.value
        else:
            fiabilite_source = ConfidenceLevel.INCONNUE.value
        qualite_extraction = {"source": "haute", "ia": "moyenne"}.get(derivation, "faible")
        distinct_sha = {p["proof_sha256"] for p in proofs}
        if len(distinct_sha) >= 2:
            solidite = ConfidenceLevel.HAUTE.value
        elif len(distinct_sha) == 1:
            solidite = ConfidenceLevel.MOYENNE.value
        else:
            solidite = ConfidenceLevel.FAIBLE.value
        connectors = {p["connector_id"] for p in proofs if p["connector_id"]}
        if len(connectors) >= 2:
            coherence = ConfidenceLevel.HAUTE.value
        elif len(connectors) == 1:
            coherence = ConfidenceLevel.MOYENNE.value
        else:
            coherence = ConfidenceLevel.INCONNUE.value
        if proofs:
            newest = max(p["fetched_at"] for p in proofs)
            age_days = (datetime.now(timezone.utc) - newest).days
            if age_days <= 90:
                fraicheur = ConfidenceLevel.HAUTE.value
            elif age_days <= 365:
                fraicheur = ConfidenceLevel.MOYENNE.value
            else:
                fraicheur = ConfidenceLevel.FAIBLE.value
        else:
            fraicheur = ConfidenceLevel.INCONNUE.value
        validation = {
            HumanDecision.VALIDATED.value: ConfidenceLevel.HAUTE.value,
            HumanDecision.REJECTED.value: ConfidenceLevel.FAIBLE.value,
        }.get(human_decision, ConfidenceLevel.INCONNUE.value)
        return {
            "fiabilite_source": fiabilite_source,
            "qualite_extraction": qualite_extraction,
            "solidite_preuves": solidite,
            "coherence_intersources": coherence,
            "fraicheur": fraicheur,
            "validation_humaine": validation,
        }

    async def add_assertion(
        self,
        investigation_id: str,
        *,
        branch_id: Optional[str],
        statement: str,
        nature: ClaimNature = ClaimNature.CONCLUSION_ANALYTIQUE,
        support_level: SupportLevel = SupportLevel.A_CONFIRMER,
        proof_ids: Optional[list[str]] = None,
        decisive: bool = False,
        derivation: str = "ia",
        contradicted_by: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        proof_ids = proof_ids or []
        contradicted_by = contradicted_by or []
        nature_value = nature.value if isinstance(nature, ClaimNature) else str(nature)
        support = support_level.value if isinstance(support_level, SupportLevel) else str(support_level)
        confidence = await self.compute_confidence(investigation_id, proof_ids, derivation, HumanDecision.UNEXAMINED.value)
        if contradicted_by:
            support = SupportLevel.CONTRADICTOIRE.value
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = _norm_row(
                    await conn.fetchrow(
                        "INSERT INTO assertions (id, investigation_id, branch_id, statement, nature, support, support_level, "
                        "human_decision, proof_ids, confidence, decisive, contradicted_by) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, 'unexamined', $8::jsonb, $9::jsonb, $10, $11::jsonb) RETURNING *",
                        new_id("assert"),
                        investigation_id,
                        branch_id,
                        statement,
                        nature_value,
                        _SUPPORT_TO_LEGACY_TEXT.get(support, "à confirmer"),
                        support,
                        _j(proof_ids),
                        _j(confidence),
                        decisive,
                        _j(contradicted_by),
                    )
                )
                for other_id in contradicted_by:
                    await conn.execute(
                        "UPDATE assertions SET support_level = 'contradictoire', "
                        "contradicted_by = contradicted_by || $3::jsonb, updated_at = now() "
                        "WHERE id = $1 AND investigation_id = $2 AND superseded_by IS NULL",
                        other_id,
                        investigation_id,
                        _j([row["id"]]),
                    )
        event_type = "assertion.contradicted" if contradicted_by else "assertion.created"
        await self.bus.emit(
            type=event_type,
            investigation_id=investigation_id,
            branch_id=branch_id,
            payload={"assertion_id": row["id"], "nature": nature_value, "support_level": support, "contradicted_by": contradicted_by},
        )
        return row

    async def propose_match(
        self,
        investigation_id: str,
        *,
        entity_a: str,
        entity_b: str,
        basis: MatchBasis = MatchBasis.SIMILARITY,
        justification: str = "",
        confidence: ConfidenceLevel = ConfidenceLevel.FAIBLE,
        branch_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Proposition de correspondance (T6.4) : jamais de fusion automatique hors identifiant exact."""
        if entity_a == entity_b:
            raise PolicyDeny("match_auto_interdit", "graphe")
        basis_value = basis.value if isinstance(basis, MatchBasis) else str(basis)
        conf_value = confidence.value if isinstance(confidence, ConfidenceLevel) else str(confidence)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", investigation_id)
                for eid in (entity_a, entity_b):
                    if not await self._entity_exists(conn, investigation_id, eid):
                        raise PolicyDeny(f"entite_inconnue:{eid}", "graphe")
                existing = await conn.fetchrow(
                    "SELECT * FROM match_proposals WHERE investigation_id = $1 AND status = 'proposed' "
                    "AND ((entity_a = $2 AND entity_b = $3) OR (entity_a = $3 AND entity_b = $2))",
                    investigation_id,
                    entity_a,
                    entity_b,
                )
                if existing is not None:
                    return _norm_row(existing)
                row = _norm_row(
                    await conn.fetchrow(
                        "INSERT INTO match_proposals (id, investigation_id, entity_a, entity_b, basis, justification, confidence, status) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, 'proposed') RETURNING *",
                        new_id("match"),
                        investigation_id,
                        entity_a,
                        entity_b,
                        basis_value,
                        justification,
                        conf_value,
                    )
                )
        await self.bus.emit(
            type="match.proposed",
            investigation_id=investigation_id,
            branch_id=branch_id,
            payload={"match_id": row["id"], "entity_a": entity_a, "entity_b": entity_b, "basis": basis_value, "confidence": conf_value},
        )
        return row

    async def decide(
        self,
        investigation_id: str,
        *,
        target_type: DecisionTargetType | str,
        target_id: str,
        action: DecisionAction | str,
        payload: Optional[dict[str, Any]] = None,
        reverts: Optional[str] = None,
        actor: Optional[str] = None,
        branch_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Applique une decision humaine supervisee, historisee et reversible (C6, A.11.4, CON-09)."""
        payload = dict(payload or {})
        ttype = DecisionTargetType(target_type)
        act = DecisionAction(action)
        events: list[tuple[str, dict[str, Any]]] = []
        decision: dict[str, Any]
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                decision = _norm_row(
                    await conn.fetchrow(
                        "INSERT INTO decisions (id, investigation_id, assertion_id, target_type, target_id, action, payload, reverts) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8) RETURNING *",
                        new_id("dec"),
                        investigation_id,
                        target_id if ttype == DecisionTargetType.ASSERTION else None,
                        ttype.value,
                        target_id,
                        act.value,
                        _j(payload),
                        reverts,
                    )
                )
                if act in (DecisionAction.VALIDATE, DecisionAction.REJECT):
                    hd = HumanDecision.VALIDATED.value if act == DecisionAction.VALIDATE else HumanDecision.REJECTED.value
                    if ttype == DecisionTargetType.ASSERTION:
                        current = await conn.fetchrow(
                            "SELECT human_decision, confidence FROM assertions WHERE id = $1 AND investigation_id = $2",
                            target_id, investigation_id,
                        )
                        if current is None:
                            raise PolicyDeny(f"assertion_inconnue:{target_id}", "graphe")
                        if current["human_decision"] != HumanDecision.UNEXAMINED.value:
                            raise PolicyDeny("decision_deja_prise_utiliser_undo", "graphe")
                        prev_conf = current["confidence"] if isinstance(current["confidence"], dict) else json.loads(current["confidence"] or "{}")
                        previous_validation = prev_conf.get("validation_humaine", ConfidenceLevel.INCONNUE.value)
                        hd_conf = ConfidenceLevel.HAUTE.value if act == DecisionAction.VALIDATE else ConfidenceLevel.FAIBLE.value
                        await conn.execute(
                            "UPDATE assertions SET human_decision = $2, confidence = jsonb_set(coalesce(confidence,'{}'::jsonb), '{validation_humaine}', to_jsonb($4::text)), updated_at = now() "
                            "WHERE id = $1 AND investigation_id = $3",
                            target_id, hd, investigation_id, hd_conf,
                        )
                        await conn.execute(
                            "UPDATE decisions SET payload = payload || $2::jsonb WHERE id = $1",
                            decision["id"], _j({"previous_validation": previous_validation}),
                        )
                        decision["payload"] = {**decision["payload"], "previous_validation": previous_validation}
                    elif ttype == DecisionTargetType.RELATION:
                        current = await conn.fetchrow(
                            "SELECT human_decision FROM relations WHERE id = $1 AND investigation_id = $2",
                            target_id, investigation_id,
                        )
                        if current is None:
                            raise PolicyDeny(f"relation_inconnue:{target_id}", "graphe")
                        if current["human_decision"] != HumanDecision.UNEXAMINED.value:
                            raise PolicyDeny("decision_deja_prise_utiliser_undo", "graphe")
                        await conn.execute(
                            "UPDATE relations SET human_decision = $2, updated_at = now() WHERE id = $1 AND investigation_id = $3",
                            target_id, hd, investigation_id,
                        )
                    elif ttype == DecisionTargetType.MATCH_PROPOSAL:
                        prop = await conn.fetchrow(
                            "SELECT status FROM match_proposals WHERE id = $1 AND investigation_id = $2",
                            target_id, investigation_id,
                        )
                        if prop is None:
                            raise PolicyDeny(f"proposition_inconnue:{target_id}", "graphe")
                        if prop["status"] != MatchStatus.PROPOSED.value:
                            raise PolicyDeny("proposition_deja_traitee_utiliser_undo", "graphe")
                        await conn.execute(
                            "UPDATE match_proposals SET status = $2, decided_by = $3, updated_at = now() WHERE id = $1 AND investigation_id = $4",
                            target_id, hd, actor, investigation_id,
                        )
                        if act == DecisionAction.REJECT:
                            to_degrade = await conn.fetch(
                                "SELECT id, support_level FROM relations WHERE investigation_id = $1 AND match_proposal_id = $2 AND support_level <> 'contradictoire' AND support_level <> 'a_confirmer'",
                                investigation_id, target_id,
                            )
                            degraded_support = {row["id"]: row["support_level"] for row in to_degrade}
                            if degraded_support:
                                await conn.execute(
                                    "UPDATE relations SET support_level = 'a_confirmer', human_decision = 'unexamined', updated_at = now() "
                                    "WHERE investigation_id = $1 AND id = ANY($2::text[])",
                                    investigation_id, list(degraded_support.keys()),
                                )
                                await conn.execute(
                                    "UPDATE decisions SET payload = payload || $2::jsonb WHERE id = $1",
                                    decision["id"], _j({"degraded_support": degraded_support}),
                                )
                                decision["payload"] = {**decision["payload"], "degraded_support": degraded_support}
                            for row in to_degrade:
                                events.append(("relation.revaluated", {"relation_id": row["id"], "cause": "match_rejected"}))
                            events.append(("match.rejected", {"match_id": target_id}))
                        else:
                            events.append(("match.validated", {"match_id": target_id}))
                    else:
                        raise PolicyDeny("action_non_autorisee_sur_entite", "graphe")
                elif act == DecisionAction.MERGE:
                    if ttype == DecisionTargetType.MATCH_PROPOSAL:
                        prop = await conn.fetchrow(
                            "SELECT entity_a, entity_b, status FROM match_proposals WHERE id = $1 AND investigation_id = $2",
                            target_id, investigation_id,
                        )
                        if prop is None:
                            raise PolicyDeny("proposition_inconnue", "graphe")
                        if prop["status"] != MatchStatus.PROPOSED.value:
                            raise PolicyDeny("proposition_deja_traitee_utiliser_undo", "graphe")
                        canonical, other = prop["entity_a"], prop["entity_b"]
                        await conn.execute(
                            "UPDATE match_proposals SET status = 'validated', decided_by = $2, updated_at = now() WHERE id = $1",
                            target_id, actor,
                        )
                    else:
                        canonical = payload.get("entity_a")
                        other = target_id
                        if not canonical:
                            raise PolicyDeny("entite_canonique_requise", "graphe")
                    for eid in (canonical, other):
                        if not await self._entity_exists(conn, investigation_id, eid):
                            raise PolicyDeny(f"entite_inconnue:{eid}", "graphe")
                    if canonical == other:
                        raise PolicyDeny("fusion_identique", "graphe")
                    await conn.execute(
                        "UPDATE entities SET merged_into = $2, updated_at = now() WHERE id = $1 AND investigation_id = $3 AND merged_into IS NULL",
                        other, canonical, investigation_id,
                    )
                    events.append(("entity.merged", {"entity_id": other, "merged_into": canonical}))
                elif act == DecisionAction.UNDO:
                    if not reverts:
                        raise PolicyDeny("undo_sans_cible", "graphe")
                    orig = await conn.fetchrow(
                        "SELECT * FROM decisions WHERE id = $1 AND investigation_id = $2", reverts, investigation_id
                    )
                    if orig is None:
                        raise PolicyDeny("decision_inconnue", "graphe")
                    later = await conn.fetchrow(
                        "SELECT d.id FROM decisions d "
                        "WHERE d.investigation_id = $1 AND d.target_id = $2 AND d.created_at > $3 "
                        "AND d.id <> $4 AND NOT EXISTS (SELECT 1 FROM decisions u WHERE u.reverts = d.id) LIMIT 1",
                        investigation_id, orig["target_id"], orig["created_at"], decision["id"],
                    )
                    if later is not None:
                        raise PolicyDeny("decision_posterieure_presente", "graphe")
                    orig_payload = orig["payload"] if isinstance(orig["payload"], dict) else json.loads(orig["payload"] or "{}")
                    orig_action = orig["action"]
                    orig_target_type = orig["target_type"]
                    orig_target = orig["target_id"]
                    if orig_action == DecisionAction.MERGE.value:
                        if orig_target_type == "match_proposal":
                            prop = await conn.fetchrow("SELECT entity_a, entity_b FROM match_proposals WHERE id = $1", orig_target)
                            canonical, other = prop["entity_a"], prop["entity_b"]
                        else:
                            canonical = orig_payload.get("entity_a")
                            other = orig_target
                        await conn.execute(
                            "UPDATE entities SET merged_into = NULL, updated_at = now() WHERE id = $1 AND merged_into = $2",
                            other, canonical,
                        )
                        await conn.execute(
                            "UPDATE match_proposals SET status = 'proposed', decided_by = NULL, updated_at = now() WHERE id = $1",
                            orig_target,
                        )
                        events.append(("entity.unmerged", {"entity_id": other, "merged_into": None}))
                    elif orig_action in (DecisionAction.VALIDATE.value, DecisionAction.REJECT.value):
                        if orig_target_type == "assertion":
                            previous_validation = orig_payload.get("previous_validation", ConfidenceLevel.INCONNUE.value)
                            await conn.execute(
                                "UPDATE assertions SET human_decision = 'unexamined', "
                                "confidence = jsonb_set(coalesce(confidence,'{}'::jsonb), '{validation_humaine}', to_jsonb($2::text)), updated_at = now() "
                                "WHERE id = $1 AND investigation_id = $3",
                                orig_target, previous_validation, investigation_id,
                            )
                        elif orig_target_type == "relation":
                            await conn.execute(
                                "UPDATE relations SET human_decision = 'unexamined', updated_at = now() WHERE id = $1 AND investigation_id = $2",
                                orig_target, investigation_id,
                            )
                        elif orig_target_type == "match_proposal":
                            await conn.execute(
                                "UPDATE match_proposals SET status = 'proposed', decided_by = NULL, updated_at = now() WHERE id = $1",
                                orig_target,
                            )
                            degraded_support = orig_payload.get("degraded_support") or {}
                            restored = await conn.fetch(
                                "UPDATE relations SET human_decision = 'unexamined', updated_at = now() WHERE investigation_id = $1 AND match_proposal_id = $2 RETURNING id",
                                investigation_id, orig_target,
                            )
                            for rel_id, previous_level in degraded_support.items():
                                await conn.execute(
                                    "UPDATE relations SET support_level = $2, updated_at = now() WHERE id = $1 AND investigation_id = $3",
                                    rel_id, previous_level, investigation_id,
                                )
                                events.append(("relation.revaluated", {"relation_id": rel_id, "cause": "match_undo_restored"}))
                            for row in restored:
                                if row["id"] not in degraded_support:
                                    events.append(("relation.revaluated", {"relation_id": row["id"], "cause": "match_undo"}))
                        events.append(("decision.undone", {"undone": reverts}))
                    elif orig_action == DecisionAction.CORRECT.value:
                        correction_id = orig_payload.get("correction_id")
                        if correction_id:
                            await conn.execute(
                                "UPDATE assertions SET superseded_by = $2, updated_at = now() WHERE id = $1 AND superseded_by IS NULL",
                                correction_id, orig_target,
                            )
                            await conn.execute("UPDATE assertions SET superseded_by = NULL, updated_at = now() WHERE id = $1", orig_target)
                        events.append(("assertion.restored", {"assertion_id": orig_target, "correction_id": correction_id}))
                    else:
                        raise PolicyDeny("action_non_reversible", "graphe")
                elif act == DecisionAction.CORRECT:
                    if ttype != DecisionTargetType.ASSERTION:
                        raise PolicyDeny("correction_reservee_aux_assertions", "graphe")
                    orig = await conn.fetchrow(
                        "SELECT * FROM assertions WHERE id = $1 AND investigation_id = $2", target_id, investigation_id
                    )
                    if orig is None:
                        raise PolicyDeny("assertion_inconnue", "graphe")
                    new_statement = payload.get("statement")
                    if not new_statement:
                        raise PolicyDeny("enonce_corrige_requis", "graphe")
                    new_support = payload.get("support_level", SupportLevel.A_CONFIRMER.value)
                    new_nature = payload.get("nature", orig["nature"])
                    new_proof_ids = payload.get("proof_ids", _as_list(orig["proof_ids"]))
                    confidence = await self.compute_confidence(investigation_id, new_proof_ids, payload.get("derivation", "source"), HumanDecision.UNEXAMINED.value)
                    new = _norm_row(
                        await conn.fetchrow(
                            "INSERT INTO assertions (id, investigation_id, branch_id, statement, nature, support, support_level, human_decision, proof_ids, confidence, decisive, superseded_by) "
                            "VALUES ($1, $2, $3, $4, $5, $6, $7, 'unexamined', $8::jsonb, $9::jsonb, $10, NULL) RETURNING *",
                            new_id("assert"), investigation_id, orig["branch_id"], new_statement, new_nature,
                            _SUPPORT_TO_LEGACY_TEXT.get(new_support, "documenté"), new_support,
                            _j(new_proof_ids), _j(confidence), bool(orig["decisive"]),
                        )
                    )
                    await conn.execute(
                        "UPDATE assertions SET superseded_by = $2, updated_at = now() WHERE id = $1", target_id, new["id"]
                    )
                    await conn.execute(
                        "UPDATE decisions SET payload = payload || $2::jsonb WHERE id = $1",
                        decision["id"], _j({"correction_id": new["id"]}),
                    )
                    decision = _norm_row(await conn.fetchrow("SELECT * FROM decisions WHERE id = $1", decision["id"]))
                    events.append(("assertion.corrected", {"assertion_id": target_id, "correction_id": new["id"]}))
                    events.append(("synthesis.stale", {"cause": "assertion_corrected", "assertion_id": target_id}))
                elif act == DecisionAction.ANNOTATE:
                    events.append(("decision.applied", {}))
                elif act == DecisionAction.PROPOSE_MATCH:
                    raise PolicyDeny("utiliser_post_matches", "graphe")
                else:
                    raise PolicyDeny("action_inconnue", "graphe")
        for event_type, event_payload in events:
            merged_payload = {"decision_id": decision["id"], "action": act.value, "target_type": ttype.value, "target_id": target_id, **event_payload}
            await self.bus.emit(
                type=event_type,
                investigation_id=investigation_id,
                branch_id=branch_id,
                payload=merged_payload,
            )
        await self.bus.emit(
            type="decision.applied",
            investigation_id=investigation_id,
            branch_id=branch_id,
            payload={"decision_id": decision["id"], "action": act.value, "target_type": ttype.value, "target_id": target_id, "reverts": reverts},
        )
        return decision

    async def list_entities(self, investigation_id: str, *, include_merged: bool = False, limit: int = 200, offset: int = 0) -> list[dict]:
        query = "SELECT * FROM entities WHERE investigation_id = $1"
        if not include_merged:
            query += " AND merged_into IS NULL"
        query += " ORDER BY created_at LIMIT $2 OFFSET $3"
        return [_norm_row(r) for r in await self.pool.fetch(query, investigation_id, limit, offset)]

    async def list_identifiers(self, investigation_id: str, entity_id: str) -> list[dict]:
        return [_norm_row(r) for r in await self.pool.fetch(
            "SELECT scheme, value_normalisee FROM entity_identifiers WHERE investigation_id = $1 AND entity_id = $2 ORDER BY scheme",
            investigation_id, entity_id,
        )]

    async def list_relations(self, investigation_id: str, *, branch_id: Optional[str] = None, limit: int = 500, offset: int = 0) -> list[dict]:
        query = "SELECT * FROM relations WHERE investigation_id = $1"
        args: list[Any] = [investigation_id]
        if branch_id:
            query += " AND branch_id = $2"
            args.append(branch_id)
            query += " ORDER BY created_at LIMIT $3 OFFSET $4"
            args.extend([limit, offset])
        else:
            query += " ORDER BY created_at LIMIT $2 OFFSET $3"
            args.extend([limit, offset])
        return [_norm_row(r) for r in await self.pool.fetch(query, *args)]

    async def list_assertions(self, investigation_id: str, *, branch_id: Optional[str] = None, include_superseded: bool = False) -> list[dict]:
        query = "SELECT * FROM assertions WHERE investigation_id = $1"
        args: list[Any] = [investigation_id]
        if branch_id:
            query += " AND branch_id = $2"
            args.append(branch_id)
        if not include_superseded:
            query += " AND superseded_by IS NULL"
        query += " ORDER BY created_at"
        return [_norm_row(r) for r in await self.pool.fetch(query, *args)]

    async def list_matches(self, investigation_id: str, *, status: Optional[str] = None) -> list[dict]:
        query = "SELECT * FROM match_proposals WHERE investigation_id = $1"
        args: list[Any] = [investigation_id]
        if status:
            query += " AND status = $2"
            args.append(status)
        query += " ORDER BY created_at"
        return [_norm_row(r) for r in await self.pool.fetch(query, *args)]

    async def list_decisions(self, investigation_id: str, limit: int = 200) -> list[dict]:
        return [_norm_row(r) for r in await self.pool.fetch(
            "SELECT * FROM decisions WHERE investigation_id = $1 ORDER BY created_at LIMIT $2",
            investigation_id, limit,
        )]

    async def entity_sheet(self, investigation_id: str, entity_id: str) -> Optional[dict]:
        """Fiche d'entite (C5) : identifiants, relations entrantes/sortantes, branches concernees."""
        entity = _norm_row(await self.pool.fetchrow(
            "SELECT * FROM entities WHERE id = $1 AND investigation_id = $2", entity_id, investigation_id
        ))
        if entity is None:
            return None
        identifiers = await self.list_identifiers(investigation_id, entity_id)
        rel = await self.pool.fetch(
            "SELECT * FROM relations WHERE investigation_id = $1 AND (src_id = $2 OR dst_id = $2) ORDER BY created_at",
            investigation_id, entity_id,
        )
        relations_out = [r for r in rel if r["src_id"] == entity_id]
        relations_in = [r for r in rel if r["dst_id"] == entity_id]
        assertions = await self.list_assertions(investigation_id)
        branches = sorted({r["branch_id"] for r in relations_out + relations_in if r["branch_id"]} | {a["branch_id"] for a in assertions if a["branch_id"]})
        return {
            "entity": entity,
            "identifiers": identifiers,
            "relations_out": relations_out,
            "relations_in": relations_in,
            "branches": branches,
        }

    async def etayage(self, investigation_id: str, branch_id: Optional[str] = None) -> list[dict]:
        """Vue d'etayage (CON-10) : natures, six dimensions, double statut, preuves (C6, T6.7)."""
        assertions = await self.list_assertions(investigation_id, branch_id=branch_id)
        out = []
        for a in assertions:
            proof_ids = _as_list(a["proof_ids"])
            proofs = [_norm_row(r) for r in await self.pool.fetch(
                "SELECT id, proof_sha256, source_url, connector_id, fetched_at FROM proof_refs WHERE investigation_id = $1 AND id = ANY($2::text[])",
                investigation_id, proof_ids or ["__none__"],
            )]
            out.append({
                "id": a["id"],
                "branch_id": a["branch_id"],
                "statement": a["statement"],
                "nature": a["nature"],
                "support_level": a["support_level"],
                "human_decision": a["human_decision"],
                "decisive": a["decisive"],
                "confidence": a["confidence"] if isinstance(a["confidence"], dict) else json.loads(a["confidence"] or "{}"),
                "proofs": proofs,
                "contradicted_by": _as_list(a["contradicted_by"]),
                "superseded_by": a["superseded_by"],
                "created_at": a["created_at"].isoformat() if a["created_at"] else None,
            })
        return out

    async def objective_etaye(self, investigation_id: str, branch_id: Optional[str] = None) -> dict[str, Any]:
        """Critere V1.4 evalue par le moteur (T4.6) : chaque reponse decisive repose sur une
        source primaire (connecteur official) ou deux sources independantes concordantes,
        et aucune contradiction majeure non resolue (T6.6)."""
        trusts = self._trust_levels()
        assertions = await self.list_assertions(investigation_id, branch_id=branch_id)
        decisive = [a for a in assertions if a["decisive"]]
        decision_by_id = {a["id"]: a["human_decision"] for a in assertions}
        linked_by: dict[str, list[str]] = {}
        for a in assertions:
            for other in _as_list(a["contradicted_by"]):
                linked_by.setdefault(other, []).append(a["id"])
        contradictions = []
        for a in assertions:
            if a["support_level"] != SupportLevel.CONTRADICTOIRE.value or a["human_decision"] != HumanDecision.UNEXAMINED.value:
                continue
            partners = _as_list(a["contradicted_by"]) + linked_by.get(a["id"], [])
            if not any(decision_by_id.get(p, HumanDecision.UNEXAMINED.value) != HumanDecision.UNEXAMINED.value for p in partners):
                contradictions.append(a)
        reponses: list[dict[str, Any]] = []
        all_ok = bool(decisive)
        for a in decisive:
            proof_ids = _as_list(a["proof_ids"])
            proofs = await self.pool.fetch(
                "SELECT connector_id FROM proof_refs WHERE investigation_id = $1 AND id = ANY($2::text[])",
                investigation_id, proof_ids or ["__none__"],
            )
            connectors = sorted({p["connector_id"] for p in proofs if p["connector_id"]})
            levels = [trusts.get(c, "experimental") for c in connectors]
            primary = any(level == "official" for level in levels)
            independent = len(connectors) >= 2
            ok = primary or independent
            all_ok = all_ok and ok
            reponses.append({
                "id": a["id"],
                "statement": a["statement"],
                "nature": a["nature"],
                "base": "source_primaire" if primary else ("deux_sources_independantes" if independent else "insuffisant"),
                "connecteurs": connectors,
            })
        etaye = all_ok and not contradictions
        detail = []
        if not decisive:
            detail.append("aucune reponse decisive dans la branche")
        for r in reponses:
            if r["base"] == "insuffisant":
                detail.append(f"reponse decisive {r['id']} insuffisamment etayee (ni source primaire ni deux sources independantes)")
        for c in contradictions:
            detail.append(f"contradiction majeure non resolue: {c['id']}")
        return {
            "etaye": etaye,
            "reponses_decisives": reponses,
            "contradictions_majeures": [c["id"] for c in contradictions],
            "detail": detail,
        }
