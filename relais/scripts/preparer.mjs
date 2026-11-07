// Crée l'espace de stockage des codes (KV) et inscrit son identifiant dans wrangler.toml.
// À lancer une seule fois, après « npx wrangler login ».
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const config = `${root}wrangler.toml`;
const current = readFileSync(config, "utf8");
if (!current.includes("A_REMPLIR_PAR_NPM_RUN_PREPARER")) {
  console.log("Déjà prêt : wrangler.toml a son identifiant de stockage.");
  process.exit(0);
}
const out = execFileSync("npx", ["wrangler", "kv", "namespace", "create", "CODES"], {
  cwd: root,
  encoding: "utf8",
  stdio: ["ignore", "pipe", "inherit"],
});
const found = out.match(/"id"\s*:\s*"([0-9a-f]{32})"/) || out.match(/id\s*=\s*"([0-9a-f]{32})"/);
if (!found) {
  console.error(out);
  console.error("Identifiant introuvable dans la réponse de wrangler : copie-le dans wrangler.toml.");
  process.exit(1);
}
writeFileSync(config, current.replace("A_REMPLIR_PAR_NPM_RUN_PREPARER", found[1]));
console.log(`Stockage créé (${found[1]}) et inscrit dans wrangler.toml.`);
