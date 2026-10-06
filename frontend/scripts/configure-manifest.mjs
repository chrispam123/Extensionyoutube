import fs from "node:fs";
import path from "node:path";

const bucket = process.env.S3_BUCKET?.trim();

if (!bucket) {
  throw new Error("S3_BUCKET es obligatorio para configurar el manifest");
}

const manifestPath = path.resolve("dist", "manifest.json");
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const existingHosts = Array.isArray(manifest.host_permissions)
  ? manifest.host_permissions
  : [];

const s3Host = `https://${bucket}.s3.amazonaws.com/*`;
const hostPermissions = existingHosts.filter(
  (host) => !/^https:\/\/[^/]+\.s3\.amazonaws\.com\/\*$/.test(host),
);

manifest.host_permissions = [...hostPermissions, s3Host];

fs.writeFileSync(`${manifestPath}`, `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`Manifest configurado para ${s3Host}`);
