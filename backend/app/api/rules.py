"""Routes des listes de règles (Réglages) : lettre, tournures à bannir."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import rules

router = APIRouter(prefix="/api/rules", tags=["règles"])


class Rules(BaseModel):
    rules: list[str] = Field(max_length=80)


@router.get("/{kind}")
def get_rules(kind: str) -> Rules:
    try:
        return Rules(rules=rules.read(kind))
    except rules.UnknownRules:
        raise HTTPException(404, f"Liste de règles inconnue : {kind}") from None


@router.put("/{kind}")
def put_rules(kind: str, body: Rules) -> Rules:
    if any(len(rule) > 1000 for rule in body.rules):
        raise HTTPException(422, "Une règle dépasse 1000 caractères.")
    try:
        return Rules(rules=rules.write(kind, body.rules))
    except rules.UnknownRules:
        raise HTTPException(404, f"Liste de règles inconnue : {kind}") from None
