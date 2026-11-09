// Essais du relais, sans Cloudflare ni Google : un faux stockage et un faux Google.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { test } from "node:test";

import { newCode } from "../scripts/codes.mjs";
import { handle, sha256 } from "../src/index.js";

class FakeKV {
  constructor() {
    this.data = new Map();
  }
  async get(key, type) {
    const value = this.data.get(key);
    if (value === undefined) return null;
    return type === "json" ? JSON.parse(value) : value;
  }
  async put(key, value) {
    this.data.set(key, value);
  }
}

const SECRET = "cle-google-de-test";
const GENERATE = "/v1beta/models/gemini-3.5-flash:generateContent";
const BODY = {
  contents: [{ role: "user", parts: [{ text: "Bonjour" }] }],
  generationConfig: { temperature: 0.2, thinkingConfig: { thinkingLevel: "high" } },
  tools: [{ googleSearch: {} }],
};

async function setup({ quota = 20, budget = 10, spent = 0 } = {}) {
  const kv = new FakeKV();
  const code = newCode();
  await kv.put(`code:${await sha256(code)}`, JSON.stringify({ nom: "Karim" }));
  if (spent) await kv.put("usage:2026-11", JSON.stringify({ depense: spent, jours: {} }));
  const env = {
    CODES: kv,
    GEMINI_API_KEY: SECRET,
    MODELE: "gemini-3.5-flash-lite",
    QUOTA_JOUR: String(quota),
    BUDGET_MOIS: String(budget),
    PRIX_ENTREE: "0.30",
    PRIX_SORTIE: "2.50",
    FUSEAU: "Europe/Paris",
    MAINTENANT: "2026-11-07T10:00:00Z",
  };
  return { kv, code, env };
}

function request(path, code, body, method = "POST") {
  const headers = { "content-type": "application/json" };
  if (code) headers.authorization = `Bearer ${code}`;
  return new Request(`https://relais.example${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/** Un faux Google : il répond « {} » et compte 1 000 jetons lus, 1 000 écrits. */
function fakeGoogle(t, status = 200) {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, init) => {
    calls.push({ url: String(url), init });
    const answer =
      status === 200
        ? { candidates: [{ content: { parts: [{ text: "{}" }] } }], usageMetadata: { promptTokenCount: 1000, candidatesTokenCount: 600, thoughtsTokenCount: 400 } }
        : { error: { code: status, message: "Le modèle est surchargé.", status: "UNAVAILABLE" } };
    return new Response(JSON.stringify(answer), { status });
  });
  return calls;
}

test("un code inconnu est refusé, sans appel à Google", async (t) => {
  const { env } = await setup();
  const calls = fakeGoogle(t);
  const reply = await handle(request(GENERATE, "cvb-faux-faux-faux-faux", BODY), env);
  assert.equal(reply.status, 401);
  assert.equal((await reply.json()).error.status, "CODE");
  assert.equal(calls.length, 0);
  assert.equal((await handle(request(GENERATE, undefined, BODY), env)).status, 401);
});

test("vérifier un code ne coûte rien et dit ce qu'il reste", async (t) => {
  const { code, env } = await setup();
  const calls = fakeGoogle(t);
  const reply = await handle(request("/v1/verifier", code), env);
  assert.equal(reply.status, 200);
  assert.deepEqual(await reply.json(), {
    ok: true,
    nom: "Karim",
    reste_jour: 20,
    quota_jour: 20,
    credit_epuise: false,
    modele: "gemini-3.5-flash-lite",
  });
  assert.equal(calls.length, 0);
});

test("une demande part chez Google avec la clé, le modèle imposé, sans réflexion ni outils", async (t) => {
  const { code, env, kv } = await setup();
  const calls = fakeGoogle(t);
  const reply = await handle(request(GENERATE, code, BODY), env);
  assert.equal(reply.status, 200);
  const text = await reply.text();
  assert.ok(!text.includes(SECRET), "la clé ne revient jamais à l'appli");
  assert.deepEqual(JSON.parse(text).candidates[0].content.parts[0].text, "{}");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent");
  assert.equal(calls[0].init.headers["x-goog-api-key"], SECRET);
  const sent = JSON.parse(calls[0].init.body);
  assert.equal(sent.generationConfig.temperature, 0.2);
  assert.equal(sent.generationConfig.thinkingConfig, undefined);
  assert.equal(sent.tools, undefined);
  // 1 000 jetons lus à 0,30 $ et 1 000 écrits (réflexion comprise) à 2,50 $ le million.
  const usage = await kv.get("usage:2026-11", "json");
  assert.equal(usage.depense, 0.0028);
  assert.deepEqual(Object.values(usage.jours["2026-11-07"]), [1]);
});

test("le quota du jour arrête la personne, pas les autres", async (t) => {
  const { code, env, kv } = await setup({ quota: 2 });
  const other = newCode();
  await kv.put(`code:${await sha256(other)}`, JSON.stringify({ nom: "Lina" }));
  const calls = fakeGoogle(t);
  assert.equal((await handle(request(GENERATE, code, BODY), env)).status, 200);
  assert.equal((await handle(request(GENERATE, code, BODY), env)).status, 200);
  const third = await handle(request(GENERATE, code, BODY), env);
  assert.equal(third.status, 429);
  const error = (await third.json()).error;
  assert.equal(error.status, "QUOTA_JOUR");
  assert.match(error.message, /ta propre clé Gemini/);
  assert.equal(calls.length, 2);
  assert.equal((await handle(request(GENERATE, other, BODY), env)).status, 200);
  assert.equal((await (await handle(request("/v1/verifier", code), env)).json()).reste_jour, 0);
});

test("le plafond du mois arrête tout le monde, sans appel à Google", async (t) => {
  const { code, env } = await setup({ budget: 10, spent: 10.01 });
  const calls = fakeGoogle(t);
  const reply = await handle(request(GENERATE, code, BODY), env);
  assert.equal(reply.status, 429);
  assert.equal((await reply.json()).error.status, "PLAFOND_MOIS");
  assert.equal(calls.length, 0);
  assert.equal((await (await handle(request("/v1/verifier", code), env)).json()).credit_epuise, true);
});

test("une erreur de Google revient telle quelle et ne compte pas", async (t) => {
  const { code, env, kv } = await setup();
  fakeGoogle(t, 503);
  const reply = await handle(request(GENERATE, code, BODY), env);
  assert.equal(reply.status, 503);
  assert.equal((await reply.json()).error.status, "UNAVAILABLE");
  assert.equal(await kv.get("usage:2026-11", "json"), null);
});

test("adresses et requêtes inattendues", async (t) => {
  const { code, env } = await setup();
  const calls = fakeGoogle(t);
  assert.equal((await handle(new Request("https://relais.example/"), env)).status, 200);
  assert.equal((await handle(request(GENERATE, code, BODY, "PUT"), env)).status, 405);
  assert.equal((await handle(request("/v1beta/models/x:streamGenerateContent", code, BODY), env)).status, 404);
  assert.equal((await handle(request(GENERATE, code, { pas: "de contenu" }), env)).status, 400);
  assert.equal(calls.length, 0);
});

test("un code se lit et se recopie facilement, et l'appli l'accepte", () => {
  const code = newCode();
  assert.match(code, /^cvb-[a-z2-9]{4}-[a-z2-9]{4}-[a-z2-9]{4}-[a-z2-9]{4}$/);
  assert.match(code, /^[A-Za-z0-9._-]{10,200}$/);
  assert.notEqual(newCode(), code);
});

test("un code serveur compte le quota par personne connectée, sans voir l'e-mail", async (t) => {
  const { env, kv } = await setup({ quota: 1 });
  const server = newCode();
  await kv.put(`code:${await sha256(server)}`, JSON.stringify({ nom: "En ligne", serveur: true }));
  const calls = fakeGoogle(t);
  const as = (email, path = GENERATE, body = BODY) => {
    const req = request(path, server, body);
    if (email) req.headers.set("x-cvb-utilisateur", createHash("sha256").update(email).digest("hex"));
    return handle(req, env);
  };
  // Sans personne connectée : refusé, sans appel à Google.
  const anonymous = await as(undefined);
  assert.equal(anonymous.status, 400);
  assert.equal((await anonymous.json()).error.status, "UTILISATEUR");
  assert.equal(calls.length, 0);

  assert.equal((await as("alice@example.com")).status, 200);
  assert.equal((await as("alice@example.com")).status, 429);
  assert.equal((await as("bob@example.com")).status, 200);
  assert.equal((await (await as("alice@example.com", "/v1/verifier")).json()).reste_jour, 0);
  assert.equal((await (await as("carla@example.com", "/v1/verifier")).json()).reste_jour, 1);
  assert.ok(![...kv.data.values()].some((v) => v.includes("example.com")), "aucun e-mail gardé");
});
