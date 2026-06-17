const fs = require("node:fs");
const path = require("node:path");
const zlib = require("node:zlib");

const renderSvg = require("lottie-to-svg");
const sharp = require("sharp");

const PREVIEW_FRAME = 3;

function usage() {
  console.error("Usage: node scripts/render_lottie_preview.cjs <input.tgs|input.json> <output.svg> <output.png|output.webp> [format]");
}

function readAnimationData(inputPath) {
  const bytes = fs.readFileSync(inputPath);
  const text = inputPath.toLowerCase().endsWith(".tgs")
    ? zlib.gunzipSync(bytes).toString("utf8")
    : bytes.toString("utf8");
  return JSON.parse(text);
}

function previewFrame(animationData) {
  const start = Number.isFinite(Number(animationData.ip)) ? Number(animationData.ip) : 0;
  const end = Number.isFinite(Number(animationData.op)) ? Number(animationData.op) : start + 1;
  const frame = start + PREVIEW_FRAME;
  return Math.min(frame, Math.max(start, end - 1));
}

async function main() {
  const [, , inputPath, svgPath, imagePath, requestedFormat] = process.argv;
  if (!inputPath || !svgPath || !imagePath) {
    usage();
    process.exit(2);
  }

  const format = (requestedFormat || path.extname(imagePath).slice(1) || "png").toLowerCase();
  if (!["png", "webp"].includes(format)) {
    console.error(`Unsupported output format: ${format}`);
    process.exit(2);
  }

  const animationData = readAnimationData(inputPath);
  const frame = previewFrame(animationData);
  const svg = await renderSvg(animationData, {}, frame);

  fs.mkdirSync(path.dirname(svgPath), { recursive: true });
  fs.mkdirSync(path.dirname(imagePath), { recursive: true });
  fs.writeFileSync(svgPath, svg, "utf8");

  const image = sharp(Buffer.from(svg));
  if (format === "webp") {
    await image.webp({ lossless: true }).toFile(imagePath);
  } else {
    await image.png().toFile(imagePath);
  }

  process.stdout.write(
    JSON.stringify({
      frame,
      svgPath: path.resolve(svgPath),
      imagePath: path.resolve(imagePath),
      format,
    })
  );
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
