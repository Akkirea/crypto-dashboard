import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "EA Crypto Dashboard",
    short_name: "EA Crypto",
    description: "Live crypto market intelligence, analytics, and paper simulation dashboard.",
    start_url: "/",
    display: "standalone",
    background_color: "#0b0b10",
    theme_color: "#0b0b10",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any"
      }
    ]
  };
}
