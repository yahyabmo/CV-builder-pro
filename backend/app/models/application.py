"""Le suivi d'une candidature, gardé dans meta.json : statut, dates, contact, historique."""

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["todo", "sent", "interview", "offer", "refused"]

# Sans réponse, on propose de relancer dix jours après l'envoi.
FOLLOW_UP_DAYS = 10

EVENTS: dict[Status, str] = {
    "todo": "Remise à envoyer",
    "sent": "Candidature envoyée",
    "interview": "Entretien obtenu",
    "offer": "Offre reçue",
    "refused": "Refus reçu",
}


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on: date
    text: str


class Application(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Status = "todo"
    sent_on: date | None = None
    follow_up_on: date | None = None
    contact: str = ""
    contact_email: str = ""
    notes: str = ""
    # Du plus récent au plus ancien.
    history: list[Event] = Field(default_factory=list)

    def due(self, today: date) -> bool:
        """Une relance à faire : envoyée, sans réponse, et la date de relance est passée."""
        return (
            self.status == "sent" and self.follow_up_on is not None and self.follow_up_on <= today
        )


class ApplicationPatch(BaseModel):
    """Ce que la fiche d'une candidature modifie ; un champ absent ne change pas."""

    model_config = ConfigDict(extra="forbid")

    status: Status | None = None
    sent_on: date | None = None
    follow_up_on: date | None = None
    contact: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    offer_url: str | None = Field(default=None, max_length=2000)
    # « Relancée aujourd'hui » : la relance est notée, la suivante proposée dix jours après.
    followed_up: bool = False


def follow_up(sent_on: date | None) -> date | None:
    return sent_on + timedelta(days=FOLLOW_UP_DAYS) if sent_on else None


def update(app: Application, patch: ApplicationPatch, today: date) -> Application:
    app = app.model_copy(deep=True)
    given = patch.model_fields_set
    if "sent_on" in given:
        app.sent_on = patch.sent_on
        if "follow_up_on" not in given:
            app.follow_up_on = follow_up(patch.sent_on)
        # Une date d'envoi corrigée déplace l'envoi dans l'historique.
        sent = next((e for e in app.history if e.text == EVENTS["sent"]), None)
        if sent and patch.sent_on:
            sent.on = patch.sent_on
    if "follow_up_on" in given:
        app.follow_up_on = patch.follow_up_on
    for name in ("contact", "contact_email", "notes"):
        value = getattr(patch, name)
        if name in given and value is not None:
            setattr(app, name, value.strip())
    if patch.status is not None and patch.status != app.status:
        app.status = patch.status
        if patch.status == "sent" and app.sent_on is None:
            app.sent_on = today
            app.follow_up_on = app.follow_up_on or follow_up(today)
        # Un envoi daté (« envoyée le 20 oct. ») entre dans l'historique à sa date.
        on = app.sent_on if patch.status == "sent" and app.sent_on else today
        app.history.insert(0, Event(on=on, text=EVENTS[patch.status]))
    if patch.followed_up:
        app.history.insert(0, Event(on=today, text="Relance faite"))
        app.follow_up_on = follow_up(today)
    return app
