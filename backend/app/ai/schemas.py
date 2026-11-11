"""Ce que l'IA doit rendre à chaque étape du ciblage (schémas JSON imposés).

Les descriptions des champs font partie de la consigne : le modèle les lit.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Out(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Keyword(_Out):
    term: str = Field(
        description="Le mot ou l'expression tel qu'écrit dans l'offre (vocabulaire exact)."
    )
    importance: Literal[1, 2, 3] = Field(
        description="3 = indispensable, 2 = important, 1 = apprécié."
    )
    category: Literal["techno", "outil", "méthode", "compétence", "soft skill", "domaine", "autre"]


class OfferAnalysis(_Out):
    """Étape 1 : l'offre lue et structurée."""

    is_job_offer: bool = Field(
        description="Faux si le texte n'est pas une offre d'emploi ou de stage."
    )
    job_title: str = Field(description="Intitulé du poste, tel qu'écrit dans l'offre.")
    company: str = Field(description="Nom de l'entreprise, vide si absent.")
    location: str = ""
    contract: str = Field(default="", description="Stage, CDI, alternance… si indiqué.")
    offer_language: Literal["fr", "en", "other"] = Field(
        description="Langue dans laquelle l'offre est RÉDIGÉE."
    )
    required_languages: list[str] = Field(description="Langues que le candidat doit parler.")
    technologies: list[str]
    tools: list[str]
    methods: list[str]
    skills: list[str] = Field(description="Compétences techniques ou métier attendues.")
    soft_skills: list[str]
    keywords: list[Keyword] = Field(
        description=(
            "Mots-clés qu'un ATS chercherait dans le CV, du plus au moins important (15 à 35)."
        )
    )
    summary: str = Field(description="En deux phrases : ce que fera la personne recrutée.")
    short_name: str = Field(
        default="",
        description="1 à 3 mots qui résument le poste, pour nommer le fichier (« agent SRE »).",
    )


class SkillItem(_Out):
    text: str = Field(
        description=(
            "La compétence telle qu'elle sera écrite dans le CV : l'écriture de l'offre "
            "si elle désigne la même chose, dans la langue de rédaction."
        )
    )
    source: str = Field(
        default="",
        description=(
            "Son nom exact dans « Ses compétences », recopié tel quel ; vide si elle n'y est "
            "pas (compétence de l'offre que le candidat confirmera ou non)."
        ),
    )


class SkillGroupOut(_Out):
    label: str = Field(description="Nom du groupe, court (ex. « Langages », « IA & Data »).")
    items: list[SkillItem] = Field(description="Compétences du groupe, une par élément.")


class MissingSkill(_Out):
    term: str = Field(description="Mot-clé de l'offre que le candidat n'a pas.")
    note: str = Field(description="Une phrase : ce qui s'en approche chez lui, ou rien.")


class ProjectChoice(_Out):
    id: str = Field(
        description="Identifiant d'un projet de la liste fournie (ex. « projet-3a1b2c3d »)."
    )
    reason: str = Field(description="Une phrase : pourquoi ce projet sert cette offre.")


class TargetPlan(_Out):
    """Étape 2 : titre, accroche, compétences et projets pour cette offre."""

    headline: str = Field(description="Titre du CV aligné sur le poste (une ligne).")
    summary: str = Field(description="Accroche de deux lignes au plus, alignée sur l'offre.")
    skill_groups: list[SkillGroupOut]
    missing: list[MissingSkill] = Field(
        description="Mots-clés de l'offre absents du profil : ne pas les inventer."
    )
    projects: list[ProjectChoice] = Field(
        description="Projets retenus, du plus au moins pertinent."
    )


class TextRewrite(_Out):
    ref: str = Field(
        description="La référence du texte, recopiée telle quelle (ex. « E1.2 », « P3 »)."
    )
    text: str = Field(description="Le nouveau texte.")


class ExperienceChoice(_Out):
    exp: str = Field(description="La référence de l'expérience (ex. « E1 »).")
    bullets: list[TextRewrite] = Field(
        description=(
            "Les puces retenues, dans l'ordre d'affichage : la référence de la puce d'origine "
            "et son texte, adapté ou inchangé."
        )
    )


class Rewrite(_Out):
    """Étape 3 : puces des expériences (choisies et adaptées) et descriptions de projets."""

    experiences: list[ExperienceChoice] = Field(default_factory=list)
    texts: list[TextRewrite] = Field(
        default_factory=list,
        description="Descriptions de projets (P1…) réellement modifiées.",
    )


class Translation(_Out):
    """Étape 4 (si besoin) : le CV traduit, texte par texte."""

    texts: list[TextRewrite]


class ProjectDraft(_Out):
    """Fiche d'un projet de la bibliothèque, rédigée depuis son README."""

    description: str = Field(description="Une phrase de CV, 20 à 30 mots.")
    bullets: list[str] = Field(description="2 à 5 points précis, une ligne chacun.")
    techs: list[str] = Field(description="Technologies réellement utilisées.")


class LetterDraft(_Out):
    """La lettre de motivation, écrite pour une offre."""

    recipient: list[str] = Field(description="1 à 3 lignes : entreprise, équipe si nommée, ville.")
    subject: str = Field(
        description="Objet : candidature au stage, avec l'intitulé exact de l'offre."
    )
    salutation: str = Field(description="« Madame, Monsieur, » sauf si une personne est nommée.")
    paragraphs: list[str] = Field(description="3 ou 4 paragraphes, 250 à 350 mots en tout.")
    closing: str = Field(
        description="La formule de politesse formelle d'une lettre, jamais « Cordialement »."
    )


# ─── Import d'un CV en PDF ───────────────────────────────────────────────────


class ImportedContact(_Out):
    text: str = Field(
        description="Tel qu'écrit : « Lyon, France », « 06 00 00 00 00 », une adresse."
    )
    label: str = Field(
        description="« Téléphone », « Email », « LinkedIn », « GitHub », « Mobilité »… "
        "Vide pour la ville, le permis ou une mention seule."
    )
    url: str = Field(
        default="",
        description="Le lien complet s'il y en a un (mailto: pour un email), sinon vide.",
    )


class ImportedEducation(_Out):
    title: str = Field(description="Le diplôme ou la formation.")
    place: str = Field(description="L'établissement et la ville.")
    dates: str
    description: str = ""


class ImportedExperience(_Out):
    title: str = Field(description="L'intitulé du poste ou du rôle.")
    tag: str = Field(default="", description="Une précision courte écrite à côté, sinon vide.")
    place: str = Field(description="L'entreprise ou l'organisation, et la ville.")
    dates: str
    bullets: list[str] = Field(description="Les puces, une par élément, telles qu'écrites.")


class ImportedProject(_Out):
    title: str
    tag: str = Field(default="", description="« Projet personnel », « En binôme »… sinon vide.")
    date: str
    description: str
    link: str = Field(default="", description="Le lien du projet s'il est écrit, sinon vide.")


class ImportedSkillGroup(_Out):
    label: str = Field(description="Le nom du groupe tel qu'écrit (« Langages », « Outils »).")
    items: list[str] = Field(description="Les compétences du groupe, une par élément.")


class ImportedLanguage(_Out):
    name: str
    level: str


class ImportedTitle(_Out):
    rubric: Literal[
        "education",
        "experience",
        "associative",
        "projects",
        "skills",
        "soft_skills",
        "languages",
        "interests",
    ]
    title: str = Field(description="Le titre de cette rubrique, tel qu'écrit dans le CV.")


class ImportedOther(_Out):
    title: str = Field(description="Le titre de la rubrique, tel qu'écrit dans le CV.")
    lines: list[str] = Field(description="Ses lignes, une par élément, telles qu'écrites.")


class ImportedCV(_Out):
    """Le contenu d'un CV lu dans un PDF, rangé dans les rubriques de l'appli."""

    language: Literal["fr", "en"] = Field(description="La langue dans laquelle le CV est écrit.")
    name: str = Field(description="Le nom de la personne, tel qu'écrit.")
    headline: str = Field(description="Le titre sous le nom, sinon vide.")
    summary: str = Field(description="L'accroche ou le profil, sinon vide.")
    contacts: list[ImportedContact]
    education: list[ImportedEducation]
    experience: list[ImportedExperience] = Field(description="Stages, emplois, alternance.")
    associative: list[ImportedExperience] = Field(
        description="Engagement associatif ou bénévolat, s'il est à part."
    )
    projects: list[ImportedProject]
    skills: list[ImportedSkillGroup]
    soft_skills: list[str] = Field(description="Les qualités humaines, une par élément.")
    languages: list[ImportedLanguage]
    interests: list[str] = Field(description="Les centres d'intérêt, un par élément.")
    unplaced: list[str] = Field(
        description="Les lignes qui n'entrent dans aucune rubrique, recopiées telles quelles."
    )
    titles: list[ImportedTitle] = Field(
        default_factory=list,
        description="Le titre de chaque rubrique remplie, tel qu'écrit dans le CV.",
    )
    others: list[ImportedOther] = Field(
        default_factory=list,
        description="Les rubriques sans place ci-dessus (Certifications, Publications, Prix…).",
    )


class ProjectIdea(_Out):
    """Un projet personnel, fait en quelques jours, qui rend vrais des mots-clés de l'offre."""

    name: str = Field(description="Nom affiché, court, en français.")
    effort: str = Field(description="Durée réaliste : « 2 à 3 jours », « 4 jours »…")
    pitch: str = Field(description="Ce que fait le projet, en deux phrases factuelles.")
    why: str = Field(
        description="Pourquoi il sert cette candidature, une phrase qui commence en minuscule."
    )
    keywords: list[str] = Field(
        description="Mots-clés de l'offre absents du CV que le projet utilise vraiment."
    )
    stack: list[str] = Field(description="Technologies réellement utilisées, écriture usuelle.")
    modules: list[str] = Field(description="4 à 6 composants principaux, une phrase chacun.")
    data: str = Field(description="Les données utilisées : publiques et gratuites, ou générées.")
    steps: list[str] = Field(description="3 à 5 étapes, une par jour : « Jour 1 : … ».")
    cv_line: str = Field(
        description="La ligne de CV une fois le projet fait : ce qu'il fait, avec quoi, un chiffre."
    )
    questions: list[str] = Field(description="3 questions qu'un recruteur posera sur ce projet.")


class ProjectIdeas(_Out):
    ideas: list[ProjectIdea] = Field(description="Exactement 3 idées, vraiment différentes.")
