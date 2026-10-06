import { Writable } from "node:stream";
import { renderToPipeableStream } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { SiteRoutes } from "./App";
import { ThemeProvider } from "./Theme";
import { guideTopics } from "./public/guideContent";
import { faqs } from "./public/content";

export const publicPages = [
  "/",
  "/guide",
  ...guideTopics.map((topic) => `/guide/${topic.id}`),
  "/docs",
  "/trust",
  "/privacy",
  "/about",
  "/changelog",
];
export function metadata(path: string) {
  const topic = guideTopics.find((item) => path === `/guide/${item.id}`);
  const titles: Record<string, string> = {
    "/": "Know what your software actually does",
    "/guide": "ProjectTrace Guide",
    "/docs": "Documentation",
    "/trust": "Security model",
    "/privacy": "Source and privacy",
    "/about": "About ProjectTrace",
    "/changelog": "Changelog",
  };
  return {
    title: `${topic?.title || titles[path] || "ProjectTrace"} — ProjectTrace`,
    description:
      topic?.simple ||
      "ProjectTrace connects what teams say about software to current evidence. Inspect native quality and security findings, claims, changes, ownership and review decisions.",
    faqs: path === "/" ? faqs : [],
  };
}
export function render(path: string): Promise<string> {
  return new Promise((resolve, reject) => {
    let html = "";
    let failed = false;
    const stream = new Writable({
      write(chunk, _encoding, callback) {
        html += chunk.toString();
        callback();
      },
    });
    stream.on("finish", () => {
      if (!failed) resolve(html);
    });
    const rendering = renderToPipeableStream(
      <ThemeProvider>
        <MemoryRouter initialEntries={[path]}>
          <SiteRoutes />
        </MemoryRouter>
      </ThemeProvider>,
      {
        onAllReady() {
          rendering.pipe(stream);
        },
        onShellError(error) {
          failed = true;
          reject(error);
        },
        onError(error) {
          failed = true;
          reject(error);
        },
      },
    );
    stream.on("error", (error) => {
      rendering.abort();
      reject(error);
    });
  });
}
