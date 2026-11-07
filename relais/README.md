# Relais Gemini de CV Builder Pro

Le choix **Gemini de Yahya** de l'appli passe par ce relais. Il tourne sur Cloudflare
Workers (offre gratuite) et :

- garde la clé Gemini de Yahya comme secret chiffré chez Cloudflare (jamais dans ce dépôt) ;
- n'accepte que les personnes qui ont reçu un **code d'accès** ;
- limite chaque code à **20 demandes par jour** (un CV ciblé en fait 3, une lettre 1) ;
- s'arrête de lui-même quand la dépense du mois atteint **9 $**, jusqu'au 1er du mois suivant
  (un peu sous les 8,99 € de crédits mensuels d'un abonnement Google AI Pro) ;
- n'utilise que **Gemini 3.5 Flash-Lite**, le modèle le moins cher, quoi que demande l'appli ;
- ne garde ni ne journalise le contenu des demandes (CV, offres, lettres).

Ces réglages sont dans `wrangler.toml` (`QUOTA_JOUR`, `BUDGET_MOIS`, `MODELE`, prix).

## Mise en ligne (une seule fois)

Il faut Node.js, un compte [Cloudflare](https://dash.cloudflare.com/sign-up) (gratuit) et
une clé Gemini sur un projet Google **avec facturation** : les conditions de Google
réservent l'offre gratuite aux usages qui ne servent pas d'utilisateurs dans l'Union
européenne. Les crédits mensuels d'un abonnement Google AI Pro s'y appliquent une fois
activés dans le Google Developer Program.

```bash
cd relais
npm install
npx wrangler login                     # ouvre le navigateur, connexion à Cloudflare
npm run preparer                       # crée le stockage des codes
npx wrangler secret put GEMINI_API_KEY # colle la clé Gemini quand il la demande
npm run deployer                       # met le relais en ligne et affiche son adresse
```

L'adresse ressemble à `https://cvb-relais.<ton-sous-domaine>.workers.dev`. L'appli la
lit dans `RELAIS_URL` (fichier `.env`), ou dans la valeur par défaut de
`backend/app/settings.py`.

## Les codes d'accès

```bash
npm run code -- ajouter "Karim"   # crée un code et l'affiche une seule fois : à lui transmettre
npm run code -- retirer "Karim"   # lui coupe l'accès
npm run code -- liste             # qui a un code
npm run code -- usage             # dépense du mois, demandes de chacun aujourd'hui
```

Le relais ne garde que l'empreinte de chaque code (SHA-256) : un code perdu ne se
retrouve pas, il se recrée.

## Essais

```bash
npm test
```

Sans Cloudflare ni Google : un faux stockage et un faux Google vérifient les codes, le
quota du jour, le plafond du mois, le modèle imposé et que la clé ne ressort jamais.
