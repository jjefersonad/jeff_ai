import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * fix-prod-frontend-docker-yarn-install-task-docker-1 / REQ-ADD-002
 * Ensures the Docker build context excludes host pollution (node_modules, .next)
 * that breaks or OOMs Portainer builds of docker-compose.prod.yml.
 */
describe("frontend .dockerignore (fix-prod-frontend-docker-yarn-install docker-1)", () => {
  const dockerignorePath = path.resolve(__dirname, "../../.dockerignore");

  it("exists and lists node_modules and .next", () => {
    expect(existsSync(dockerignorePath)).toBe(true);

    const content = readFileSync(dockerignorePath, "utf8");
    const lines = content
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0 && !line.startsWith("#"));

    expect(lines).toEqual(expect.arrayContaining(["node_modules", ".next"]));
  });

  it("also ignores common local noise (.git, logs, coverage)", () => {
    const content = readFileSync(dockerignorePath, "utf8");
    const lines = content
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0 && !line.startsWith("#"));

    expect(lines).toEqual(
      expect.arrayContaining([".git", "npm-debug.log*", "coverage"])
    );
  });
});
