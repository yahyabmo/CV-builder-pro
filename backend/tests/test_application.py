from datetime import date

from fastapi.testclient import TestClient

from app.models.application import Application, ApplicationPatch, update

TODAY = date(2026, 11, 3)


def test_sending_sets_the_date_and_a_follow_up_ten_days_later() -> None:
    app = update(Application(), ApplicationPatch(status="sent"), TODAY)
    assert app.status == "sent" and app.sent_on == TODAY
    assert app.follow_up_on == date(2026, 11, 13)
    assert [(e.on, e.text) for e in app.history] == [(TODAY, "Candidature envoyée")]


def test_a_chosen_send_date_moves_the_follow_up() -> None:
    app = update(Application(), ApplicationPatch(status="sent", sent_on=date(2026, 10, 20)), TODAY)
    assert app.sent_on == date(2026, 10, 20) and app.follow_up_on == date(2026, 10, 30)
    assert app.history[0].on == date(2026, 10, 20)
    # Une date de relance choisie à la main l'emporte.
    patch = ApplicationPatch(sent_on=date(2026, 10, 21), follow_up_on=date(2026, 11, 5))
    app = update(app, patch, TODAY)
    assert app.follow_up_on == date(2026, 11, 5)


def test_correcting_the_send_date_moves_the_event() -> None:
    app = update(Application(), ApplicationPatch(status="sent"), TODAY)
    app = update(app, ApplicationPatch(sent_on=date(2026, 10, 23)), TODAY)
    assert [(e.on, e.text) for e in app.history] == [(date(2026, 10, 23), "Candidature envoyée")]
    assert app.follow_up_on == date(2026, 11, 2)


def test_a_follow_up_is_due_only_while_waiting_for_an_answer() -> None:
    app = update(Application(), ApplicationPatch(status="sent", sent_on=date(2026, 10, 20)), TODAY)
    assert app.due(TODAY) and not app.due(date(2026, 10, 29))
    answered = update(app, ApplicationPatch(status="interview"), TODAY)
    assert not answered.due(TODAY)
    assert answered.history[0].text == "Entretien obtenu"


def test_followed_up_today_pushes_the_next_reminder() -> None:
    app = update(Application(), ApplicationPatch(status="sent", sent_on=date(2026, 10, 20)), TODAY)
    app = update(app, ApplicationPatch(followed_up=True), TODAY)
    assert not app.due(TODAY) and app.follow_up_on == date(2026, 11, 13)
    assert app.history[0].text == "Relance faite"


def test_same_status_adds_no_event_and_text_is_trimmed() -> None:
    app = update(Application(), ApplicationPatch(contact="  Équipe Data  ", notes=" Lu. "), TODAY)
    assert app.contact == "Équipe Data" and app.notes == "Lu."
    assert update(app, ApplicationPatch(status="todo"), TODAY).history == []


def test_route_updates_the_summary(client: TestClient) -> None:
    slug = client.post("/api/cvs", json={"name": "Nordia – Data Scientist"}).json()["slug"]
    out = client.patch(
        f"/api/cvs/{slug}/application",
        json={"status": "sent", "sent_on": "2020-01-01", "offer_url": " https://exemple.fr/offre "},
    ).json()
    assert out["meta"]["application"]["status"] == "sent"
    assert out["meta"]["application"]["follow_up_on"] == "2020-01-11"
    assert out["meta"]["offer_url"] == "https://exemple.fr/offre"
    assert out["due"] is True
    listed = {cv["slug"]: cv for cv in client.get("/api/cvs").json()}
    assert listed[slug]["due"] is True and listed["base"]["due"] is False


def test_the_base_cv_is_not_an_application(client: TestClient) -> None:
    assert client.patch("/api/cvs/base/application", json={"status": "sent"}).status_code == 409


def test_unknown_status_is_refused(client: TestClient) -> None:
    slug = client.post("/api/cvs", json={"name": "Essai"}).json()["slug"]
    assert client.patch(f"/api/cvs/{slug}/application", json={"status": "perdu"}).status_code == 422
