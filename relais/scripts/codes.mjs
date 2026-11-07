// Les codes d'accès au relais : les créer, les retirer, les lister, voir la dépense du mois.
//
//   npm run code -- ajouter "Karim"   crée un code pour Karim et l'affiche (à lui transmettre)
//   npm run code -- retirer "Karim"   lui coupe l'accès
//   npm run code -- liste             les personnes qui ont un code
//   npm run code -- usage             la dépense du mois et les demandes de chacun aujourd'hui
//
// Le code n'est montré qu'une fois : le relais n'en garde que l'empreinte (SHA-256).
import { execFileSync } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"; // sans 0/o, 1/l/i : lisible à la main

function wrangler(args, quiet = false) {
  return execFileSync("npx", ["wrangler", "kv", "key", ...args, "--binding=CODES", "--remote"], {
    cwd: root,
    encoding: "utf8",
    stdio: ["ignore", "pipe", quiet ? "pipe" : "inherit"],
  });
}
const put = (key, value) => wrangler(["put", key, value]);
// Une clé absente répond 404 : ce n'est pas une erreur ici, d'où le silence.
const get = (key) => {
  try {
    return wrangler(["get", key], true).trim();
  } catch {
    return "";
  }
};
const list = (prefix) => JSON.parse(wrangler(["list", `--prefix=${prefix}`]) || "[]").map((k) => k.name);
const sha256 = (text) => createHash("sha256").update(text).digest("hex");
const nameKey = (name) => `nom:${encodeURIComponent(name.trim().toLowerCase())}`;

export function newCode() {
  const bytes = randomBytes(16);
  const chars = [...bytes].map((b) => ALPHABET[b % ALPHABET.length]).join("");
  return `cvb-${chars.match(/.{4}/g).join("-")}`;
}

function today() {
  return new Intl.DateTimeFormat("fr-CA", { timeZone: "Europe/Paris" }).format(new Date());
}

function main([action, ...rest]) {
  const name = rest.join(" ").trim();
  if (action === "ajouter" && name) {
    if (get(nameKey(name))) {
      console.error(`« ${name} » a déjà un code. Retire-le d'abord pour en créer un nouveau.`);
      process.exit(1);
    }
    const code = newCode();
    const hash = sha256(code);
    put(`code:${hash}`, JSON.stringify({ nom: name, cree: new Date().toISOString() }));
    put(nameKey(name), hash);
    console.log(`\nCode d'accès de ${name} (il ne sera plus affiché) :\n\n  ${code}\n`);
    console.log("Dans l'appli : Réglages › Gemini de Yahya, puis colle ce code.");
  } else if (action === "retirer" && name) {
    const hash = get(nameKey(name));
    if (!hash) {
      console.error(`Aucun code pour « ${name} ».`);
      process.exit(1);
    }
    wrangler(["delete", `code:${hash}`]);
    wrangler(["delete", nameKey(name)]);
    console.log(`Accès de ${name} coupé.`);
  } else if (action === "liste") {
    const names = list("nom:").map((k) => decodeURIComponent(k.slice(4)));
    console.log(names.length ? names.join("\n") : "Aucun code pour l'instant.");
  } else if (action === "usage") {
    const day = today();
    const usage = JSON.parse(get(`usage:${day.slice(0, 7)}`) || "{}");
    const ids = Object.fromEntries(
      list("nom:").map((k) => [get(k).slice(0, 16), decodeURIComponent(k.slice(4))]),
    );
    console.log(`Dépense du mois : ${(usage.depense || 0).toFixed(4)} $ (plafond : voir BUDGET_MOIS)`);
    const counts = usage.jours?.[day] || {};
    for (const [id, n] of Object.entries(counts)) console.log(`  ${ids[id] || id} : ${n} demande(s) aujourd'hui`);
  } else {
    console.log("Usage : npm run code -- ajouter <nom> | retirer <nom> | liste | usage");
    process.exit(action ? 1 : 0);
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main(process.argv.slice(2));
