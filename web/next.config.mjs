// Static export: `npm run build` writes plain files to out/, deployable on Vercel, Netlify or GitHub Pages.
// Set BASE_PATH=/<repo> when serving from a sub-path (GitHub Pages project sites).
const basePath = process.env.BASE_PATH ?? "";

export default {
  output: "export",
  basePath,
  images: { unoptimized: true },
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
};
