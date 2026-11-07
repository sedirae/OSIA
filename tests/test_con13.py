"""CON-13 (D3/D7, T4.8, V1.4) : paramètres hiérarchisés, profils, valeurs par défaut non
permissives, TTL du cache source, quotas/seuils.

Vérifications : defaults non permissifs par accident (overrides clampés) ; restrictions
supérieures appliquées (profil > override, branche <= investigation) ; cache 24 h (B-ACC-06)."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from osia.api import create_app
from osia.models import LimitSet, validate_setting_value
from osia.policies.limits import limits_from_profile_row
from osia.tasks import TaskContext, handle_source_query

from conftest import make_investigation


class FakeProfile(dict):
    pass


def profile_row(rapide=True):
    base = {"rapide": (2, 12, 4, 120, 5), "standard": (4, 40, 12, 600, 20), "approfondi": (8, 100, 30, 1800, 100)}
    r, s, a, d, c = base["rapide" if rapide else "standard"]
    return FakeProfile(
        max_rebonds=r, max_source_requests=s, max_ai_calls=a, max_duration_seconds=d, max_cost_cents=c
    )


# ---------- Clamp des overrides (D3 §5.4, D7 §9.2, T4.8) ----------


def test_overrides_ne_peuvent_jamais_augmenter_au_dela_du_profil():
    """Un override ne peut que rabaisser : jamais de default permissif par accident."""
    limits = limits_from_profile_row(profile_row(), {"max_rebonds": 10, "max_cost_cents": 999, "max_source_requests": 1000})
    assert limits.max_rebonds == 2  # profil rapide, pas 10
    assert limits.max_cost_cents == 5
    assert limits.max_source_requests == 12


def test_overrides_peuvent_abaisser():
    limits = limits_from_profile_row(profile_row(), {"max_rebonds": 1, "max_ai_calls": 2})
    assert limits.max_rebonds == 1
    assert limits.max_ai_calls == 2


def test_garde_fous_v1_4_non_surchargeables_a_la_hausse():
    """V1.4 : 2 ops simultanées, 15 s HTTP, 60 s IA — T4.8 : non désactivables par surcharge."""
    limits = limits_from_profile_row(profile_row(), {"max_concurrent_external_ops": 50, "http_timeout_seconds": 3600, "ai_timeout_seconds": 600})
    assert limits.max_concurrent_external_ops == 2
    assert limits.http_timeout_seconds == 15
    assert limits.ai_timeout_seconds == 60
    # mais on peut les abaisser
    limits2 = limits_from_profile_row(profile_row(), {"http_timeout_seconds": 5})
    assert limits2.http_timeout_seconds == 5


def test_override_sous_borne_rejete_et_au_dessus_clampe():
    # sous la borne inférieure du schéma : rejeté (validation pydantic)
    with pytest.raises(ValidationError):
        limits_from_profile_row(profile_row(), {"max_rebonds": 0})
    # au-dessus du profil : clampé (jamais permissif par accident), pas rejeté
    assert limits_from_profile_row(profile_row(), {"max_rebonds": 11}).max_rebonds == 2


async def test_investigation_effective_limits_clampes_au_profil(engine):
    """Création d'investigation avec overrides supérieurs : effective_limits = profil (D7 §9.2)."""
    from osia.models import CreateInvestigationRequest

    inv = await engine.orchestrator.start_investigation(
        CreateInvestigationRequest(title="t", profile_id="rapide", limits={"max_rebonds": 10, "max_cost_cents": 500})
    )
    eff = inv["effective_limits"]
    if isinstance(eff, str):
        eff = json.loads(eff)
    assert eff["max_rebonds"] == 2
    assert eff["max_cost_cents"] == 5


# ---------- Validation des paramètres globaux (D7 §9.3) ----------


def test_validate_setting_value():
    assert validate_setting_value("paid_calls_enabled", True) is True
    assert validate_setting_value("global_monthly_cap_cents", 500) == 500
    assert validate_setting_value("source_cache_ttl_hours", 24) == 24
    with pytest.raises(ValueError):
        validate_setting_value("global_monthly_cap_cents", -1)
    with pytest.raises(ValueError):
        validate_setting_value("source_cache_ttl_hours", 0)
    with pytest.raises(ValueError):
        validate_setting_value("paid_calls_enabled", "oui")
    with pytest.raises(ValueError):
        validate_setting_value("cle_secrete", "x")  # inconnu / non modifiable


# ---------- Cache source avec TTL (V1.4 24 h, B-ACC-06, D4 §6.2) ----------


async def test_cache_set_get_et_expiration(engine):
    await engine.repo.cache_set("simulated.web", "q1", {"content": "abc"}, 24)
    hit = await engine.repo.cache_get("simulated.web", "q1")
    assert hit is not None and hit["cached"] is True and hit["content"] == "abc"
    assert hit["fetched_at"] and hit["expires_at"]
    assert await engine.repo.cache_get("simulated.web", "autre") is None
    # expiration : TTL négatif impossible (min 1 h) -> on force une entrée expirée en base
    await engine.pool.execute(
        "UPDATE source_cache SET expires_at = $1 WHERE connector_id = $2",
        datetime.now(timezone.utc) - timedelta(hours=1),
        "simulated.web",
    )
    assert await engine.repo.cache_get("simulated.web", "q1") is None
    purged = await engine.repo.cache_purge_expired()
    assert purged == 1


async def test_handler_reutilise_cache_sans_nouvel_appel(engine):
    inv = await make_investigation(engine)
    branches = await engine.repo.list_branches(inv["id"])
    task = await engine.repo.insert_task(
        investigation_id=inv["id"],
        branch_id=branches[0]["id"],
        kind="source_query",
        payload={"connector_id": "simulated.web", "query": "q-cache"},
        depth=0,
    )
    ctx = TaskContext(engine=engine)
    connector = engine.registry.get("simulated.web")
    # 1er appel : miss -> fetch réel (simulé) + mise en cache
    out1 = await handle_source_query(task, ctx)
    assert out1.get("cached") is not True
    assert connector.calls == ["q-cache"]
    # 2e appel : hit -> AUCUN nouvel appel externe (B-ACC-06)
    out2 = await handle_source_query(task, ctx)
    assert out2["cached"] is True
    assert connector.calls == ["q-cache"]  # pas de second fetch


# ---------- Seuils d'alerte budget (D3 §5.4) ----------


async def test_budget_warnings_approche_plafond(engine):
    from osia.models import OpKind

    inv = await make_investigation(engine)  # profil rapide : max_cost_cents = 5
    view = await engine.budgets.budget_view(inv["id"])
    assert any("payants désactivés" in w for w in view.warnings)  # V1.4 : budget 0 € au démarrage
    await engine.repo.set_setting("paid_calls_enabled", True)
    # réserve via une vraie opération autorisée (crée external_ops + réservation, T8.4)
    decision = await engine.policy.authorize(
        investigation_id=inv["id"],
        kind=OpKind.AI_CALL,
        target="simulated:simulated-1",
        is_paid=True,
        cost_estimated_cents=4,  # 80 % du plafond investigation (5 c)
    )
    assert decision.allowed
    view2 = await engine.budgets.budget_view(inv["id"])
    assert any("plafond investigation atteint à 80 %" in w for w in view2.warnings)


# ---------- API settings / profiles ----------


async def test_api_settings_get_put(engine):
    app = create_app(engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        r = await client.get("/api/v1/settings")
        assert r.status_code == 200
        s = r.json()["settings"]
        assert s["paid_calls_enabled"] is False  # défaut non permissif (V1.4 : 0 €)
        assert s["source_cache_ttl_hours"] == 24  # V1.4 : TTL cache 24 h

        r = await client.put("/api/v1/settings", json={"settings": {"source_cache_ttl_hours": 48, "paid_calls_enabled": True}})
        assert r.status_code == 200
        assert r.json()["updated"]["source_cache_ttl_hours"] == 48
        assert await engine.repo.get_setting("source_cache_ttl_hours") == 48
        assert await engine.repo.get_setting("paid_calls_enabled") is True

        r = await client.put("/api/v1/settings", json={"settings": {"global_monthly_cap_cents": -5}})
        assert r.status_code == 400
        r = await client.put("/api/v1/settings", json={"settings": {"inconnu": 1}})
        assert r.status_code == 400


async def test_api_profiles_create_et_validation(engine):
    app = create_app(engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        r = await client.get("/api/v1/profiles")
        ids = {p["id"] for p in r.json()}
        assert {"rapide", "standard", "approfondi"} <= ids  # V1.4

        r = await client.post(
            "/api/v1/profiles",
            json={
                "id": "perso",
                "name": "Perso",
                "limits": {"max_rebonds": 3, "max_source_requests": 20, "max_ai_calls": 6, "max_duration_seconds": 300, "max_cost_cents": 10},
            },
        )
        assert r.status_code == 201
        assert r.json()["id"] == "perso"

        r = await client.post(
            "/api/v1/profiles",
            json={"id": "bad", "name": "Bad", "limits": {"max_rebonds": 99, "max_source_requests": 1, "max_ai_calls": 1, "max_duration_seconds": 60, "max_cost_cents": 1}},
        )
        assert r.status_code == 400  # borne 1–10 (T4.8)

        r = await client.post(
            "/api/v1/profiles",
            json={"id": "perso", "name": "Doublon", "limits": {"max_rebonds": 1, "max_source_requests": 1, "max_ai_calls": 1, "max_duration_seconds": 60, "max_cost_cents": 1}},
        )
        assert r.status_code == 409
