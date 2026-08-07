import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * fix-prod-frontend-docker-yarn-install-task-docker-2 / REQ-ADD-001, REQ-001, REQ-003
 */
describe("Dockerfile.frontend (fix-prod-frontend-docker-yarn-install docker-2)", () => {
  const dockerfilePath = path.resolve(__dirname, "../../Dockerfile.frontend");
  const content = readFileSync(dockerfilePath, "utf8");

  it("installs deps with yarn install --frozen-lockfile in stage base", () => {
    expect(content).toMatch(/RUN\s+yarn\s+install\s+--frozen-lockfile\b/);
    // Must not keep a bare `yarn install` without the freeze flag.
    expect(content).not.toMatch(/RUN\s+yarn\s+install\s*$/m);
  });

  it("keeps base/prod/dev stages and NEXT_PUBLIC_API_URL wiring", () => {
    expect(content).toMatch(/AS base\b/);
    expect(content).toMatch(/AS prod\b/);
    expect(content).toMatch(/AS dev\b/);
    expect(content).toMatch(/ARG NEXT_PUBLIC_API_URL/);
    expect(content).toMatch(/ENV NEXT_PUBLIC_API_URL=\$NEXT_PUBLIC_API_URL/);
    // `dev` remains the last stage (default target when unset).
    const prodIdx = content.lastIndexOf("AS prod");
    const devIdx = content.lastIndexOf("AS dev");
    expect(devIdx).toBeGreaterThan(prodIdx);
  });
});
