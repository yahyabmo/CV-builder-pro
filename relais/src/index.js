/**
 * Relais Gemini de CV Builder Pro.
 *
 * Il garde la clé Gemini de Yahya (secret GEMINI_API_KEY, jamais dans le dépôt), vérifie
 * les codes d'accès qu'il a distribués, applique un quota par code et par jour et un
 * plafond de dépense par mois. Il imite l'adresse de Google
 * (POST /v1beta/models/<modèle>:generateContent) : l'appli n'a qu'à changer d'adresse
 * et d'en-tête. Le contenu des demandes n'est ni gardé ni journalisé.
 *
 *   POST /v1/verifier                              le code est-il valable ? (sans appel à Google)
 *   POST /v1beta/models/<modèle>:generateContent   une demande au modèle (le modèle est imposé)
 *
 * Un code « serveur » (serveur: true) est celui de la version en ligne : plusieurs
 * personnes le partagent, et l'appli envoie avec chaque demande l'en-tête
 * X-CVB-Utilisateur, l'empreinte SHA-256 de l'e-mail de la personne connectée. Le
 * quota du jour compte alors par personne ; le relais ne voit jamais l'e-mail.
 *
 * Stockage (KV, liaison CODES) :
 *   code:<sha256 du code>  {nom, cree, serveur?}  un code d'accès, rangé haché
 *   nom:<nom>              <sha256>          pour retirer un code par son nom
 *   usage:<AAAA-MM>        {depense, jours: {<AAAA-MM-JJ>: {<id>: demandes}}}
 */

const GOOGLE = "https://generativelanguage.googleapis.com/v1beta/models/";
// Un CV et une offre font quelques dizaines de milliers de caractères.
const MAX_BODY = 400_000;

export default {
  fetch(request, env, ctx) {
    return handle(request, env, ctx);
  },
};

export async function handle(request, env, ctx) {
  const url = new URL(request.url);
  if (request.method === "GET" && url.pathname === "/") {
    return json(200, { service: "Relais Gemini de CV Builder Pro" });
  }
  if (request.method !== "POST") return error(405, "Méthode non permise.", "METHODE");

  const who = await identify(request, env);
  if (!who) {
    return error(
      401,
      "Code d'accès inconnu ou retiré. Demande un code à Yahya, ou utilise ta propre clé Gemini.",
      "CODE",
    );
  }
  if (who.serveur) {
    const user = (request.headers.get("x-cvb-utilisateur") || "").trim().toLowerCase();
    if (!/^[0-9a-f]{64}$/.test(user)) {
      return error(400, "Demande sans personne connectée.", "UTILISATEUR");
    }
    who.id = (await sha256(`${who.id}:${user}`)).slice(0, 16);
  }
  const day = today(env);
  const month = day.slice(0, 7);
  const usage = await readUsage(env, month);
  const quota = Number(env.QUOTA_JOUR || 20);
  const budget = Number(env.BUDGET_MOIS || 10);
  const used = usage.jours?.[day]?.[who.id] || 0;

  if (url.pathname === "/v1/verifier") {
    return json(200, {
      ok: true,
      nom: who.nom,
      reste_jour: Math.max(0, quota - used),
      quota_jour: quota,
      credit_epuise: usage.depense >= budget,
      modele: env.MODELE,
    });
  }
  if (!/^\/v1beta\/models\/[A-Za-z0-9._-]+:generateContent$/.test(url.pathname)) {
    return error(404, "Adresse inconnue.", "ADRESSE");
  }
  if (usage.depense >= budget) {
    return error(
      429,
      "Le crédit offert ce mois-ci est épuisé. Il revient le 1er du mois ; d'ici là, " +
        "utilise ta propre clé Gemini (Réglages).",
      "PLAFOND_MOIS",
    );
  }
  if (used >= quota) {
    return error(
      429,
      `Tes ${quota} demandes du jour sont utilisées. Elles reviennent demain ; d'ici là, ` +
        "utilise ta propre clé Gemini (Réglages).",
      "QUOTA_JOUR",
    );
  }

  const raw = await request.text();
  if (raw.length > MAX_BODY) return error(413, "Demande trop longue.", "TAILLE");
  let body;
  try {
    body = JSON.parse(raw);
  } catch {
    return error(400, "Demande illisible.", "CORPS");
  }
  if (!body || typeof body !== "object" || !Array.isArray(body.contents)) {
    return error(400, "Demande illisible.", "CORPS");
  }
  // Le modèle garde sa réflexion par défaut (minimale pour Flash-Lite), et aucun outil
  // payant (recherche web, exécution de code) ne s'ajoute.
  if (body.generationConfig && typeof body.generationConfig === "object") {
    delete body.generationConfig.thinkingConfig;
  }
  delete body.tools;
  delete body.toolConfig;
  delete body.cachedContent;

  let upstream;
  try {
    upstream = await fetch(`${GOOGLE}${env.MODELE}:generateContent`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-goog-api-key": env.GEMINI_API_KEY },
      body: JSON.stringify(body),
    });
  } catch {
    return error(502, "Google est injoignable depuis le relais. Réessaie dans un instant.", "GOOGLE");
  }
  const text = await upstream.text();
  if (upstream.ok) {
    const record = recordUse(env, month, day, who.id, cost(text, env));
    if (ctx && typeof ctx.waitUntil === "function") ctx.waitUntil(record);
    else await record;
  }
  return new Response(text, {
    status: upstream.status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

/** Le code d'accès de l'en-tête Authorization, s'il est connu : {id, nom, serveur}. */
async function identify(request, env) {
  const header = request.headers.get("authorization") || "";
  const code = header.replace(/^Bearer\s+/i, "").trim();
  if (code.length < 10 || code.length > 200) return null;
  const hash = await sha256(code);
  const found = await env.CODES.get(`code:${hash}`, "json");
  return found ? { id: hash.slice(0, 16), nom: found.nom || "", serveur: found.serveur === true } : null;
}

export async function sha256(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** La date du jour à Paris, AAAA-MM-JJ : les quotas reviennent à minuit, heure française. */
function today(env) {
  return new Intl.DateTimeFormat("fr-CA", { timeZone: env.FUSEAU || "Europe/Paris" }).format(
    env.MAINTENANT ? new Date(env.MAINTENANT) : new Date(),
  );
}

async function readUsage(env, month) {
  const found = await env.CODES.get(`usage:${month}`, "json");
  return found && typeof found === "object" ? { depense: 0, jours: {}, ...found } : { depense: 0, jours: {} };
}

/** Ce qu'a coûté une réponse de Google, en dollars, d'après ses compteurs de jetons. */
function cost(text, env) {
  try {
    const meta = JSON.parse(text).usageMetadata || {};
    const input = meta.promptTokenCount || 0;
    const output = (meta.candidatesTokenCount || 0) + (meta.thoughtsTokenCount || 0);
    return (input * Number(env.PRIX_ENTREE || 0) + output * Number(env.PRIX_SORTIE || 0)) / 1e6;
  } catch {
    return 0;
  }
}

/** Une demande de plus pour ce code aujourd'hui, et sa dépense ajoutée au mois. */
async function recordUse(env, month, day, id, spent) {
  try {
    const usage = await readUsage(env, month);
    usage.depense = Math.round((usage.depense + spent) * 1e6) / 1e6;
    usage.jours[day] = usage.jours[day] || {};
    usage.jours[day][id] = (usage.jours[day][id] || 0) + 1;
    await env.CODES.put(`usage:${month}`, JSON.stringify(usage), { expirationTtl: 400 * 86400 });
  } catch {
    // Le décompte est au mieux : une écriture perdue ne doit pas faire échouer la réponse.
  }
}

function json(status, data) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

/** Une erreur au format de Google : l'appli la lit comme celles de Gemini. */
function error(status, message, code) {
  return json(status, { error: { code: status, message, status: code } });
}
